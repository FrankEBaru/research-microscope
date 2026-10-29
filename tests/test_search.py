"""Seconds-long checks. Synthetic arrays only. No network, Modal, or model download."""

from collections import OrderedDict

import numpy as np
import pyarrow as pa
import pytest

from eval.citation_recall import evaluate_one, offline_split, recall_at_k, sample_local_ids
from rrm.search.burst import burst_query, rank_expanded
from rrm.search.display import PaperLookup, filter_papers, hydrate, merge_display
from rrm.search.encode import use_proximity
from rrm.search.faissutil import add_vectors, merge_indexes, search_vectors, train_ivfpq, vector_at, vectors_from_table
from rrm.search.graph import Graph, csr_from_edges, edges_from_pairs, int_column, stack_edges
from rrm.search.split import parse_subtopics, skip_split, split_query


def test_split_parse_skip_and_cache():
    assert skip_split("10.1145/3292500.3330919")
    assert skip_split("doi:10.1145/3292500.3330919")
    assert skip_split("1706.03762")
    assert skip_split("arXiv:1706.03762v1")
    assert skip_split("graph neural networks")
    assert not skip_split("How do graph neural networks use citation structure?")
    text = '```json\n{"subtopics": ["attention", "positional encoding", "long context"]}\n```'
    assert parse_subtopics(text) == ["attention", "positional encoding", "long context"]
    wrapped = 'notes {"subtopics": ["a", "b", "c", "d", "e", "f", "g"]} tail'
    assert parse_subtopics(wrapped) == ["a", "b", "c", "d", "e", "f"]
    calls = []

    def complete(query):
        calls.append(query)
        return '{"subtopics": ["one hop", "two hop", "local rank"]}'

    cache = OrderedDict()
    query = "How do graph neural networks use citation structure?"
    assert split_query(query, complete=complete, cache=cache) == ["one hop", "two hop", "local rank"]
    assert split_query(query, complete=complete, cache=cache) == ["one hop", "two hop", "local rank"]
    assert calls == [query]
    assert split_query("1706.03762", complete=complete, cache=cache) == []
    assert calls == [query]


def test_csr_from_shards_and_one_hop():
    table = pa.table({
        "citingcorpusid": pa.array([10, 10, 20, 99, None], type=pa.int64()),
        "citedcorpusid": pa.array([20, 20, 10, 30, 10], type=pa.int64()),
    })
    citing, citing_ok = int_column(table, "citingcorpusid")
    cited, cited_ok = int_column(table, "citedcorpusid")
    cs = np.array([10, 20, 30], dtype=np.int64)
    src_a, dst_a = edges_from_pairs(citing, cited, cs, citing_ok, cited_ok)
    src_b, dst_b = edges_from_pairs(
        np.array([10, 30]), np.array([20, 30]), cs
    )
    src, dst = stack_edges([(src_a, dst_a), (src_b, dst_b)])
    indptr, indices = csr_from_edges(src, dst, 3)
    assert indptr.tolist() == [0, 1, 2, 2]
    assert indices.tolist() == [1, 0]
    graph = Graph.from_edges(cs, src, dst)
    # 10 cites 20. One hop from 10 reaches 20, and the paper that cites 10.
    ranked = rank_expanded([[10]], graph, k=10)
    assert ranked["corpusids"] == [10, 20]
    assert {"citing": 10, "cited": 20} in ranked["edges"]
    assert 30 not in ranked["corpusids"]


def test_rank_boosts_bridges_and_drops_singletons():
    ids = np.array([1, 2, 3, 4, 9], dtype=np.int64)
    # 1→2 and 3→4. 9 has no edge.
    graph = Graph.from_edges(ids, np.array([0, 2]), np.array([1, 3]))
    ranked = rank_expanded([[1], [3, 2], [9]], graph, k=10)
    assert 9 not in ranked["corpusids"]
    order = ranked["corpusids"]
    assert order.index(1) < order.index(3)
    assert order.index(2) < order.index(4)
    assert {edge["citing"] for edge in ranked["edges"]} == {1, 3}


def test_faiss_search_and_merge():
    import faiss

    rng = np.random.default_rng(0)
    n, dim = 1500, 32
    vecs = rng.normal(size=(n, dim)).astype(np.float32) * 0.01
    vecs[0] = 1.0
    ids = np.arange(1000, 1000 + n, dtype=np.int64)
    # A repeated corpus id keeps the first vector.
    table = pa.table({
        "corpusid": pa.array(np.concatenate([ids, ids[:1]]), type=pa.int64()),
        "vector": pa.FixedSizeListArray.from_arrays(
            pa.array(np.vstack([vecs, vecs[:1]]).astype(np.float16).reshape(-1), type=pa.float16()),
            dim,
        ),
    })
    got_ids, got_vecs = vectors_from_table(table)
    assert len(got_ids) == n and int(got_ids[0]) == 1000
    trained = train_ivfpq(got_vecs, nlist=16, m=8, nbits=8, nprobe=16)
    with pytest.raises(ValueError):
        train_ivfpq(got_vecs, nlist=16, m=3, nbits=8, nprobe=4)
    path = "/tmp/rrm-test-trained.index"
    faiss.write_index(trained, path)
    left, right = faiss.read_index(path), faiss.read_index(path)
    add_vectors(left, got_vecs[:800])
    add_vectors(right, got_vecs[800:])
    index, merged_ids = merge_indexes([left, right], [got_ids[:800], got_ids[800:]])
    index.nprobe = 16
    hits = search_vectors(index, merged_ids, got_vecs[0], 5)
    assert hits[0][0] == 1000
    assert [cid for cid, _dist in hits].count(1000) == 1
    assert vector_at(index, merged_ids, 1000) is not None
    assert vector_at(index, merged_ids, -1) is None


def test_display_join_and_hydrate():
    cs = np.array([1, 2], dtype=np.int64)
    papers = pa.table({
        "corpusid": pa.array([2, 1, 1, 9], type=pa.int64()),
        "title": ["b", "a", "a", "nope"],
        "year": pa.array([2020, 2019, 2019, 2018], type=pa.int64()),
        "venue": ["VB", "VA", "VA", "VX"],
        "citationcount": pa.array([3, 4, 4, 1], type=pa.int64()),
    })
    tldrs = pa.table({
        "corpusid": pa.array([1], type=pa.int64()),
        "text": ["short"],
    })
    table = merge_display(filter_papers(papers, cs), tldrs)
    assert table.column("corpusid").to_pylist() == [1, 2]
    assert table.column("title").to_pylist() == ["a", "b"]
    rows = hydrate([2, 7], table)
    assert rows[0]["title"] == "b" and rows[0]["tldr"] is None
    assert rows[1]["title"] is None


def test_eval_recall_uses_graph_references():
    assert recall_at_k([1, 9, 2, 3], [1, 2, 3, 4], 100) == 0.75
    indptr = np.array([0, 1, 21], dtype=np.int64)
    picked = sample_local_ids(indptr, n=1, min_refs=20, seed=0)
    assert picked.tolist() == [1]
    # 11 cites 12 and 13. The held-out paper is 10. Search returns 11, then 10.
    ids = np.array([10, 11, 12, 13], dtype=np.int64)
    graph = Graph.from_edges(ids, np.array([1, 1]), np.array([2, 3]))

    def encode(texts):
        return np.zeros((len(texts), 4), dtype=np.float32)

    def search(vector, k):
        return [(11, 0.1), (10, 0.2)]

    row = evaluate_one(
        "A title about graphs\nAn abstract long enough to split into pieces here",
        exclude=10,
        relevant=[12, 13],
        encode=encode,
        search=search,
        graph=graph,
        split_fn=offline_split,
        k=100,
    )
    assert row["recall"]["knn"] == 0.0
    assert row["recall"]["knn_hop"] == 1.0
    assert row["recall"]["split"] == 1.0
    assert set(row["seconds"]) >= {"encode", "search", "split", "rank_hop"}


def test_full_text_search_overlaps_split():
    ids = np.array([1, 2], dtype=np.int64)
    graph = Graph.from_edges(ids, np.array([0]), np.array([1]))
    order = []

    def encode(texts):
        order.append("encode")
        return np.zeros((len(texts), 4), dtype=np.float32)

    def search(vector, k):
        order.append("search")
        return [(1, 0.2)]

    def split(query):
        order.append("split-start")
        import time
        time.sleep(0.05)
        order.append("split-end")
        return ["citation graphs", "spectral ranking", "query expansion"]

    out = burst_query("How do graph neural networks use citation structure?", encode, search, split, graph)
    assert order.index("search") < order.index("split-end")
    assert out["subtopics"][0] == "citation graphs"
    assert 1 in out["first_ids"]
    assert 2 in out["papers"]["corpusids"]


def test_paper_seed_and_adapter_rule():
    assert use_proximity("graph neural networks") is False
    assert use_proximity("word " * 41) is True
    assert use_proximity("Attention Is All You Need\nWe propose a new simple network.") is True
    ext = pa.struct([("DOI", pa.string()), ("ArXiv", pa.string())])
    papers = pa.table({
        "corpusid": pa.array([5, 6], type=pa.int64()),
        "title": ["Graph Nets", "Attention Is All You Need"],
        "year": pa.array([2018, 2017], type=pa.int64()),
        "venue": ["A", "B"],
        "citationcount": pa.array([1, 2], type=pa.int64()),
        "externalids": pa.array([
            {"DOI": "https://doi.org/10.1145/3292500.3330919", "ArXiv": None},
            {"DOI": None, "ArXiv": "1706.03762v1"},
        ], type=ext),
    })
    table = filter_papers(papers, np.array([5, 6], dtype=np.int64))
    look = PaperLookup(table)
    assert look.resolve("doi:10.1145/3292500.3330919") == 5
    assert look.resolve("arXiv:1706.03762v1") == 6
    assert look.resolve("corpusid:5") == 5
    assert look.resolve("Attention, is ALL you need!") == 6
    assert look.resolve("graph neural networks") is None
    calls = {"encode": 0, "split": 0}

    def encode(texts):
        calls["encode"] += 1
        return np.zeros((len(texts), 4), dtype=np.float32)

    def search(vector, k):
        assert float(vector[0]) == 3.0
        return [(7, 0.2), (5, 0.0)]

    def split(query):
        calls["split"] += 1
        return ["a", "b", "c"]

    graph = Graph.from_edges(np.array([5, 7], dtype=np.int64), np.array([0]), np.array([1]))
    out = burst_query(
        "10.1145/3292500.3330919",
        encode,
        search,
        split,
        graph,
        resolve=lambda query: 5,
        vector_of=lambda corpusid: np.array([3.0, 0.0, 0.0, 0.0], dtype=np.float32),
    )
    assert calls == {"encode": 0, "split": 0}
    assert out["subtopics"] == []
    assert out["papers"]["corpusids"][0] == 5
    assert 7 in out["papers"]["corpusids"]
