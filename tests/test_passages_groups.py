"""Grupos k-means, score penalizado y unión por capas. Sin Modal ni arXiv."""

import numpy as np
import pyarrow as pa

from rrm.passages.groups import (
    assign_vectors,
    citation_like,
    corpus_by_arxiv,
    ivf_labels,
    partition_stats,
    probe_group,
    reservoir_extend,
    select_donors,
    select_mode,
    titled_ids_from_table,
    would_split_group,
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
    as_array = rank_group(graph, np.array([10, 20], dtype=np.int64), cc)
    assert [row["corpusid"] for row in as_array] == [40, 50, 90, 80]


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


def test_untitled_is_skipped_and_citation_order_is_only_counted():
    display = np.array([11], dtype=np.int64)
    titled = np.array([11, 12], dtype=np.int64)
    donors, pending = select_donors([99, 11, 12, 10], display, set(), keep=3, depth=10, titled=titled)
    assert donors == [11]
    assert pending == [12]
    same, overlap, n_have = citation_like(np.arange(10), np.arange(10, 0, -1))
    assert same is True and overlap == 10 and n_have == 10
    assert would_split_group(same, overlap, n_have) is True
    shuffled = np.array([3, 1, 4, 0, 2], dtype=np.int64)
    cites = np.array([1, 2, 3, 9, 0], dtype=np.int64)
    same2, overlap2, n2 = citation_like(shuffled, cites, n=5)
    assert same2 is False and n2 == 5
    assert would_split_group(same2, overlap2, n2) is False
    graph, cc = _graph()
    report = probe_group(graph, cc, [10, 20], meta_of=lambda _cid: {}, titled=np.array([40, 50]), n=10)
    assert [row["corpusid"] for row in report["top"]] == [40, 50]
    assert [row["corpusid"] for row in report["by_citations"]] == [40, 50]


def test_title_table_drops_blanks_and_arxiv_version_matches():
    table = pa.table({
        "corpusid": pa.array([1, 2, 3], type=pa.int64()),
        "arxiv": ["2211.15661v2", None, "1706.03762"],
        "title": ["What learning algorithm is in-context learning?", "", "Attention Is All You Need"],
    })
    assert titled_ids_from_table(table).tolist() == [1, 3]
    assert corpus_by_arxiv(table, "2211.15661") == 1
    assert titled_ids_from_table(pa.table({"corpusid": [1]})) is None


def test_seed_document_is_title_newline_abstract():
    from rrm.passages.groups import seed_document

    assert seed_document("What learning", "Investigations with linear models") == (
        "What learning\nInvestigations with linear models"
    )
    assert seed_document("  Only title  ", "  ") == "Only title"


def test_local_harvest_skips_done_and_always_writes_the_log(tmp_path):
    from rrm.passages.arxiv import ArxivStopped
    from rrm.passages.harvest_local import load_meta_map, load_order, pending_ids, run_local

    order = tmp_path / "union.json"
    order.write_text('{"ids": [1, 2, 3, 4]}', encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text('{"papers": [{"corpusid": 2, "arxiv": "1.2"}]}', encoding="utf-8")
    assert load_order(order) == [1, 2, 3, 4]
    assert load_meta_map(meta)[2]["arxiv_id"] == "1.2"
    out = tmp_path / "out"
    (out / "papers").mkdir(parents=True)
    (out / "papers" / "1.json").write_text("{}", encoding="utf-8")
    (out / "failures").mkdir()
    (out / "failures" / "3.json").write_text("{}", encoding="utf-8")
    assert pending_ids([1, 2, 3, 4], out, 2) == [2, 4]

    class Boom:
        log = []

        def gaps(self):
            return []

        def fetch_eprint(self, _arxiv_id):
            raise ArxivStopped("arXiv http 429 repeated")

    summary = run_local([2], {2: {"corpusid": 2, "arxiv_id": "1.2"}}, tmp_path / "out2", limit=1, client=Boom())
    assert summary["error"] == "arXiv http 429 repeated"
    assert (tmp_path / "out2" / "local_requests.json").is_file()


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
