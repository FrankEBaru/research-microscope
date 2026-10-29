"""Link-out burst ranking on the extended citation graph.

Seeds are a FAISS neighborhood. A candidate's score is the sum of the weights
of seeds that cite it, plus half the candidate's own weight when it is a seed.
Long text (proximity adapter) uses k=200 and an exponential of the distance.
Short text (adhoc_query) uses k=100 and 1/(1+rank/20). Order is score, then
citation count, then corpus id. Muse labels never enter this score.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from rrm.search.encode import use_proximity
from rrm.search.graph import locate

LONG_K = 200
SHORT_K = 100
SEED_BONUS = 0.5
EXACT_CAP = 100
MUSE_TIMEOUT_S = 6.0


def seed_count(proximity):
    return LONG_K if proximity else SHORT_K


def seed_weights(dists, proximity):
    """One weight per seed, in the order given (already distance-sorted)."""
    dists = np.asarray(dists, dtype=np.float64).reshape(-1)
    if dists.size == 0:
        return dists
    if proximity:
        scale = max(float(np.std(dists)), 1e-6)
        return np.exp(-(dists - float(dists.min())) / scale)
    rank = np.arange(dists.size, dtype=np.float64)
    return 1.0 / (1.0 + rank / 20.0)


def gather_out(indptr, indices, nodes):
    """CSR rows for nodes, concatenated, with the seed slot of each entry."""
    nodes = np.asarray(nodes, dtype=np.int64).reshape(-1)
    empty = np.zeros(0, dtype=np.int64)
    if nodes.size == 0:
        return empty, empty
    indptr = np.asarray(indptr)
    start = indptr[nodes]
    length = (indptr[nodes + 1] - start).astype(np.int64, copy=False)
    total = int(length.sum())
    if total == 0:
        return empty, empty
    owner = np.repeat(np.arange(nodes.size, dtype=np.int64), length)
    offset = np.arange(total, dtype=np.int64) - np.repeat(np.cumsum(length) - length, length)
    cited = np.asarray(indices, dtype=np.int64)[start[owner] + offset]
    return cited, owner


def candidate_scores(seed_local, dists, graph, proximity, exclude_local=-1):
    """Score every candidate. uniq is sorted; scores[i] matches uniq[i]."""
    k = seed_count(proximity)
    seed_local = np.asarray(seed_local, dtype=np.int64).reshape(-1)
    dists = np.asarray(dists, dtype=np.float64).reshape(-1)
    m = min(int(seed_local.size), int(dists.size))
    seed_local = seed_local[:m]
    dists = dists[:m]
    if int(exclude_local) >= 0 and seed_local.size:
        keep = seed_local != int(exclude_local)
        seed_local = seed_local[keep]
        dists = dists[keep]
    seed_local = seed_local[:k]
    dists = dists[:k]
    empty_i = np.zeros(0, dtype=np.int64)
    empty_s = np.zeros(0, dtype=np.float64)
    if seed_local.size == 0:
        return empty_i, empty_s
    weights = seed_weights(dists, proximity)
    cited, owner = gather_out(graph.out_indptr, graph.out_indices, seed_local)
    nodes = np.concatenate([cited, seed_local])
    w = np.concatenate([weights[owner], SEED_BONUS * weights])
    if int(exclude_local) >= 0:
        keep = nodes != int(exclude_local)
        nodes = nodes[keep]
        w = w[keep]
    if nodes.size == 0:
        return empty_i, empty_s
    uniq, inv = np.unique(nodes, return_inverse=True)
    scores = np.zeros(uniq.size, dtype=np.float64)
    np.add.at(scores, inv, w)
    return uniq, scores


def order_candidates(uniq, scores, ids, cc, n):
    """score desc, citation count desc, corpus id asc. At most n rows."""
    uniq = np.asarray(uniq, dtype=np.int64).reshape(-1)
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    if uniq.size == 0 or (n is not None and int(n) <= 0):
        return uniq[:0], scores[:0]
    citations = np.asarray(cc, dtype=np.int64)[uniq]
    corpus = np.asarray(ids, dtype=np.int64)[uniq]
    order = np.lexsort((corpus, -citations, -scores))
    if n is not None:
        order = order[: int(n)]
    return uniq[order], scores[order]


def link_rank(seed_local, dists, graph, cc, proximity, n, exclude_local=-1):
    """Top-n local ids and their scores."""
    uniq, scores = candidate_scores(seed_local, dists, graph, proximity, exclude_local)
    return order_candidates(uniq, scores, graph.ids, cc, n)


def top_by_citations(nodes, cc, cap):
    """Highest citation counts first. Stable. At most cap."""
    nodes = np.asarray(nodes, dtype=np.int64).reshape(-1)
    cap = int(cap)
    if nodes.size == 0 or cap <= 0:
        return nodes[:0]
    citations = np.asarray(cc, dtype=np.int64)[nodes]
    order = np.argsort(-citations, kind="stable")
    return nodes[order[:cap]]


def _neighbors(graph, local, outgoing):
    local = int(local)
    indptr = graph.out_indptr if outgoing else graph.in_indptr
    indices = graph.out_indices if outgoing else graph.in_indices
    return np.asarray(indices[int(indptr[local]) : int(indptr[local + 1])], dtype=np.int64)


def _dedupe(blocks, n):
    n = int(n)
    if n <= 0:
        return np.zeros(0, dtype=np.int64)
    seen = set()
    out = []
    for block in blocks:
        for item in np.asarray(block, dtype=np.int64).reshape(-1).tolist():
            item = int(item)
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
            if len(out) >= int(n):
                return np.asarray(out, dtype=np.int64)
    if not out:
        return np.zeros(0, dtype=np.int64)
    return np.asarray(out, dtype=np.int64)


def _scores_for(chosen, uniq, scores):
    chosen = np.asarray(chosen, dtype=np.int64).reshape(-1)
    out = np.zeros(chosen.size, dtype=np.float64)
    if chosen.size == 0 or uniq.size == 0:
        return out
    pos = np.searchsorted(uniq, chosen)
    pos = np.minimum(pos, uniq.size - 1)
    hit = uniq[pos] == chosen
    out[hit] = scores[pos[hit]]
    return out


def exact_locals(seed_local, seed_hits, dists, graph, cc, n):
    """Seed, then its top refs, then its top citers, then the link-out list."""
    refs = top_by_citations(_neighbors(graph, seed_local, True), cc, EXACT_CAP)
    citers = top_by_citations(_neighbors(graph, seed_local, False), cc, EXACT_CAP)
    uniq, scores = candidate_scores(seed_hits, dists, graph, True, exclude_local=seed_local)
    ranked, _ranked_scores = order_candidates(uniq, scores, graph.ids, cc, None)
    chosen = _dedupe(([int(seed_local)], refs, citers, ranked), n)
    return chosen, _scores_for(chosen, uniq, scores)


def _edge_locals(graph, chosen, similar):
    parts = []
    if len(chosen):
        parts.append(np.asarray(chosen, dtype=np.int64).reshape(-1))
    sim_local, _dists = _align(graph, similar)
    if sim_local.size:
        parts.append(sim_local)
    if not parts:
        return np.zeros(0, dtype=np.int64)
    return np.unique(np.concatenate(parts))


def edges_among(graph, locals):
    """Out-edges whose both ends are in locals."""
    chosen = [int(x) for x in np.asarray(locals, dtype=np.int64).reshape(-1).tolist()]
    if not chosen:
        return []
    chosen_set = set(chosen)
    edges = []
    for src in sorted(chosen_set, key=lambda local: int(graph.ids[local])):
        dsts = _neighbors(graph, src, True)
        for dst in dsts.tolist():
            dst = int(dst)
            if dst in chosen_set:
                edges.append({"citing": int(graph.ids[src]), "cited": int(graph.ids[dst])})
    return edges


def _align(graph, hits):
    """Local ids and distances for hits that exist in the graph, same order."""
    if not hits:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    cids = np.asarray([int(cid) for cid, _dist in hits], dtype=np.int64)
    dists = np.asarray([float(dist) for _cid, dist in hits], dtype=np.float64)
    hit, pos = locate(graph.ids, cids)
    return pos[hit].astype(np.int64, copy=False), dists[hit]


def _trim(hits, k, exclude_cid):
    skip = None if exclude_cid is None else int(exclude_cid)
    out = []
    for cid, dist in hits:
        cid = int(cid)
        if skip is not None and cid == skip:
            continue
        out.append((cid, float(dist)))
        if len(out) >= int(k):
            break
    return out


def _ids(graph, locals):
    if len(locals) == 0:
        return []
    return [int(x) for x in np.asarray(graph.ids)[np.asarray(locals, dtype=np.int64)].tolist()]


def _start_split(split, query):
    if split is None:
        return None, None, None
    pool = ThreadPoolExecutor(max_workers=1)
    started = time.perf_counter()

    def _call():
        try:
            return [str(item) for item in split(query)]
        except Exception:
            return []

    return pool.submit(_call), started, pool


def _join_split(pending, started, pool, timeout):
    if pending is None:
        return [], 0.0
    left = float(timeout) - (time.perf_counter() - started)
    topics = []
    try:
        topics = list(pending.result(timeout=max(0.0, left)))
    except Exception:
        topics = []
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return topics, time.perf_counter() - started


def _locate_one(graph, corpusid):
    hit, pos = locate(graph.ids, [int(corpusid)])
    if not bool(hit[0]):
        return -1
    return int(pos[0])


def _result(mode, first_id, papers, scores, similar, edges, subtopics, seconds):
    return {
        "mode": mode,
        "first_id": first_id,
        "papers": {
            "corpusids": papers,
            "scores": [float(x) for x in scores],
        },
        "similar": [{"corpusid": int(cid), "dist": float(dist)} for cid, dist in similar],
        "edges": edges,
        "subtopics": list(subtopics),
        "seconds": {name: round(float(value), 4) for name, value in seconds.items()},
    }


def _from_paper(seed, search, graph, cc, vector_of, n):
    """Stored vector, capped bibliography, then the long-text link rank."""
    seconds = {"encode": 0.0, "search": 0.0, "rank": 0.0, "split": 0.0}
    local = _locate_one(graph, seed)
    hits = []
    t0 = time.perf_counter()
    if vector_of is not None and local >= 0:
        vec = vector_of(int(seed))
        if vec is not None:
            hits = list(search(vec, seed_count(True) + 1))
    seconds["search"] = time.perf_counter() - t0
    similar = _trim(hits, seed_count(True), seed)
    t0 = time.perf_counter()
    if local < 0:
        papers = [int(seed)][: int(n)]
        scores = [0.0] * len(papers)
        edges = []
    else:
        seed_local, dists = _align(graph, similar)
        chosen, score_arr = exact_locals(local, seed_local, dists, graph, cc, n)
        papers = _ids(graph, chosen)
        scores = [float(x) for x in score_arr.tolist()]
        edges = edges_among(graph, _edge_locals(graph, chosen, similar))
    seconds["rank"] = time.perf_counter() - t0
    return _result("paper", int(seed), papers, scores, similar, edges, [], seconds)


def burst_query(
    query,
    encode,
    search,
    graph,
    cc,
    n=50,
    resolve=None,
    vector_of=None,
    split=None,
    split_timeout=MUSE_TIMEOUT_S,
):
    """Rank one query.

    encode(texts) -> (n, d) float32. search(vector, k) -> [(corpusid, dist), ...]
    in ascending distance. graph is the extended Graph. cc[i] is the citation
    count of graph.ids[i]. resolve(query) -> corpus id or None. vector_of(corpus
    id) -> stored vector or None. split(query) -> subtopic strings; it is timed
    out and discarded on failure, and it does not change the ranking.
    """
    n = max(0, int(n))
    if resolve is not None:
        seed = resolve(query)
        if seed is not None:
            return _from_paper(int(seed), search, graph, cc, vector_of, n)

    proximity = use_proximity(query)
    pending, started, pool = _start_split(split, query)
    seconds = {}
    t0 = time.perf_counter()
    qvec = np.asarray(encode([query]), dtype=np.float32)[0]
    seconds["encode"] = time.perf_counter() - t0
    k = seed_count(proximity)
    t0 = time.perf_counter()
    hits = list(search(qvec, k))
    seconds["search"] = time.perf_counter() - t0
    similar = _trim(hits, k, None)
    t0 = time.perf_counter()
    seed_local, dists = _align(graph, similar)
    chosen, score_arr = link_rank(seed_local, dists, graph, cc, proximity, n)
    papers = _ids(graph, chosen)
    edges = edges_among(graph, _edge_locals(graph, chosen, similar))
    seconds["rank"] = time.perf_counter() - t0
    subtopics, seconds["split"] = _join_split(pending, started, pool, split_timeout)
    return _result(
        "long" if proximity else "short",
        None,
        papers,
        score_arr.tolist(),
        similar,
        edges,
        subtopics,
        seconds,
    )
