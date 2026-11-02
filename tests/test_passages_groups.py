"""Grupos k-means, score penalizado y unión por capas. Sin Modal ni arXiv."""

import numpy as np
import pyarrow as pa

from rrm.passages.groups import (
    assign_vectors,
    ivf_labels,
    partition_stats,
    reservoir_extend,
    select_donors,
    select_mode,
)
from rrm.passages.score import rank_group
from rrm.passages.union import layer_union
from rrm.search.graph import Graph


def _graph():
    ids = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90], dtype=np.int64)
    src = np.array([0, 0, 0, 1, 1, 5, 5], dtype=np.int64)
    dst = np.array([3, 4, 8, 3, 7, 2, 3], dtype=np.int64)
    cc = np.array([0, 0, 1000, 5, 5, 0, 9, 500, 5], dtype=np.int64)
    return Graph.from_edges(ids, src, dst), cc


def test_select_mode_keeps_anchors_behind_the_flag():
    assert select_mode("") == "groups"
    assert select_mode("groups") == "groups"
    assert select_mode("anchors") == "anchors"
    assert select_mode("ANCHORS") == "anchors"


def test_penalized_score_demotes_the_global_hub():
    graph, cc = _graph()
    ranked = rank_group(graph, [10, 20], cc)
    assert [row["corpusid"] for row in ranked] == [40, 50, 90, 80]
    by_id = {row["corpusid"]: row for row in ranked}
    assert by_id[40]["local"] == 2
    assert by_id[80]["local"] == 1 and by_id[80]["citationcount"] == 500
    assert by_id[40]["score"] > by_id[50]["score"] > by_id[80]["score"]
    assert by_id[50]["score"] == by_id[90]["score"]
    assert 30 not in by_id and 70 not in by_id


def test_layer_union_is_round_robin_and_skips_duplicates():
    body = layer_union([[1, 2, 3], [1, 4], [5]], limit=2000)
    assert body["ids"] == [1, 4, 5, 2, 3]
    assert body["layers"] == [1, 1, 1, 2, 3]
    assert body["layer_donors"] == [3, 1, 1]
    assert body["method"] == "layers"
    capped = layer_union([[1, 2], [3, 4], [5]], limit=4)
    assert capped["ids"] == [1, 3, 5, 2] and capped["reached"] is True


def test_donors_skip_ids_without_arxiv_and_do_not_spend_the_turn():
    display = np.array([11, 13], dtype=np.int64)
    donors, pending = select_donors([10, 11, 12, 13], display, set(), keep=2, depth=10)
    assert donors == [11, 13]
    assert pending == [10, 12]
    again, pending = select_donors([10, 11, 12], display, {10}, keep=3, depth=10)
    assert again == [10, 11]
    assert pending == [12]


def test_train_centroids_in_a_clean_process():
    """faiss.Kmeans choca con el SWIG de pymupdf si ese módulo ya se importó."""
    import subprocess
    import sys

    code = (
        "import numpy as np\n"
        "from rrm.passages.groups import train_centroids, assign_vectors\n"
        "rng = np.random.default_rng(0)\n"
        "left = rng.normal(-3, 0.1, size=(40, 4)).astype(np.float32)\n"
        "right = rng.normal(3, 0.1, size=(40, 4)).astype(np.float32)\n"
        "sample = np.vstack([left, right])\n"
        "centroids = train_centroids(sample, 2, seed=0, niter=8)\n"
        "labels = assign_vectors(centroids, sample)\n"
        "assert labels[:40].tolist() == [int(labels[0])] * 40\n"
        "assert int(labels[40]) != int(labels[0])\n"
        "print('ok')\n"
    )
    out = subprocess.check_output([sys.executable, "-c", code], text=True)
    assert "ok" in out


def test_kmeans_separates_two_blobs_and_ivf_lists_cover_every_row():
    import faiss

    rng = np.random.default_rng(0)
    left = rng.normal(-3, 0.1, size=(30, 4)).astype(np.float32)
    right = rng.normal(3, 0.1, size=(30, 4)).astype(np.float32)
    sample = np.vstack([left, right])
    centroids = np.vstack([left.mean(axis=0), right.mean(axis=0)]).astype(np.float32)
    labels = assign_vectors(centroids, sample)
    assert set(labels.tolist()) == {0, 1}
    assert labels[:30].tolist() == [labels[0]] * 30
    assert labels[30] != labels[0]
    buf_ids, buf_vecs, seen = None, None, 0
    buf_ids, buf_vecs, seen = reservoir_extend(buf_ids, buf_vecs, seen, np.arange(10), left[:10], 4, rng)
    buf_ids, buf_vecs, seen = reservoir_extend(buf_ids, buf_vecs, seen, np.arange(10, 40), sample[:30], 4, rng)
    assert seen == 40 and buf_ids.shape == (4,) and buf_vecs.shape == (4, 4)
    stats = partition_stats(np.bincount(labels, minlength=2))
    assert stats["min"] == 30 and stats["max"] == 30 and stats["empty"] == 0

    quant = faiss.IndexFlatL2(4)
    index = faiss.IndexIVFFlat(quant, 4, 4)
    index.train(sample)
    index.add(sample)
    got = ivf_labels(index)
    assert got.shape == (60,) and (got >= 0).all()
    assert len(set(got.tolist())) >= 2


def test_arxiv_column_and_external_ids():
    from rrm.passages.groups import arxiv_from_external, arxiv_ids_from_table

    table = pa.table({
        "corpusid": pa.array([1, 2, 3], type=pa.int64()),
        "arxiv": ["1706.03762", None, ""],
    })
    assert arxiv_ids_from_table(table).tolist() == [1]
    ext = pa.table({
        "corpusid": pa.array([8, 9], type=pa.int64()),
        "externalids": pa.array(
            [{"ArXiv": "1609.02907", "DOI": None}, {"ArXiv": None, "DOI": "10.1/x"}],
            type=pa.struct([("ArXiv", pa.string()), ("DOI", pa.string())]),
        ),
    })
    found = arxiv_from_external(ext, np.array([8, 9], dtype=np.int64))
    assert found == {8: "1609.02907"}
