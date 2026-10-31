"""Map positions from real citations or SPECTER2. No network."""

import json
import threading
import urllib.request

import numpy as np

from rrm.offline import make_server
from rrm.search.layout import WORLD_W, place_papers


def _xs(layout):
    return {point["corpusid"]: point["x"] for point in layout["points"]}


def test_year_axis_orders_years_and_drops_outside_edges():
    papers = [
        {"corpusid": 1, "year": 1990, "title": "A"},
        {"corpusid": 2, "year": 2010, "title": "B"},
        {"corpusid": 3, "title": "C"},
    ]
    edges = [{"citing": 2, "cited": 1}, {"citing": 9, "cited": 1}, {"citing": 3, "cited": 3}]
    layout = place_papers(papers, edges)
    assert layout["method"] == "year-citation"
    assert layout["similarity"] == []
    assert layout["links"] == [{"citing": 2, "cited": 1, "kind": "citation"}]
    xs = _xs(layout)
    assert xs[1] < xs[2] < xs[3]
    assert layout["years"]["missing"] == [3]
    assert layout["grouping"] == "year"
    assert "specter" not in layout["method"]


def test_rank_circle_when_nothing_connects_them():
    layout = place_papers(
        [{"corpusid": 1, "year": 2000}, {"corpusid": 2, "year": 2020}],
        [],
    )
    assert layout["method"] == "rank-circle"
    assert layout["links"] == []
    assert layout["similarity"] == []
    assert layout["points"][0]["rank"] == 0


def test_missing_vector_does_not_invent_a_projection():
    papers = [{"corpusid": 1, "year": 2001}, {"corpusid": 2, "year": 2002}]
    vectors = np.eye(2, dtype=np.float64)
    layout = place_papers(papers, [{"citing": 2, "cited": 1}], vectors, missing_vectors=[2])
    assert layout["method"] == "year-citation"
    assert layout["missing_vectors"] == [2]
    assert "variance" not in layout


def test_specter_pca_groups_by_cosine_and_keeps_citations():
    papers = [
        {"corpusid": 1, "year": 2000},
        {"corpusid": 2, "year": 2001},
        {"corpusid": 3, "year": 2002},
    ]
    vectors = np.asarray([
        [1.0, 0.0, 0.0, 0.0],
        [0.96, 0.28, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ], dtype=np.float64)
    layout = place_papers(papers, [{"citing": 2, "cited": 1}, {"citing": 2, "cited": 99}], vectors)
    assert layout["method"] == "specter2-pca"
    clusters = [point["cluster"] for point in layout["points"]]
    assert clusters[0] == clusters[1]
    assert clusters[2] != clusters[0]
    pairs = {(min(row["a"], row["b"]), max(row["a"], row["b"])) for row in layout["similarity"]}
    assert (1, 2) in pairs
    assert (1, 3) not in pairs
    assert layout["links"] == [{"citing": 2, "cited": 1, "kind": "citation"}]
    share = sum(layout["variance"])
    assert 0 < share <= 1
    assert layout["points"][0]["x"] >= WORLD_W / 2 - 0.1


def test_identical_vectors_are_nudged_and_labeled():
    vector = np.asarray([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    layout = place_papers([{"corpusid": 1}, {"corpusid": 2}], [], vector)
    assert layout["method"] == "specter2-pca"
    assert any(point.get("nudged") for point in layout["points"])
    dist = abs(layout["points"][0]["y"] - layout["points"][1]["y"]) + abs(layout["points"][0]["x"] - layout["points"][1]["x"])
    assert dist >= 28


def test_offline_burst_uses_citations_not_specter(tmp_path):
    root = tmp_path / "fx"
    (root / "burst").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({
        "version": 1,
        "queries": [{"slug": "hello", "q": "hello world"}],
    }), encoding="utf-8")
    (root / "burst" / "hello.json").write_text(json.dumps({
        "query": "hello world",
        "papers": [
            {"corpusid": 1, "year": 1997, "title": "LSTM", "score": 3},
            {"corpusid": 2, "year": 2017, "title": "Attention", "score": 9},
        ],
        "edges": [{"citing": 2, "cited": 1}],
    }), encoding="utf-8")
    httpd = make_server(root, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/burst?q=hello%20world&n=10", timeout=5) as res:
            body = json.loads(res.read().decode())
        assert body["layout"]["method"] == "year-citation"
        assert body["layout"]["links"][0]["kind"] == "citation"
        assert "specter" not in body["layout"]["method"]
        xs = _xs(body["layout"])
        assert xs[1] < xs[2]
    finally:
        httpd.shutdown()
