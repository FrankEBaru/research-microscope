"""One Modal class that keeps FAISS, the extended graph, and both display tables.

MODEL_API_KEY is read from the environment. `modal run` copies it from the
local process with Secret.from_dict. The key is not stored in this repo.
The HTTP endpoint is GET /burst?q=&n= . GET /subtopics?q= returns the
Muse labels separately, so the paper list never waits on Muse.
"""

import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 2:  # local checkout; inside Modal, rrm is already importable
    ROOT = _HERE.parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

import modal

from rrm.search.burst import burst_query
from rrm.search.display import IdTable, PaperLookup
from rrm.search.encode import QueryEncoder
from rrm.search.faissutil import ensure_direct_map, search_vectors, vector_at
from rrm.search.graph import locate
from rrm.search.split import split_query
from rrm.search.store import load_display, load_faiss, load_graph

MOUNT = "/s2"
RELEASE = "2026-10-20"
_endpoint = getattr(modal, "fastapi_endpoint", None) or modal.web_endpoint
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "fastapi[standard]")
    .add_local_python_source("rrm")
)
app = modal.App("rrm-burst")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
if modal.is_local():
    model_secret = modal.Secret.from_dict({"MODEL_API_KEY": os.environ.get("MODEL_API_KEY", "")})
else:
    model_secret = modal.Secret.from_dict({})


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


@app.cls(image=image, volumes={MOUNT: vol}, cpu=2, memory=32768, timeout=900, secrets=[model_secret])
@modal.concurrent(max_inputs=8)  # /subtopics waits seconds on Muse; /burst must not queue behind it
class BurstSearch:
    @modal.enter()
    def start(self):
        import numpy as np
        import pyarrow.parquet as pq

        vol.reload()
        root = Path(MOUNT) / RELEASE
        index, faiss_ids = load_faiss(root / "index")
        index.nprobe = 32
        ensure_direct_map(index)
        display = load_display(root / "index")
        graph = load_graph(root / "index_ext")
        meta = np.load(root / "index_ext" / "node_meta.npz", allow_pickle=True)
        cc = np.maximum(np.asarray(meta["cc"]), 0).astype(np.int64, copy=False)
        is_cs = np.asarray(meta["is_cs"], dtype=bool)
        if len(cc) != len(graph.ids) or len(is_cs) != len(graph.ids):
            raise RuntimeError("node_meta length does not match index_ext graph_ids")
        display_ext = pq.read_table(root / "index_ext" / "display_ext.parquet")
        self.index = index
        self.faiss_ids = faiss_ids
        self.graph = graph
        self.cc = cc
        self.is_cs = is_cs
        self.display = IdTable(display)
        self.display_ext = IdTable(display_ext)
        self.lookup = PaperLookup(display)
        self.encoder = QueryEncoder()
        self.encoder.load()

    def _rows(self, corpusids, scores):
        corpusids = [int(c) for c in corpusids]
        main = self.display.rows(corpusids)
        miss = [cid for cid, row in zip(corpusids, main) if row is None]
        ext = dict(zip(miss, self.display_ext.rows(miss)))
        hit, pos = locate(self.graph.ids, corpusids)
        out = []
        for i, cid in enumerate(corpusids):
            row = main[i]
            from_cs = row is not None
            if row is None:
                row = ext.get(cid)
            if row is None:
                row = {"corpusid": cid, "title": None, "year": None, "venue": None, "citationcount": None}
            if bool(hit[i]):
                local = int(pos[i])
                row["is_cs"] = bool(self.is_cs[local])
                if row["citationcount"] is None:
                    row["citationcount"] = int(self.cc[local])
            else:
                row["is_cs"] = from_cs
            score = None if scores is None else scores[i]
            row["score"] = None if score is None else float(score)
            out.append(row)
        return out

    def _answer(self, query, n):
        n = max(0, min(100, int(n)))

        def search(vector, k):
            return search_vectors(self.index, self.faiss_ids, vector, k)

        def vector_of(corpusid):
            return vector_at(self.index, self.faiss_ids, corpusid)

        result = burst_query(
            query,
            encode=self.encoder.encode,
            search=search,
            graph=self.graph,
            cc=self.cc,
            n=int(n),
            resolve=self.lookup.resolve,
            vector_of=vector_of,
            split=None,  # papers never wait on Muse; labels come from GET /subtopics
        )
        papers = result["papers"]
        _prefetch_reader(papers["corpusids"][:10])
        first = None
        if result["first_id"] is not None:
            first = self._rows([result["first_id"]], [None])[0]
        t0 = time.perf_counter()
        out = {
            "query": query,
            "mode": result["mode"],
            "first": first,
            "papers": self._rows(papers["corpusids"], papers["scores"]),
            "similar": self._rows([row["corpusid"] for row in result["similar"]], None),
            "edges": result["edges"],
            "subtopics": result["subtopics"],
            "seconds": result["seconds"],
        }
        out["seconds"]["hydrate"] = round(time.perf_counter() - t0, 4)
        return out

    @_endpoint(method="GET")
    def burst(self, q: str, n: int = 50):
        return self._answer(q, n)

    @_endpoint(method="GET")
    def subtopics(self, q: str):
        """Muse labels for the same query. Call it in parallel with /burst; it never blocks the list."""
        t0 = time.perf_counter()
        try:
            topics = [str(t) for t in split_query(q)]
        except Exception:
            topics = []
        return {"query": q, "subtopics": topics, "seconds": round(time.perf_counter() - t0, 4)}


def _prefetch_reader(corpusids):
    """Fire-and-forget prepare of the top papers. A missing reader app must not fail the burst."""
    ids = []
    for raw in list(corpusids or [])[:10]:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        return
    try:
        modal.Function.from_name("rrm-reader", "prepare").spawn({"ids": ids})
    except Exception:
        return


@app.local_entrypoint()
def main(query: str, n: int = 50, release: str = "2026-10-20", dest: str = "index"):
    import json

    _safe(release)
    _safe(dest)
    if release != RELEASE or dest != "index":
        raise SystemExit("burst reads /s2/2026-10-20/index and /s2/2026-10-20/index_ext")
    out = BurstSearch().burst.remote(q=query, n=int(n))
    print(json.dumps(out, ensure_ascii=False))
