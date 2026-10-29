"""One Modal class that keeps FAISS, the extended graph, and both display tables.

MODEL_API_KEY is read from the environment. `modal run` copies it from the
local process with Secret.from_dict. The key is not stored in this repo.
The HTTP endpoint is GET /burst?q=&n= . Ranking does not wait on Muse; labels
are whatever the split call returns within a few seconds.
"""

import os
import sys
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
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters")
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


def _paper(cid, display, display_ext, graph_ids, is_cs, cc, score):
    row = display.row(cid)
    from_cs = row is not None
    if row is None:
        row = display_ext.row(cid)
    if row is None:
        row = {"corpusid": int(cid), "title": None, "year": None, "venue": None, "citationcount": None}
    hit, pos = locate(graph_ids, [int(cid)])
    if bool(hit[0]):
        local = int(pos[0])
        row["is_cs"] = bool(is_cs[local])
        if row["citationcount"] is None:
            row["citationcount"] = int(cc[local])
    else:
        row["is_cs"] = from_cs
    row["score"] = None if score is None else float(score)
    return row


@app.cls(image=image, volumes={MOUNT: vol}, cpu=2, memory=32768, timeout=900, secrets=[model_secret])
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
        out = []
        for i, cid in enumerate(corpusids):
            score = None if scores is None else scores[i]
            out.append(_paper(cid, self.display, self.display_ext, self.graph.ids, self.is_cs, self.cc, score))
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
            split=split_query,
        )
        papers = result["papers"]
        first = None
        if result["first_id"] is not None:
            first = self._rows([result["first_id"]], [None])[0]
        return {
            "query": query,
            "mode": result["mode"],
            "first": first,
            "papers": self._rows(papers["corpusids"], papers["scores"]),
            "similar": self._rows([row["corpusid"] for row in result["similar"]], None),
            "edges": result["edges"],
            "subtopics": result["subtopics"],
            "seconds": result["seconds"],
        }

    @_endpoint(method="GET")
    def burst(self, q: str, n: int = 50):
        return self._answer(q, n)


@app.local_entrypoint()
def main(query: str, n: int = 50, release: str = "2026-10-20", dest: str = "index"):
    import json

    _safe(release)
    _safe(dest)
    if release != RELEASE or dest != "index":
        raise SystemExit("burst reads /s2/2026-10-20/index and /s2/2026-10-20/index_ext")
    out = BurstSearch().burst.remote(q=query, n=int(n))
    print(json.dumps(out, ensure_ascii=False))
