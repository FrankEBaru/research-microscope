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


def test_specter_knn_groups_by_cosine_and_keeps_citations():
    papers = [
        {"corpusid": 1, "year": 2000, "title": "in-context learning"},
        {"corpusid": 2, "year": 2001, "title": "in-context learning prompts"},
        {"corpusid": 3, "year": 2002, "title": "neural radiance field"},
    ]
    vectors = np.asarray([
        [1.0, 0.0, 0.0, 0.0],
        [0.96, 0.28, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ], dtype=np.float64)
    layout = place_papers(papers, [{"citing": 2, "cited": 1}, {"citing": 2, "cited": 99}], vectors)
    assert layout["method"] == "specter2-knn"
    clusters = [point["cluster"] for point in layout["points"]]
    assert clusters[0] == clusters[1]
    assert clusters[2] != clusters[0]
    pairs = {(min(row["a"], row["b"]), max(row["a"], row["b"])) for row in layout["similarity"]}
    assert (1, 2) in pairs
    assert (1, 3) not in pairs
    assert layout["links"] == [{"citing": 2, "cited": 1, "kind": "citation"}]
    assert layout["points"][0]["focus"] is True
    assert layout["neighbors"]["k"] >= 1
    names = " ".join(group["name"] for group in layout["groups"])
    assert "context" in names
    assert "?" not in names


def test_knn_splits_a_neighborhood_across_the_canvas():
    rng = np.random.default_rng(3)
    titles = [
        "in-context learning prompts",
        "neural radiance field",
        "graph neural networks",
        "attention transformer heads",
    ]
    blobs = []
    for t in range(4):
        center = np.zeros(16)
        center[t] = 5.0
        blobs.append(center + rng.normal(scale=0.12, size=(18, 16)))
    vectors = np.vstack(blobs)
    papers = [
        {"corpusid": i + 1, "year": 2018, "title": titles[i // 18], "abstract": titles[i // 18]}
        for i in range(72)
    ]
    layout = place_papers(papers, [], vectors)
    groups = layout["groups"]
    assert 3 <= len(groups) <= 6
    assert all(group["n"] >= 5 for group in groups)
    assert "context" in " ".join(group["name"] for group in groups)
    assert "?" not in " ".join(group["name"] for group in groups)
    for i, a in enumerate(groups):
        for b in groups[i + 1 :]:
            dist = ((a["cx"] - b["cx"]) ** 2 + (a["cy"] - b["cy"]) ** 2) ** 0.5
            assert dist > a["r"] + b["r"]
    pts = [(p["x"], p["y"], p["cluster"]) for p in layout["points"]]
    for i, a in enumerate(pts):
        for b in pts[i + 1 :]:
            if a[2] != b[2]:
                continue
            assert (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 >= 20 ** 2


def test_identical_vectors_stay_apart():
    vector = np.asarray([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    layout = place_papers(
        [{"corpusid": 1, "title": "alpha"}, {"corpusid": 2, "title": "beta"}],
        [],
        vector,
    )
    assert layout["method"] == "specter2-knn"
    dist = abs(layout["points"][0]["y"] - layout["points"][1]["y"]) + abs(layout["points"][0]["x"] - layout["points"][1]["x"])
    assert dist >= 28


def test_map_rows_keeps_ranked_papers_ahead_of_faiss_hits():
    from rrm.search.layout import map_rows

    rows = map_rows({
        "papers": [{"corpusid": 2, "title": "ranked"}],
        "similar": [{"corpusid": 2, "title": "dup"}, {"corpusid": 9, "title": "faiss"}],
    })
    assert [row["corpusid"] for row in rows] == [2, 9]


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


def test_point_i_is_paper_i_on_every_layout_path():
    """RRM-48: a dot opens the paper it is drawn for (click → card → Abrir use point.corpusid)."""
    rng = np.random.default_rng(7)
    papers = [{"corpusid": 100 + i, "year": 2000 + i % 5, "title": f"t{i}"} for i in range(30)]
    edges = [{"citing": 101, "cited": 100}, {"citing": 105, "cited": 103}]
    vectors = rng.normal(size=(30, 8))
    for layout in (place_papers(papers, edges), place_papers(papers, edges, vectors)):
        by_rank = {p["rank"]: p["corpusid"] for p in layout["points"]}
        assert by_rank == {i: row["corpusid"] for i, row in enumerate(papers)}, layout["method"]
