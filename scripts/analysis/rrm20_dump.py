"""Dump neighbor senses and vote parts for the short-query burst ranker.

Reads the existing volume on CPU. Does not change ranking, does not call the
reader, and does not call the Meta API. Ranking math is the functions in
rrm.search.burst; this file only records how those scores are made.

    modal run scripts/analysis/rrm20_dump.py
    python3 scripts/analysis/rrm20_dump.py --self-check
"""

import json
import re
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rrm.search.burst import SEED_BONUS, _align, candidate_scores, link_rank, seed_count, seed_weights
from rrm.search.display import TITLE_MIN_CITES, TITLE_MIN_WORDS, norm_title
from rrm.search.encode import use_proximity

RELEASE = "2026-10-20"
MOUNT = "/s2"
QUERIES = (
    "diffusion models",
    "graph neural networks",
    "neural radiance fields",
    "transformers for time series forecasting",
    "denoising diffusion probabilistic models",
    "diffusion models image generation",
    "score-based generative models",
    "speech recognition",
    "attention",
    "transformers",
    "graph",
)
TOP_N = 30
VOTER_TOP = 10
CLUSTER_KS = (2, 3, 4, 5)
EXEMPLARS = 6
# Public list price, https://modal.com/pricing (physical core and GiB).
CPU_USD_PER_S = 0.0000131
GIB_USD_PER_S = 0.00000222
CPU_REQUEST = 2.0
MEMORY_MIB = 32768
# Stop inside the container before the hard cap. 40 min at this request is about $0.23.
DEADLINE_S = 40 * 60

# Title patterns used only as counts. The sense split itself is the clustering.
TOKEN_PATTERNS = (
    ("diffusion", re.compile(r"\bdiffusion\b", re.I)),
    ("denois", re.compile(r"denois", re.I)),
    ("score", re.compile(r"\bscore[- ]based\b|\bscore matching\b", re.I)),
    ("generative", re.compile(r"\bgenerative\b", re.I)),
    ("image", re.compile(r"\bimage\b|\bvision\b|\bpixel\b", re.I)),
    ("influence", re.compile(r"\binfluence\b|\bcascade\b|\bsocial network\b|\binformation diffusion\b", re.I)),
    ("graph", re.compile(r"\bgraph\b", re.I)),
    ("transformer", re.compile(r"transformer", re.I)),
    ("attention", re.compile(r"\battention\b", re.I)),
    ("speech", re.compile(r"\bspeech\b|\basr\b", re.I)),
    ("radiance", re.compile(r"radiance|\bnerf\b", re.I)),
    ("forecast", re.compile(r"forecast|time series", re.I)),
    ("adam", re.compile(r"\badam\b", re.I)),
    ("lstm", re.compile(r"\blstm\b|long short-term", re.I)),
)


def _r(value, places=6):
    return round(float(value), places)


def token_counts(titles):
    counts = {name: 0 for name, _pat in TOKEN_PATTERNS}
    for title in titles:
        text = title or ""
        for name, pat in TOKEN_PATTERNS:
            if pat.search(text):
                counts[name] += 1
    return counts


def average_linkage(dist, k):
    """Average-linkage clusters. dist is square and symmetric. Labels are 0..k-1.

    Lance-Williams update: merging a and b gives
    d(a, c) = (n_a d(a, c) + n_b d(b, c)) / (n_a + n_b).
    """
    dist = np.asarray(dist, dtype=np.float64)
    n = int(dist.shape[0])
    k = int(min(max(int(k), 1), n))
    if n == 0 or k == n:
        return np.arange(n, dtype=np.int32)
    gap = np.array(dist, dtype=np.float64, copy=True)
    np.fill_diagonal(gap, np.inf)
    size = np.ones(n, dtype=np.float64)
    current = list(range(n))
    point_cluster = np.arange(n, dtype=np.int32)
    while len(current) > k:
        sub = gap[np.ix_(current, current)]
        flat = int(np.argmin(sub))
        width = len(current)
        a_i, b_i = divmod(flat, width)
        if a_i > b_i:
            a_i, b_i = b_i, a_i
        a = current[a_i]
        b = current[b_i]
        na = float(size[a])
        nb = float(size[b])
        for c in current:
            if c == a or c == b:
                continue
            updated = (na * gap[a, c] + nb * gap[b, c]) / (na + nb)
            gap[a, c] = updated
            gap[c, a] = updated
        size[a] = na + nb
        gap[b, :] = np.inf
        gap[:, b] = np.inf
        gap[a, a] = np.inf
        point_cluster[point_cluster == b] = a
        del current[b_i]
    remap = {cid: i for i, cid in enumerate(current)}
    return np.asarray([remap[int(cid)] for cid in point_cluster.tolist()], dtype=np.int32)


def silhouette(dist, labels):
    dist = np.asarray(dist, dtype=np.float64)
    labels = np.asarray(labels)
    n = int(labels.size)
    uniq = np.unique(labels)
    if n == 0 or uniq.size < 2:
        return 0.0
    scores = np.zeros(n, dtype=np.float64)
    for i in range(n):
        same = labels == labels[i]
        n_same = int(same.sum())
        if n_same <= 1:
            continue
        a = float(dist[i, same].sum() / (n_same - 1))
        b = None
        for lab in uniq:
            if lab == labels[i]:
                continue
            other = labels == lab
            gap = float(dist[i, other].mean())
            if b is None or gap < b:
                b = gap
        denom = max(a, b, 1e-12)
        scores[i] = (b - a) / denom
    return float(scores.mean())


def pairwise_l2(vectors):
    x = np.asarray(vectors, dtype=np.float64)
    sq = np.sum(x * x, axis=1)
    d2 = sq[:, None] + sq[None, :] - 2.0 * (x @ x.T)
    np.maximum(d2, 0.0, out=d2)
    np.fill_diagonal(d2, 0.0)
    return np.sqrt(d2)


def choose_clusters(dist):
    """Pick k in CLUSTER_KS by mean silhouette. Returns labels, k, silhouette."""
    n = int(dist.shape[0])
    if n < 3:
        return np.zeros(n, dtype=np.int32), 1, 0.0
    best = None
    for k in CLUSTER_KS:
        if k >= n:
            continue
        labels = average_linkage(dist, k)
        score = silhouette(dist, labels)
        if best is None or score > best[0]:
            best = (score, k, labels)
    if best is None:
        return np.zeros(n, dtype=np.int32), 1, 0.0
    score, k, labels = best
    return labels, int(k), float(score)


def jaccard_dist(sets):
    n = len(sets)
    dist = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        a = sets[i]
        for j in range(i + 1, n):
            b = sets[j]
            union = len(a | b)
            gap = 1.0 if union == 0 else 1.0 - (len(a & b) / union)
            dist[i, j] = dist[j, i] = gap
    return dist


def vote_parts(seed_local, dists, graph, proximity):
    """Per-candidate vote sum and neighbor bonus. Matches candidate_scores."""
    k = seed_count(proximity)
    seed_local = np.asarray(seed_local, dtype=np.int64).reshape(-1)[:k]
    dists = np.asarray(dists, dtype=np.float64).reshape(-1)[: seed_local.size]
    empty = {
        "seed_local": seed_local,
        "weights": np.zeros(0, dtype=np.float64),
        "voters": {},
        "bonus": {},
    }
    if seed_local.size == 0:
        return empty
    weights = seed_weights(dists, proximity)
    voters = {}
    indptr = graph.out_indptr
    indices = graph.out_indices
    for i, local in enumerate(seed_local.tolist()):
        local = int(local)
        weight = float(weights[i])
        start = int(indptr[local])
        end = int(indptr[local + 1])
        for dst in indices[start:end].tolist():
            voters.setdefault(int(dst), []).append((i, weight))
    bonus = {int(local): SEED_BONUS * float(weights[i]) for i, local in enumerate(seed_local.tolist())}
    uniq, scores = candidate_scores(seed_local, dists, graph, proximity)
    if uniq.size:
        got = np.array(
            [sum(w for _i, w in voters.get(int(node), ())) + bonus.get(int(node), 0.0) for node in uniq.tolist()],
            dtype=np.float64,
        )
        err = float(np.max(np.abs(got - scores)))
    else:
        err = 0.0
    if err > 1e-6:
        raise RuntimeError(f"vote parts differ from candidate_scores by {err}")
    return {"seed_local": seed_local, "weights": weights, "voters": voters, "bonus": bonus, "check_abs": err}


def _coverage(voters_for, weights, members):
    """Share of member weight that cites this candidate. 1 means every member cites it."""
    member_w = float(sum(float(weights[i]) for i in members))
    if member_w <= 0:
        return 0.0, 0.0
    cited = 0.0
    have = {i for i, _w in voters_for}
    for i in members:
        if i in have:
            cited += float(weights[i])
    return cited, cited / member_w


def cluster_winners(labels, parts, ids, year, limit=3):
    """For each cluster, the papers that cluster's seeds cite most, by weight coverage."""
    labels = np.asarray(labels, dtype=np.int32)
    weights = parts["weights"]
    out = []
    for lab in sorted(set(int(x) for x in labels.tolist())):
        members = np.flatnonzero(labels == lab).tolist()
        member_w = float(sum(float(weights[i]) for i in members))
        tally = {}
        member_set = set(members)
        for node, votes in parts["voters"].items():
            cover, frac = _coverage([(i, w) for i, w in votes if i in member_set], weights, members)
            if cover > 0:
                tally[int(node)] = (cover, frac)
        ranked = sorted(tally.items(), key=lambda item: (-item[1][0], int(ids[item[0]])))
        winners = []
        for node, (cover, frac) in ranked[:limit]:
            y = int(year[node])
            winners.append({
                "local": int(node),
                "corpusid": int(ids[node]),
                "year": None if y == 0 else y,
                "vote": _r(cover),
                "weight_coverage": _r(frac),
            })
        out.append({
            "id": int(lab),
            "size": len(members),
            "weight": _r(member_w),
            "winners": winners,
        })
    return out


def indegree_percentile(indeg_sorted, degree):
    n = int(indeg_sorted.size)
    if n == 0:
        return 0.0
    return float(np.searchsorted(indeg_sorted, int(degree), side="right") / n)


def row_stub(local, ids, year, cc, field, field_names, indeg, indeg_sorted):
    fid = int(field[local])
    name = None
    if fid >= 0 and fid < len(field_names):
        name = str(field_names[fid])
    y = int(year[local])
    degree = int(indeg[local])
    return {
        "local": int(local),
        "corpusid": int(ids[local]),
        "year": None if y == 0 else y,
        "field": name,
        "citationcount": int(cc[local]),
        "in_degree": degree,
        "in_degree_percentile": _r(indegree_percentile(indeg_sorted, degree), 4),
    }


def build_query(
    query,
    qvec,
    hits,
    graph,
    cc,
    year,
    field,
    field_names,
    indeg,
    indeg_sorted,
    vectors,
    recon_err,
    resolved,
):
    proximity = use_proximity(query)
    seed_local, dists = _align(graph, hits)
    parts = vote_parts(seed_local, dists, graph, proximity)
    chosen, score_arr = link_rank(seed_local, dists, graph, cc, proximity, TOP_N)
    weights = parts["weights"]
    seed_index = {int(local): i for i, local in enumerate(parts["seed_local"].tolist())}
    titles_for_tokens = []  # filled by the caller after hydration; placeholder
    embed_labels = np.zeros(seed_local.size, dtype=np.int32)
    embed_k, embed_sil = 1, 0.0
    cite_labels = np.zeros(seed_local.size, dtype=np.int32)
    cite_k, cite_sil = 1, 0.0
    if seed_local.size >= 3:
        if vectors is not None and len(vectors) == seed_local.size:
            embed_labels, embed_k, embed_sil = choose_clusters(pairwise_l2(vectors))
        sets = []
        indptr = graph.out_indptr
        indices = graph.out_indices
        for local in seed_local.tolist():
            start = int(indptr[local])
            end = int(indptr[local + 1])
            sets.append(set(int(x) for x in indices[start:end].tolist()))
        cite_labels, cite_k, cite_sil = choose_clusters(jaccard_dist(sets))
    ids = graph.ids
    neighbors = []
    for i, local in enumerate(seed_local.tolist()):
        item = row_stub(local, ids, year, cc, field, field_names, indeg, indeg_sorted)
        item.update({
            "rank": i,
            "dist": _r(dists[i]),
            "weight": _r(weights[i]),
            "embed_cluster": int(embed_labels[i]),
            "cite_cluster": int(cite_labels[i]),
            "out_degree": int(graph.out_indptr[local + 1] - graph.out_indptr[local]),
        })
        neighbors.append(item)
    ranked = []
    for pos, (local, score) in enumerate(zip(chosen.tolist(), score_arr.tolist())):
        local = int(local)
        votes = parts["voters"].get(local, [])
        vote_sum = float(sum(w for _i, w in votes))
        bonus = float(parts["bonus"].get(local, 0.0))
        item = row_stub(local, ids, year, cc, field, field_names, indeg, indeg_sorted)
        item.update({
            "rank": pos + 1,
            "score": _r(score),
            "vote_sum": _r(vote_sum),
            "neighbor_bonus": _r(bonus),
            "n_voters": len(votes),
            "is_neighbor": local in seed_index,
        })
        if pos < VOTER_TOP:
            ordered = sorted(votes, key=lambda pair: -pair[1])
            item["voters"] = [
                {
                    "neighbor_rank": int(i),
                    "corpusid": int(ids[parts["seed_local"][i]]),
                    "weight": _r(w),
                    "embed_cluster": int(embed_labels[i]),
                    "cite_cluster": int(cite_labels[i]),
                }
                for i, w in ordered
            ]
        ranked.append(item)
    total_score = float(score_arr.sum()) if score_arr.size else 0.0
    top_score = float(score_arr[0]) if score_arr.size else 0.0
    n_tied = int(np.sum(np.abs(score_arr - top_score) <= 1e-9)) if score_arr.size else 0
    return {
        "query": query,
        "words": len(query.split()),
        "proximity": bool(proximity),
        "k": int(seed_count(proximity)),
        "faiss_hits": len(hits),
        "seeds": int(seed_local.size),
        "resolved_paper": resolved,
        "reconstruct_l2_mae": None if recon_err is None else _r(recon_err),
        "embed_clusters": {
            "k": embed_k,
            "silhouette": _r(embed_sil),
            "groups": cluster_winners(embed_labels, parts, ids, year),
        },
        "cite_clusters": {
            "k": cite_k,
            "silhouette": _r(cite_sil),
            "groups": cluster_winners(cite_labels, parts, ids, year),
        },
        "score_check_abs": _r(parts.get("check_abs", 0.0), 8),
        "top_score_share": _r(top_score / total_score) if total_score else 0.0,
        "n_tied_at_top_score": n_tied,
        "neighbors": neighbors,
        "ranked": ranked,
        "_token_titles": titles_for_tokens,
    }


def attach_text(blob, rows):
    """Fill title and venue from the display scan. Drop the internal title buffer."""
    for item in blob["neighbors"]:
        row = rows.get(item["corpusid"]) or {}
        item["title"] = row.get("title")
        item["venue"] = row.get("venue")
    for item in blob["ranked"]:
        row = rows.get(item["corpusid"]) or {}
        item["title"] = row.get("title")
        item["venue"] = row.get("venue")
    titles = [item.get("title") for item in blob["neighbors"]]
    blob["neighbor_token_counts"] = token_counts(titles)
    blob["neighbor_year"] = _year_summary(blob["neighbors"])
    for block_name in ("embed_clusters", "cite_clusters"):
        for group in blob[block_name]["groups"]:
            exemplars = [n for n in blob["neighbors"] if n["embed_cluster" if block_name == "embed_clusters" else "cite_cluster"] == group["id"]]
            exemplars = sorted(exemplars, key=lambda n: n["dist"])[:EXEMPLARS]
            group["exemplar_titles"] = [n.get("title") for n in exemplars]
            group["mean_dist"] = _r(float(np.mean([n["dist"] for n in blob["neighbors"] if (n["embed_cluster"] if block_name == "embed_clusters" else n["cite_cluster"]) == group["id"]])))
            for winner in group["winners"]:
                row = rows.get(winner["corpusid"]) or {}
                if row.get("title"):
                    winner["title"] = row["title"]
                if row.get("year") is not None:
                    winner["year"] = row["year"]
    blob.pop("_token_titles", None)
    return blob


def _year_summary(neighbors):
    years = [n["year"] for n in neighbors if n.get("year")]
    if not years:
        return {"n": 0}
    arr = np.asarray(years, dtype=np.int64)
    return {
        "n": int(arr.size),
        "median": int(np.median(arr)),
        "min": int(arr.min()),
        "max": int(arr.max()),
        "before_2018": int(np.sum(arr < 2018)),
        "from_2020": int(np.sum(arr >= 2020)),
    }


def hub_table(queries):
    seen = {}
    for blob in queries:
        for item in blob["ranked"][:10]:
            cid = int(item["corpusid"])
            row = seen.setdefault(cid, {
                "corpusid": cid,
                "title": item.get("title"),
                "year": item.get("year"),
                "in_degree": item["in_degree"],
                "in_degree_percentile": item["in_degree_percentile"],
                "citationcount": item["citationcount"],
                "queries": [],
            })
            row["queries"].append({
                "query": blob["query"],
                "rank": item["rank"],
                "score": item["score"],
                "vote_sum": item["vote_sum"],
                "neighbor_bonus": item["neighbor_bonus"],
            })
    rows = sorted(seen.values(), key=lambda row: (-len(row["queries"]), -row["in_degree"], row["corpusid"]))
    for row in rows:
        row["n_queries_in_top10"] = len(row["queries"])
    return rows


def scan_display(path, wanted, query_norms):
    """Titles for wanted ids, and exact-title resolution for the queries."""
    import pyarrow.parquet as pq

    path = Path(path)
    found = {}
    resolved = {key: None for key in query_norms}
    best_cites = {key: -1 for key in query_norms}
    if not path.exists():
        return found, resolved
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    cols = [c for c in ("corpusid", "title", "year", "venue", "citationcount", "title_norm") if c in names]
    wanted_arr = np.asarray(sorted(wanted), dtype=np.int64)
    if wanted_arr.size == 0:
        wanted_arr = np.zeros(1, dtype=np.int64)
    for batch in pf.iter_batches(columns=cols, batch_size=65536):
        ids = batch.column("corpusid").fill_null(-1).to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
        pos = np.searchsorted(wanted_arr, ids)
        pos = np.minimum(pos, wanted_arr.size - 1)
        hit = wanted_arr[pos] == ids
        if hit.any():
            idx = np.flatnonzero(hit)
            take = idx.astype(np.int64)
            titles = _take_list(batch, "title", take)
            years = _take_list(batch, "year", take)
            venues = _take_list(batch, "venue", take)
            for offset, i in enumerate(idx.tolist()):
                cid = int(ids[i])
                if cid in found:
                    continue
                year = years[offset] if years is not None else None
                found[cid] = {
                    "title": titles[offset] if titles is not None else None,
                    "year": None if year in (None, 0) else int(year),
                    "venue": venues[offset] if venues is not None else None,
                }
        if "title_norm" not in names or not query_norms:
            continue
        norms = batch.column("title_norm").to_pylist()
        cites_col = batch.column("citationcount").to_pylist() if "citationcount" in names else [0] * len(norms)
        for cid, raw, cites in zip(ids.tolist(), norms, cites_col):
            if not raw or raw not in query_norms:
                continue
            cites = int(cites or 0)
            words = query_norms[raw]
            if words < TITLE_MIN_WORDS and cites < TITLE_MIN_CITES:
                continue
            if cites > best_cites[raw]:
                best_cites[raw] = cites
                resolved[raw] = int(cid)
    return found, resolved


def _take_list(batch, name, idx):
    import pyarrow as pa

    if name not in batch.schema.names:
        return None
    return batch.column(name).take(pa.array(idx)).to_pylist()


def reconstruct_rows(index, faiss_ids, corpusids):
    """Stored PQ vectors in corpusids order. None if a row is missing."""
    from rrm.search.faissutil import ensure_direct_map

    ids = np.asarray(faiss_ids, dtype=np.int64).reshape(-1)
    order = np.argsort(ids, kind="mergesort")
    sorted_ids = ids[order]
    corpusids = np.asarray(corpusids, dtype=np.int64)
    pos = np.searchsorted(sorted_ids, corpusids)
    pos = np.minimum(pos, max(sorted_ids.size - 1, 0))
    hit = sorted_ids.size > 0
    hit = hit & (sorted_ids[pos] == corpusids) if sorted_ids.size else np.zeros(corpusids.size, dtype=bool)
    if not bool(np.all(hit)):
        return None
    ensure_direct_map(index)
    rows = order[pos]
    vecs = np.vstack([np.ascontiguousarray(index.reconstruct(int(row)), dtype=np.float32) for row in rows.tolist()])
    return vecs


def self_check():
    from rrm.search.graph import Graph

    ids = np.array([10, 20, 30, 40], dtype=np.int64)
    graph = Graph.from_edges(ids, np.array([0, 0, 1]), np.array([2, 3, 2]))
    parts = vote_parts(np.array([0, 1]), np.array([0.1, 0.2]), graph, False)
    assert parts["check_abs"] < 1e-9
    # Seed 0 weight 1 cites 30 and 40. Seed 1 weight 1/1.05 cites 30.
    # 30 gets both. 10 and 20 get bonuses only.
    chosen, scores = link_rank(np.array([0, 1]), np.array([0.1, 0.2]), graph, np.zeros(4), False, 10)
    assert ids[chosen].tolist()[0] == 30
    assert abs(scores[0] - (1.0 + 1.0 / 1.05)) < 1e-9
    rng = np.random.default_rng(0)
    a = rng.normal(size=(12, 4))
    b = rng.normal(size=(12, 4)) + 4
    labels, k, score = choose_clusters(pairwise_l2(np.vstack([a, b])))
    assert k >= 2
    assert score > 0.5
    left = int(np.sum(labels[:12] == labels[0]))
    assert left >= 10
    print("self-check ok")


def _load_state():
    import pyarrow.parquet as pq

    from rrm.search.encode import QueryEncoder
    from rrm.search.faissutil import search_vectors
    from rrm.search.store import load_faiss, load_graph

    t0 = time.perf_counter()
    root = Path(MOUNT) / RELEASE
    index, faiss_ids = load_faiss(root / "index")
    index.nprobe = 32
    graph = load_graph(root / "index_ext")
    meta = np.load(root / "index_ext" / "node_meta.npz", allow_pickle=True)
    cc = np.maximum(np.asarray(meta["cc"]), 0).astype(np.int64, copy=False)
    year = np.asarray(meta["year"])
    field = np.asarray(meta["field"])
    field_names = np.asarray(meta["field_names"])
    indeg = np.diff(graph.in_indptr).astype(np.int64, copy=False)
    indeg_sorted = np.sort(indeg)
    encoder = QueryEncoder()
    encoder.load()
    display_cols = pq.ParquetFile(root / "index" / "display.parquet").schema_arrow.names
    return {
        "index": index,
        "faiss_ids": faiss_ids,
        "graph": graph,
        "cc": cc,
        "year": year,
        "field": field,
        "field_names": field_names,
        "indeg": indeg,
        "indeg_sorted": indeg_sorted,
        "encoder": encoder,
        "search": lambda vector, k: search_vectors(index, faiss_ids, vector, k),
        "root": root,
        "display_cols": list(display_cols),
        "load_s": time.perf_counter() - t0,
        "t0": t0,
    }


def run_dump():
    started = time.perf_counter()
    state = _load_state()
    if time.perf_counter() - started > DEADLINE_S:
        raise RuntimeError("deadline during load")
    graph = state["graph"]
    query_norms = {norm_title(q): len(norm_title(q).split()) for q in QUERIES}
    blobs = []
    for query in QUERIES:
        if time.perf_counter() - started > DEADLINE_S:
            raise RuntimeError(f"deadline before query {query}")
        qvec = np.asarray(state["encoder"].encode([query]), dtype=np.float32)[0]
        k = seed_count(use_proximity(query))
        hits = list(state["search"](qvec, k))
        seed_local, dists = _align(graph, hits)
        vectors = None
        recon_err = None
        recon_error = None
        try:
            vectors = reconstruct_rows(state["index"], state["faiss_ids"], graph.ids[seed_local])
        except Exception as exc:
            vectors = None
            recon_error = type(exc).__name__
        if vectors is not None:
            err = [abs(float(np.linalg.norm(qvec - vectors[i])) - float(dists[i])) for i in range(len(dists))]
            recon_err = float(np.mean(err)) if err else 0.0
        key = norm_title(query)
        resolved = {"norm": key, "corpusid": None, "title": None}
        blob = build_query(
            query,
            qvec,
            hits,
            graph,
            state["cc"],
            state["year"],
            state["field"],
            state["field_names"],
            state["indeg"],
            state["indeg_sorted"],
            vectors,
            recon_err,
            resolved,
        )
        blob["reconstruct_error"] = recon_error
        blobs.append(blob)
    wanted = set()
    for blob in blobs:
        for item in blob["neighbors"]:
            wanted.add(int(item["corpusid"]))
        for item in blob["ranked"]:
            wanted.add(int(item["corpusid"]))
        for block in (blob["embed_clusters"], blob["cite_clusters"]):
            for group in block["groups"]:
                for winner in group["winners"]:
                    wanted.add(int(winner["corpusid"]))
    # One pass over the CS display table: titles, plus the same exact-title rule as PaperLookup.
    rows, resolved_map = scan_display(state["root"] / "index" / "display.parquet", wanted, query_norms)
    missing = wanted - set(rows)
    if missing:
        ext, _skip = scan_display(state["root"] / "index_ext" / "display_ext.parquet", missing, {})
        rows.update(ext)
    for blob in blobs:
        key = blob["resolved_paper"]["norm"]
        cid = resolved_map.get(key)
        if cid is not None:
            blob["resolved_paper"]["corpusid"] = int(cid)
            blob["resolved_paper"]["title"] = (rows.get(int(cid)) or {}).get("title")
        attach_text(blob, rows)
        for winner_group in (blob["embed_clusters"]["groups"], blob["cite_clusters"]["groups"]):
            for group in winner_group:
                for winner in group["winners"]:
                    if winner.get("year") is None:
                        winner["year"] = (rows.get(winner["corpusid"]) or {}).get("year")
    hubs = hub_table(blobs)
    elapsed = time.perf_counter() - started
    gib = MEMORY_MIB / 1024
    usd = elapsed * (CPU_REQUEST * CPU_USD_PER_S + gib * GIB_USD_PER_S)
    return {
        "release": RELEASE,
        "n_queries": len(blobs),
        "graph_nodes": int(len(graph.ids)),
        "graph_edges": int(len(graph.out_indices)),
        "faiss_ntotal": int(state["index"].ntotal),
        "display_columns": state["display_cols"],
        "field_names": [str(x) for x in state["field_names"].tolist()],
        "load_s": _r(state["load_s"], 3),
        "elapsed_s": _r(elapsed, 3),
        "cost_estimate_usd": _r(usd, 4),
        "cost_note": "https://modal.com/pricing list price times measured container seconds times the request (2 physical cores, 32 GiB). Excludes image build and the 2s scaledown window.",
        "queries": blobs,
        "hubs": hubs,
    }


import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "fastapi[standard]")
    .add_local_python_source("rrm")
)
vol = modal.Volume.from_name("rrm-data", create_if_missing=False)
app = modal.App("rrm-rrm20-analysis")


@app.function(
    image=image,
    volumes={MOUNT: vol},
    cpu=CPU_REQUEST,
    memory=MEMORY_MIB,
    timeout=DEADLINE_S + 120,
    scaledown_window=2,
    retries=0,
)
def dump():
    vol.reload()
    return run_dump()


@app.local_entrypoint()
def main():
    out = dump.remote()
    dest = ROOT / "scripts" / "analysis" / "rrm20_results.json"
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "wrote": str(dest),
        "bytes": dest.stat().st_size,
        "queries": out["n_queries"],
        "elapsed_s": out["elapsed_s"],
        "cost_estimate_usd": out["cost_estimate_usd"],
        "graph_nodes": out["graph_nodes"],
        "faiss_ntotal": out["faiss_ntotal"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        raise SystemExit("use: modal run scripts/analysis/rrm20_dump.py")
