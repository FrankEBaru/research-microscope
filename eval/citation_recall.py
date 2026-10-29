"""Recall@100 of a paper's own CS references, from title + abstract.

The query paper is excluded. Three rankings are compared on the same hits:
plain kNN, kNN plus one citation hop, and the same hop after an offline
split of the query text. The split function is injectable so this file
never calls the Meta API. There is no hand-listed set of expected papers.
"""

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rrm.search.burst import knn_ids, rank_expanded


def recall_at_k(retrieved, relevant, k=100):
    relevant = [int(x) for x in relevant]
    if not relevant:
        return 0.0
    got = {int(x) for x in list(retrieved)[: int(k)]}
    return len(got & set(relevant)) / len(relevant)


def sample_local_ids(indptr, n, min_refs, seed):
    """Local row indexes whose out-degree is at least min_refs."""
    degree = np.diff(np.asarray(indptr))
    eligible = np.flatnonzero(degree >= int(min_refs))
    if eligible.size == 0 or int(n) <= 0:
        return np.zeros(0, dtype=np.int64)
    rng = np.random.default_rng(int(seed))
    take = min(int(n), int(eligible.size))
    return np.sort(rng.choice(eligible, size=take, replace=False)).astype(np.int64)


def offline_split(query):
    """Three slices of the query. Stand-in for the model when it cannot be called."""
    words = query.split()
    if len(words) < 6:
        return []
    cuts = [len(words) // 3, 2 * len(words) // 3]
    parts = [
        " ".join(words[: cuts[0]]),
        " ".join(words[cuts[0] : cuts[1]]),
        " ".join(words[cuts[1] :]),
    ]
    return [part for part in parts if part][:6]


def evaluate_one(query, exclude, relevant, encode, search, graph, split_fn, k=100, fanout=80):
    """Time each stage and score the three rankings. encode/search are callables."""
    seconds = {}
    t0 = time.perf_counter()
    qvec = np.asarray(encode([query]), dtype=np.float32)[0]
    seconds["encode"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    hits = search(qvec, max(int(k), int(fanout)) + 1)
    seconds["search"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    knn = knn_ids(hits, k, [exclude])
    seconds["rank_knn"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    hop = rank_expanded([[cid for cid, _dist in hits]], graph, k=k, exclude=[exclude])
    seconds["rank_hop"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    topics = list(split_fn(query))
    seconds["split"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    vecs = np.asarray(encode(topics), dtype=np.float32) if topics else np.zeros((0, qvec.shape[0]), np.float32)
    seconds["encode_sub"] = time.perf_counter() - t0
    groups = [[cid for cid, _dist in hits]]
    t0 = time.perf_counter()
    for row in vecs:
        groups.append([cid for cid, _dist in search(row, int(fanout))])
    seconds["search_sub"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    split_ranked = rank_expanded(groups, graph, k=k, exclude=[exclude])
    seconds["rank_split"] = time.perf_counter() - t0
    return {
        "recall": {
            "knn": recall_at_k(knn, relevant, k),
            "knn_hop": recall_at_k(hop["corpusids"], relevant, k),
            "split": recall_at_k(split_ranked["corpusids"], relevant, k),
        },
        "seconds": seconds,
    }


def summarize(rows):
    """Mean recall and p50/p95 seconds per stage. rows come from evaluate_one."""
    summary = {"n": len(rows), "recall": {}, "seconds_p50": {}, "seconds_p95": {}}
    if not rows:
        return summary
    for mode in ("knn", "knn_hop", "split"):
        summary["recall"][mode] = float(np.mean([row["recall"][mode] for row in rows]))
    stages = rows[0]["seconds"].keys()
    for stage in stages:
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


def run_loaded(bundle, release, n, min_refs, seed, k, shard_limit, row_limit, split_fn, encode, search):
    """Sample papers that have an abstract and at least min_refs CS references."""
    graph = bundle["graph"]
    degree = np.diff(graph.out_indptr)
    eligible = np.flatnonzero(degree >= int(min_refs))
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
        title = _title_of(bundle["display"], cid)
        if not abstract or not title:
            continue
        relevant = [int(graph.ids[j]) for j in graph.out_neighbors(local).tolist()]
        query = title + "\n" + abstract
        rows.append(
            evaluate_one(query, cid, relevant, encode, search, graph, split_fn, k=k)
        )
    return summarize(rows)


def _modal():
    import modal

    from rrm.search.faissutil import search_vectors
    from rrm.search.serve import image as search_image
    from rrm.search.serve import vol
    from rrm.search.store import load_bundle

    eval_app = modal.App("rrm-citation-recall")

    @eval_app.cls(image=search_image, volumes={"/s2": vol}, cpu=2, memory=16384, timeout=7200)
    class Recall:
        @modal.enter()
        def start(self):
            from rrm.search.encode import QueryEncoder

            self.encoder = QueryEncoder()
            self.bundle = None
            self.key = None

        @modal.method()
        def run(
            self,
            release: str = "2026-10-20",
            dest: str = "index",
            n: int = 100,
            min_refs: int = 20,
            seed: int = 0,
            k: int = 100,
            shard_limit: int = 0,
            row_limit: int = 0,
        ):
            key = (release, dest)
            if self.bundle is None or self.key != key:
                vol.reload()
                self.bundle = load_bundle(Path("/s2") / release / dest)
                self.key = key
            bundle = self.bundle

            def search(vector, k_search):
                return search_vectors(bundle["index"], bundle["faiss_ids"], vector, k_search)

            return run_loaded(
                bundle,
                release,
                n,
                min_refs,
                seed,
                k,
                shard_limit,
                row_limit,
                offline_split,
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
            release, dest, int(n), int(min_refs), int(seed), 100, int(shard_limit), int(row_limit)
        )
        print(json.dumps(out))

    return eval_app


try:
    import modal as _modal_lib
except ImportError:
    _modal_lib = None

if _modal_lib is not None:
    app = _modal()
