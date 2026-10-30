"""One Modal class that keeps FAISS, the extended graph, and both display tables.

MODEL_API_KEY is read from the environment. `modal run` copies it from the
local process with Secret.from_dict. The key is not stored in this repo.
HTTP is the ASGI app `api` on this class: GET /burst?q=&n= and
GET /subtopics?q= . Subtopics stays off the paper list, so the list never waits on Muse.
"""

import os
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 2:  # local checkout; inside Modal, rrm is already importable
    ROOT = _HERE.parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

import modal

from rrm.demo_guard import check, cors_kwargs
from rrm.demo_warm import scaledown_window
from rrm.search.burst import burst_query
from rrm.search.prefetch import detach_queue, note_burst_top
from rrm.search.display import IdTable, PaperLookup
from rrm.search.encode import QueryEncoder
from rrm.search.faissutil import ensure_direct_map, search_vectors, vector_at
from rrm.search.graph import locate
from rrm.search.split import split_query
from rrm.search.store import load_display, load_faiss, load_graph

MOUNT = "/s2"
RELEASE = "2026-10-20"
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "fastapi[standard]")
    .add_local_python_source("rrm")
)
app = modal.App("rrm-burst")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
if modal.is_local():
    model_secret = modal.Secret.from_dict({
        "MODEL_API_KEY": os.environ.get("MODEL_API_KEY", ""),
        "RRM_DEMO_TOKEN": os.environ.get("RRM_DEMO_TOKEN", ""),
    })
else:
    model_secret = modal.Secret.from_dict({})


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


# RRM_DEMO_KEEP_WARM=1 at deploy time sets scaledown_window to 20 min.
# min_containers stays 0. See scripts/warm.sh.
_burst_cls = dict(image=image, volumes={MOUNT: vol}, cpu=2, memory=32768, timeout=900, secrets=[model_secret])
if scaledown_window() is not None:
    _burst_cls["scaledown_window"] = scaledown_window()


@app.cls(**_burst_cls)
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
        # After the payload exists: a spawn failure must not drop the papers.
        # The top-10 ids are noted for /status here. The volume commit that
        # used to run inside queue_top stays off this return.
        _prefetch_reader(papers["corpusids"][:10])
        return out

    @modal.method()
    def run_burst(self, q: str, n: int = 50):
        return self._answer(q, n)

    @modal.asgi_app()
    def api(self):
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import Response

        web = FastAPI()
        web.add_middleware(CORSMiddleware, **cors_kwargs())

        def gate(request: Request):
            # `k` lets a GET stay a CORS simple request (no OPTIONS) while the container is cold.
            code = check(
                request.headers.get("x-rrm-demo"),
                request.query_params.get("k"),
                request.headers.get("origin"),
            )
            if code:
                return Response(status_code=code)
            return None

        @web.get("/burst")
        def route_burst(request: Request, q: str, n: int = 50):
            denied = gate(request)
            if denied:
                return denied
            return self._answer(q, n)

        @web.get("/subtopics")
        def route_subtopics(request: Request, q: str):
            """Muse labels for the same query. The UI does not call this."""
            denied = gate(request)
            if denied:
                return denied
            t0 = time.perf_counter()
            import rrm.search.split as split_mod
            split_mod.LAST_USAGE = None
            try:
                topics = [str(t) for t in split_query(q)]
            except Exception:
                topics = []
            return {
                "query": q,
                "subtopics": topics,
                "seconds": round(time.perf_counter() - t0, 4),
                "skipped": split_mod.skip_split(q),
                "usage": split_mod.LAST_USAGE,
            }

        return web


def _prefetch_reader(corpusids):
    """Note the top ids, then write queued rows off the response path.

    A missing reader app must not fail the burst. `/status` treats a noted id
    with no meta.json as queued, so the first poll does not wait for the commit.
    """
    def spawn(ids):
        modal.Function.from_name("rrm-reader", "prefetch").spawn(ids)

    def start(work):
        threading.Thread(target=work, name="rrm-queue-top", daemon=True).start()

    try:
        detach_queue(
            corpusids,
            Path(MOUNT) / "papers",
            spawn=spawn,
            commit=vol.commit,
            note=note_burst_top,
            start=start,
        )
    except Exception:
        return


@app.local_entrypoint()
def main(query: str, n: int = 50, release: str = "2026-10-20", dest: str = "index"):
    import json

    _safe(release)
    _safe(dest)
    if release != RELEASE or dest != "index":
        raise SystemExit("burst reads /s2/2026-10-20/index and /s2/2026-10-20/index_ext")
    out = BurstSearch().run_burst.remote(q=query, n=int(n))
    print(json.dumps(out, ensure_ascii=False))
