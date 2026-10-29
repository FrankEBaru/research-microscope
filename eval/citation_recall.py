"""Citation recall of the link-out burst against plain kNN.

The query is the paper's title and abstract (proximity adapter). The relevant
set is every reference that has a corpus id in index_ext, including papers
with no embedding and papers outside CS. The query paper is excluded.
Recall is reported at 10, 15, 20, 50, and 100, plus precision@10 and nDCG@10.
This file does not call the Meta API.
"""

import math
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 1:  # local checkout; inside Modal, rrm is already importable
    ROOT = _HERE.parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from rrm.search.burst import link_rank, seed_count
from rrm.search.encode import use_proximity
from rrm.search.graph import locate

KS = (10, 15, 20, 50, 100)


def recall_at_k(retrieved, relevant, k=100):
    relevant = [int(x) for x in relevant]
    if not relevant:
        return 0.0
    got = {int(x) for x in list(retrieved)[: int(k)]}
    return len(got & set(relevant)) / len(relevant)


def precision_at_k(retrieved, relevant, k=10):
    k = int(k)
    if k <= 0:
        return 0.0
    rel = {int(x) for x in relevant}
    got = [int(x) for x in list(retrieved)[:k]]
    return sum(1 for cid in got if cid in rel) / k


def ndcg_at_k(retrieved, relevant, k=10):
    k = int(k)
    rel = {int(x) for x in relevant}
    if k <= 0 or not rel:
        return 0.0
    dcg = 0.0
    for i, cid in enumerate(list(retrieved)[:k]):
        if int(cid) in rel:
            dcg += 1.0 / math.log2(i + 2)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(rel))))
    return dcg / ideal if ideal else 0.0


def sample_local_ids(indptr, n, min_refs, seed):
    """Local row indexes whose out-degree is at least min_refs."""
    degree = np.diff(np.asarray(indptr))
    eligible = np.flatnonzero(degree >= int(min_refs))
    if eligible.size == 0 or int(n) <= 0:
        return np.zeros(0, dtype=np.int64)
    rng = np.random.default_rng(int(seed))
    take = min(int(n), int(eligible.size))
    return np.sort(rng.choice(eligible, size=take, replace=False)).astype(np.int64)


def _trim(hits, k, exclude):
    skip = int(exclude)
    out = []
    for cid, dist in hits:
        cid = int(cid)
        if cid == skip:
            continue
        out.append((cid, float(dist)))
        if len(out) >= int(k):
            break
    return out


def _align(graph, hits):
    if not hits:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float64)
    cids = np.asarray([cid for cid, _dist in hits], dtype=np.int64)
    dists = np.asarray([dist for _cid, dist in hits], dtype=np.float64)
    hit, pos = locate(graph.ids, cids)
    return pos[hit].astype(np.int64, copy=False), dists[hit]


def _metrics(retrieved, relevant):
    return {
        "recall": {str(k): recall_at_k(retrieved, relevant, k) for k in KS},
        "precision_at_10": precision_at_k(retrieved, relevant, 10),
        "ndcg_at_10": ndcg_at_k(retrieved, relevant, 10),
    }


def evaluate_one(query, exclude, relevant, encode, search, graph, cc):
    """Score link-out and plain kNN for one paper. encode/search are callables."""
    seconds = {}
    proximity = use_proximity(query)
    t0 = time.perf_counter()
    qvec = np.asarray(encode([query]), dtype=np.float32)[0]
    seconds["encode"] = time.perf_counter() - t0
    k = seed_count(proximity)
    t0 = time.perf_counter()
    hits = list(search(qvec, max(k, max(KS)) + 1))
    seconds["search"] = time.perf_counter() - t0
    knn = [cid for cid, _dist in _trim(hits, max(KS), exclude)]
    seeds = _trim(hits, k, exclude)
    t0 = time.perf_counter()
    seed_local, dists = _align(graph, seeds)
    hit, pos = locate(graph.ids, [int(exclude)])
    exclude_local = int(pos[0]) if bool(hit[0]) else -1
    chosen, _scores = link_rank(seed_local, dists, graph, cc, proximity, max(KS), exclude_local=exclude_local)
    ranked = [int(x) for x in graph.ids[chosen].tolist()] if chosen.size else []
    seconds["rank"] = time.perf_counter() - t0
    burst = _metrics(ranked, relevant)
    knn_m = _metrics(knn, relevant)
    return {
        "recall": {"burst": burst["recall"], "knn": knn_m["recall"]},
        "precision_at_10": {"burst": burst["precision_at_10"], "knn": knn_m["precision_at_10"]},
        "ndcg_at_10": {"burst": burst["ndcg_at_10"], "knn": knn_m["ndcg_at_10"]},
        "seconds": seconds,
    }


def summarize(rows):
    """Mean metrics and p50/p95 seconds. rows come from evaluate_one."""
    summary = {
        "n": len(rows),
        "recall": {"burst": {}, "knn": {}},
        "precision_at_10": {},
        "ndcg_at_10": {},
        "seconds_p50": {},
        "seconds_p95": {},
    }
    if not rows:
        return summary
    for mode in ("burst", "knn"):
        for k in rows[0]["recall"][mode]:
            summary["recall"][mode][k] = float(np.mean([row["recall"][mode][k] for row in rows]))
        summary["precision_at_10"][mode] = float(np.mean([row["precision_at_10"][mode] for row in rows]))
        summary["ndcg_at_10"][mode] = float(np.mean([row["ndcg_at_10"][mode] for row in rows]))
    for stage in rows[0]["seconds"]:
        values = np.array([row["seconds"][stage] for row in rows], dtype=np.float64)
        summary["seconds_p50"][stage] = float(np.percentile(values, 50))
        summary["seconds_p95"][stage] = float(np.percentile(values, 95))
    return summary


def _title_of(table, corpusid):
    from rrm.search.display import hydrate

    row = hydrate([corpusid], table)[0]
    return row["title"]


def _collect_abstracts(release, wanted, shard_limit, row_limit):
    from rrm.search.graph import int_column
    from rrm.search.store import part_names, read_capped

    mount = Path("/s2") / release / "abstracts"
    names = part_names(mount)
    if int(shard_limit) > 0:
        names = names[: int(shard_limit)]
    found = {}
    pending = set(wanted)
    for name in names:
        if not pending:
            break
        table = read_capped(mount / name, ["corpusid", "abstract"], row_limit)
        ids, valid = int_column(table, "corpusid")
        abstracts = table.column("abstract")
        for i, (cid, ok) in enumerate(zip(ids.tolist(), valid.tolist())):
            cid = int(cid)
            if ok and cid in pending:
                text = abstracts[i].as_py() or ""
                if text:
                    found[cid] = text
                    pending.discard(cid)
    return found


def run_loaded(release, display, graph, cc, is_cs, n, min_refs, seed, shard_limit, row_limit, encode, search):
    """Sample CS papers that have an abstract and at least min_refs references."""
    degree = np.diff(graph.out_indptr)
    eligible = np.flatnonzero((degree >= int(min_refs)) & np.asarray(is_cs, dtype=bool))
    if eligible.size == 0 or int(n) <= 0:
        return summarize([])
    rng = np.random.default_rng(int(seed))
    pool_n = min(int(eligible.size), max(int(n) * 50, int(n)))
    pool = rng.choice(eligible, size=pool_n, replace=False)
    wanted = [int(graph.ids[i]) for i in pool.tolist()]
    abstracts = _collect_abstracts(release, set(wanted), shard_limit, row_limit)
    rows = []
    for local in pool.tolist():
        if len(rows) >= int(n):
            break
        cid = int(graph.ids[local])
        abstract = abstracts.get(cid)
        title = _title_of(display, cid)
        if not abstract or not title:
            continue
        relevant = [int(graph.ids[j]) for j in graph.out_neighbors(local).tolist()]
        # Newline marks title + abstract, so QueryEncoder uses the proximity adapter.
        query = title + "\n" + abstract
        rows.append(evaluate_one(query, cid, relevant, encode, search, graph, cc))
    return summarize(rows)


try:
    import modal
except ImportError:
    modal = None

# Module scope, so Modal can import Recall inside the container.
if modal is not None:
    from rrm.search.faissutil import search_vectors
    from rrm.search.serve import image as search_image
    from rrm.search.serve import vol
    from rrm.search.store import load_display, load_faiss, load_graph

    eval_app = modal.App("rrm-citation-recall")

    @eval_app.cls(image=search_image, volumes={"/s2": vol}, cpu=2, memory=32768, timeout=7200)
    class Recall:
        @modal.enter()
        def start(self):
            from rrm.search.encode import QueryEncoder

            self.encoder = QueryEncoder()
            self.ready = None

        def _load(self, release, dest):
            import numpy as np

            key = (release, dest)
            if self.ready is not None and self.ready[0] == key:
                return self.ready[1]
            vol.reload()
            root = Path("/s2") / release
            index, faiss_ids = load_faiss(root / dest)
            index.nprobe = 32
            display = load_display(root / dest)
            graph = load_graph(root / "index_ext")
            meta = np.load(root / "index_ext" / "node_meta.npz", allow_pickle=True)
            cc = np.maximum(np.asarray(meta["cc"]), 0).astype(np.int64, copy=False)
            is_cs = np.asarray(meta["is_cs"], dtype=bool)
            state = {
                "index": index,
                "faiss_ids": faiss_ids,
                "display": display,
                "graph": graph,
                "cc": cc,
                "is_cs": is_cs,
            }
            self.ready = (key, state)
            return state

        @modal.method()
        def run(
            self,
            release: str = "2026-10-20",
            dest: str = "index",
            n: int = 100,
            min_refs: int = 20,
            seed: int = 0,
            shard_limit: int = 0,
            row_limit: int = 0,
        ):
            state = self._load(release, dest)

            def search(vector, k_search):
                return search_vectors(state["index"], state["faiss_ids"], vector, k_search)

            return run_loaded(
                release,
                state["display"],
                state["graph"],
                state["cc"],
                state["is_cs"],
                n,
                min_refs,
                seed,
                shard_limit,
                row_limit,
                self.encoder.encode,
                search,
            )

    @eval_app.local_entrypoint()
    def main(
        release: str = "2026-10-20",
        dest: str = "index",
        n: int = 100,
        min_refs: int = 20,
        seed: int = 0,
        shard_limit: int = 0,
        row_limit: int = 0,
    ):
        import json

        out = Recall().run.remote(
            release, dest, int(n), int(min_refs), int(seed), int(shard_limit), int(row_limit)
        )
        print(json.dumps(out))

    app = eval_app
