"""Seconds-long checks. Synthetic arrays only. No network, Modal, or model download."""

from collections import OrderedDict

import numpy as np
import pyarrow as pa
import pytest

from eval.citation_recall import evaluate_one, ndcg_at_k, precision_at_k, recall_at_k, sample_local_ids
from rrm.search.burst import burst_query, link_rank, seed_weights
from rrm.search.display import IdTable, PaperLookup, filter_papers, hydrate, merge_display
from rrm.search.encode import use_proximity
from rrm.search.faissutil import add_vectors, merge_indexes, search_vectors, train_ivfpq, vector_at, vectors_from_table
from rrm.search.graph import Graph, csr_from_edges, edges_from_pairs, int_column, stack_edges
from rrm.search.split import parse_subtopics, skip_split, split_query, usage_of


def test_split_parse_skip_and_cache():
    assert skip_split("10.1145/3292500.3330919")
    assert skip_split("doi:10.1145/3292500.3330919")
    assert skip_split("1706.03762")
    assert skip_split("arXiv:1706.03762v1")
    assert skip_split("graph neural networks")
    assert not skip_split("How do graph neural networks use citation structure?")
    assert not skip_split("how does self-attention replace recurrence in sequence translation")
    assert skip_split("neural radiance fields view synthesis")
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
    assert usage_of({"usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}) == {
        "prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7,
    }
    assert usage_of({}) is None
    assert usage_of({"usage": {"prompt_tokens": True}}) is None


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
    # 10 cites 20. That citation, plus the seed bonus on 10, is the whole score.
    cc = np.array([1, 4, 0], dtype=np.int64)
    chosen, scores = link_rank(np.array([0]), np.array([0.2]), graph, cc, False, 10)
    assert graph.ids[chosen].tolist() == [20, 10]
    assert scores[0] > scores[1]
    assert 30 not in graph.ids[chosen]


def test_weights_scores_and_tie_break():
    dists = np.array([0.0, 1.0, 3.0])
    scale = float(np.std(dists))
    assert np.allclose(seed_weights(dists, True), np.exp(-(dists - dists.min()) / scale))
    assert np.allclose(seed_weights(np.array([4.0, 100.0]), False), [1.0, 1.0 / 1.05])
    assert np.allclose(seed_weights(np.array([2.0, 2.0]), True), [1.0, 1.0])

    ids = np.array([10, 20, 30, 40], dtype=np.int64)
    # 10 cites 30 and 40. One short seed, so both cited papers share a score.
    graph = Graph.from_edges(ids, np.array([0, 0]), np.array([2, 3]))
    tied = np.array([0, 0, 5, 5], dtype=np.int64)
    chosen, scores = link_rank(np.array([0]), np.array([0.2]), graph, tied, False, 10)
    assert ids[chosen].tolist() == [30, 40, 10]
    assert np.allclose(scores, [1.0, 1.0, 0.5])
    higher = np.array([0, 0, 1, 9], dtype=np.int64)
    chosen, _scores = link_rank(np.array([0]), np.array([0.2]), graph, higher, False, 10)
    assert ids[chosen].tolist() == [40, 30, 10]

    # 20 cites 10. Seeds are 20 then 10, so 10 keeps the incoming weight and its bonus.
    back = Graph.from_edges(np.array([10, 20], dtype=np.int64), np.array([1]), np.array([0]))
    chosen, scores = link_rank(np.array([1, 0]), np.array([0.1, 0.2]), back, np.zeros(2, dtype=np.int64), False, 10)
    assert back.ids[chosen].tolist() == [10, 20]
    assert np.allclose(scores[0], 1.0 + 0.5 / 1.05)
    assert np.allclose(scores[1], 0.5)

    # Short ranking keeps 100 seeds. The 101st seed's citation stays out.
    n = 120
    wide = np.arange(n, dtype=np.int64)
    src = np.arange(101, dtype=np.int64)
    dst = np.array([110] * 100 + [111], dtype=np.int64)
    wide_graph = Graph.from_edges(wide, src, dst)
    cc = np.zeros(n, dtype=np.int64)
    short, _s = link_rank(np.arange(101), np.arange(101, dtype=np.float64), wide_graph, cc, False, 20)
    assert 110 in short
    assert 111 not in short
    long, _s = link_rank(np.arange(101), np.zeros(101), wide_graph, cc, True, 20)
    assert 111 in long


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
    ext = IdTable(pa.table({
        "corpusid": pa.array([8], type=pa.int64()),
        "title": ["Quantum"],
        "year": pa.array([2014], type=pa.int64()),
        "venue": ["PRL"],
        "citationcount": pa.array([12], type=pa.int64()),
    }))
    assert ext.row(8)["title"] == "Quantum"
    assert ext.row(2) is None


def test_eval_recall_uses_graph_references():
    assert recall_at_k([1, 9, 2, 3], [1, 2, 3, 4], 100) == 0.75
    assert precision_at_k([1, 9, 2], [1, 2], 10) == 0.2
    assert ndcg_at_k([12, 13], [12, 13], 10) > ndcg_at_k([11], [12, 13], 10)
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
        "A title about graphs\nAn abstract long enough to count as paper text here",
        exclude=10,
        relevant=[12, 13],
        encode=encode,
        search=search,
        graph=graph,
        cc=np.zeros(4, dtype=np.int64),
    )
    assert row["recall"]["knn"]["10"] == 0.0
    assert row["recall"]["burst"]["10"] == 1.0
    assert row["recall"]["burst"]["100"] == 1.0
    assert row["precision_at_10"]["burst"] == 0.2
    assert row["ndcg_at_10"]["burst"] == ndcg_at_k([12, 13, 11], [12, 13], 10)
    assert set(row["seconds"]) == {"encode", "search", "rank"}


def test_muse_failure_does_not_change_ranking():
    ids = np.array([1, 2], dtype=np.int64)
    graph = Graph.from_edges(ids, np.array([0]), np.array([1]))
    cc = np.array([0, 3], dtype=np.int64)

    def encode(texts):
        return np.zeros((len(texts), 4), dtype=np.float32)

    def search(vector, k):
        return [(1, 0.2), (2, 0.4)]

    base = burst_query("graph neural networks", encode, search, graph, cc, n=10)
    assert base["mode"] == "short"
    assert base["papers"]["corpusids"][0] == 2

    def boom(query):
        raise RuntimeError("muse down")

    failed = burst_query("graph neural networks", encode, search, graph, cc, n=10, split=boom)
    assert failed["subtopics"] == []
    assert failed["papers"] == base["papers"]

    def slow(query):
        import time
        time.sleep(0.4)
        return ["too late"]

    late = burst_query(
        "graph neural networks", encode, search, graph, cc, n=10, split=slow, split_timeout=0.05
    )
    assert late["subtopics"] == []
    assert late["papers"]["corpusids"] == base["papers"]["corpusids"]

    labeled = burst_query(
        "graph neural networks",
        encode,
        search,
        graph,
        cc,
        n=10,
        split=lambda query: ["citation graphs", "a second label"],
    )
    assert labeled["subtopics"] == ["citation graphs", "a second label"]
    assert labeled["papers"] == base["papers"]


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
    assert look.resolve("Graph Nets") is None  # short and barely cited: search instead
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
        graph,
        np.array([2, 1], dtype=np.int64),
        resolve=lambda query: 5,
        vector_of=lambda corpusid: np.array([3.0, 0.0, 0.0, 0.0], dtype=np.float32),
        split=split,
    )
    assert calls == {"encode": 0, "split": 0}
    assert out["mode"] == "paper"
    assert out["subtopics"] == []
    assert out["first_id"] == 5
    assert out["papers"]["corpusids"][0] == 5
    assert 7 in out["papers"]["corpusids"]
    assert {"citing": 5, "cited": 7} in out["edges"]


def test_exact_paper_caps_refs_and_citers():
    # 0 cites 1..101 and is cited by 201..301. Citation count equals the id.
    ids = np.arange(400, dtype=np.int64)
    src = np.array([0] * 101 + list(range(201, 302)), dtype=np.int64)
    dst = np.array(list(range(1, 102)) + [0] * 101, dtype=np.int64)
    graph = Graph.from_edges(ids, src, dst)
    cc = ids.copy()

    def encode(texts):
        raise AssertionError("exact paper does not encode the query")

    def search(vector, k):
        return []

    out = burst_query(
        "1706.03762",
        encode,
        search,
        graph,
        cc,
        n=300,
        resolve=lambda query: 0,
        vector_of=lambda corpusid: np.zeros(4, dtype=np.float32),
        split=lambda query: ["should not run"],
    )
    papers = out["papers"]["corpusids"]
    assert papers[0] == 0
    assert papers[1:101] == list(range(101, 1, -1))
    assert 1 not in papers
    assert papers[101:201] == list(range(301, 201, -1))
    assert 201 not in papers
    assert out["subtopics"] == []
    short = burst_query(
        "1706.03762",
        encode,
        search,
        graph,
        cc,
        n=50,
        resolve=lambda query: 0,
        vector_of=lambda corpusid: None,
    )
    assert short["papers"]["corpusids"] == [0] + list(range(101, 52, -1))
