"""Pure burst ranking over an in-memory FAISS id map and a CSR citation graph.

One full-text search runs beside the split call. Subtopic hits are then
expanded one hop on the CS-CS graph. Papers that tie several subtopics
together get a higher score. Papers with no citation edge in the candidate
set are dropped. Order is local PageRank times that subtopic count.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from rrm.search.graph import locate


def knn_ids(hits, k, exclude=()):
    """Corpus ids from a distance-sorted hit list, skipping exclude and dupes."""
    skip = set(int(x) for x in exclude)
    out = []
    seen = set()
    for cid, _dist in hits:
        cid = int(cid)
        if cid in skip or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= int(k):
            break
    return out


def pagerank(n, src, dst, iters=20, damping=0.85):
    """Deterministic power iteration. src/dst index the induced subgraph."""
    n = int(n)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    src = np.asarray(src, dtype=np.int64).reshape(-1)
    dst = np.asarray(dst, dtype=np.int64).reshape(-1)
    rank = np.full(n, 1.0 / n, dtype=np.float64)
    if src.size == 0:
        return rank
    outdeg = np.bincount(src, minlength=n).astype(np.float64)
    base = (1.0 - damping) / n
    for _ in range(int(iters)):
        share = np.zeros(n, dtype=np.float64)
        np.add.at(share, dst, damping * rank[src] / outdeg[src])
        dangling = float(rank[outdeg == 0].sum())
        rank = base + share + (damping * dangling / n)
    return rank


def _neighbors(locals_ids, indptr, indices):
    if len(locals_ids) == 0:
        return np.zeros(0, dtype=np.int32)
    parts = []
    for local in np.asarray(locals_ids).reshape(-1):
        local = int(local)
        parts.append(indices[int(indptr[local]) : int(indptr[local + 1])])
    if not parts:
        return np.zeros(0, dtype=np.int32)
    return np.unique(np.concatenate(parts))


def _seeds(group, graph, exclude):
    ids = [int(cid) for cid in group if int(cid) not in exclude]
    if not ids:
        return np.zeros(0, dtype=np.int64)
    hit, pos = locate(graph.ids, ids)
    if not hit.any():
        return np.zeros(0, dtype=np.int64)
    return np.unique(pos[hit])


def rank_expanded(groups, graph, k=100, exclude=(), iters=20):
    """One-hop expansion, drop unlinked singletons, PageRank times subtopic touches.

    groups is a list of corpus-id lists, one per search (full text, then subtopics).
    """
    exclude = set(int(x) for x in exclude)
    group_seeds = [_seeds(group, graph, exclude) for group in groups]
    pieces = [seeds for seeds in group_seeds if seeds.size]
    if not pieces:
        return {"corpusids": [], "scores": [], "edges": []}
    all_seeds = np.unique(np.concatenate(pieces))
    neigh = np.unique(
        np.concatenate(
            [
                _neighbors(all_seeds, graph.out_indptr, graph.out_indices),
                _neighbors(all_seeds, graph.in_indptr, graph.in_indices),
            ]
        )
    )
    cand = np.unique(np.concatenate([all_seeds, neigh]))
    if exclude:
        hit, pos = locate(graph.ids, list(exclude))
        drop = set(pos[hit].tolist())
        if drop:
            cand = np.array([c for c in cand.tolist() if c not in drop], dtype=np.int64)
    if cand.size == 0:
        return {"corpusids": [], "scores": [], "edges": []}

    cand_set = set(int(c) for c in cand.tolist())
    touch = np.zeros(len(graph.ids), dtype=np.int32)
    for seeds in group_seeds:
        if seeds.size == 0:
            continue
        nodes = set(int(s) for s in seeds.tolist())
        nodes.update(int(x) for x in _neighbors(seeds, graph.out_indptr, graph.out_indices))
        nodes.update(int(x) for x in _neighbors(seeds, graph.in_indptr, graph.in_indices))
        for node in nodes:
            if node in cand_set:
                touch[node] += 1

    compact = {int(node): i for i, node in enumerate(cand.tolist())}
    srcs = []
    dsts = []
    for src in cand.tolist():
        start = int(graph.out_indptr[src])
        stop = int(graph.out_indptr[src + 1])
        for dst in graph.out_indices[start:stop]:
            dst = int(dst)
            if dst in cand_set and dst != int(src):
                srcs.append(compact[int(src)])
                dsts.append(compact[dst])
    srcs = np.asarray(srcs, dtype=np.int64)
    dsts = np.asarray(dsts, dtype=np.int64)
    if srcs.size:
        deg = np.bincount(np.concatenate([srcs, dsts]), minlength=len(cand))
    else:
        deg = np.zeros(len(cand), dtype=np.int64)
    keep = deg > 0
    if not np.any(keep):
        return {"corpusids": [], "scores": [], "edges": []}

    new_nodes = np.flatnonzero(keep)
    old_to_new = -np.ones(len(cand), dtype=np.int64)
    old_to_new[new_nodes] = np.arange(new_nodes.size)
    if srcs.size:
        mask = keep[srcs] & keep[dsts]
        srcs = old_to_new[srcs[mask]]
        dsts = old_to_new[dsts[mask]]
    pr = pagerank(int(new_nodes.size), srcs, dsts, iters=iters)
    touches = np.maximum(touch[cand[new_nodes]].astype(np.float64), 1.0)
    scores = pr * touches
    chosen_ids = graph.ids[cand[new_nodes]]
    order = np.lexsort((chosen_ids, -scores))
    order = order[: int(k)]
    chosen_local = cand[new_nodes][order]
    chosen_scores = scores[order]
    chosen_set = set(int(x) for x in chosen_local.tolist())
    edges = []
    for src in sorted(chosen_set):
        start = int(graph.out_indptr[src])
        stop = int(graph.out_indptr[src + 1])
        for dst in graph.out_indices[start:stop]:
            dst = int(dst)
            if dst in chosen_set:
                edges.append({"citing": int(graph.ids[src]), "cited": int(graph.ids[dst])})
    return {
        "corpusids": [int(x) for x in graph.ids[chosen_local].tolist()],
        "scores": [float(x) for x in chosen_scores.tolist()],
        "edges": edges,
    }


def burst_query(query, encode, search, split, graph, k=100, fanout=80, exclude=()):
    """Full-text search overlaps the split. Then one search per subtopic.

    encode(texts) -> (n, d) float32. search(vector, k) -> [(corpusid, dist), ...].
    split(query) -> list[str]. graph is a Graph.
    """
    exclude = set(int(x) for x in exclude)
    seconds = {}

    def _split():
        t0 = time.perf_counter()
        try:
            topics = list(split(query))
        except Exception:
            topics = []
        return topics, time.perf_counter() - t0

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(_split)
        t0 = time.perf_counter()
        qvec = encode([query])[0]
        seconds["encode"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        full = search(qvec, int(fanout))
        seconds["search"] = time.perf_counter() - t0
        subtopics, seconds["split"] = pending.result()

    groups = [[cid for cid, _dist in full]]
    if subtopics:
        t0 = time.perf_counter()
        vecs = encode(list(subtopics))
        seconds["encode"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        for row in vecs:
            groups.append([cid for cid, _dist in search(row, int(fanout))])
        seconds["search"] += time.perf_counter() - t0
    t0 = time.perf_counter()
    ranked = rank_expanded(groups, graph, k=k, exclude=exclude)
    seconds["rank"] = time.perf_counter() - t0
    return {
        "subtopics": list(subtopics),
        "first_ids": knn_ids(full, k, exclude),
        "papers": ranked,
        "seconds": {name: round(value, 4) for name, value in seconds.items()},
    }
