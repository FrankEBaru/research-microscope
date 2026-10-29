"""One Modal class that keeps the index, graph, and display table in memory.

MODEL_API_KEY is read from the environment. `modal run` copies it from the
local process with Secret.from_dict. The key is not stored in this repo.
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
from rrm.search.display import PaperLookup, hydrate
from rrm.search.encode import QueryEncoder
from rrm.search.faissutil import search_vectors, vector_at
from rrm.search.split import split_query
from rrm.search.store import load_bundle

MOUNT = "/s2"
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


def _rows(ids, scores, table):
    rows = hydrate(ids, table)
    if scores is None:
        return rows
    for row, score in zip(rows, scores):
        row["score"] = score
    return rows


@app.cls(image=image, volumes={MOUNT: vol}, cpu=2, memory=16384, timeout=900, secrets=[model_secret])
class BurstSearch:
    @modal.enter()
    def start(self):
        self.bundle = None
        self.key = None
        self.encoder = QueryEncoder()

    def _bundle(self, release, dest):
        key = (_safe(release), _safe(dest))
        if self.bundle is None or self.key != key:
            vol.reload()
            self.bundle = load_bundle(Path(MOUNT) / key[0] / key[1])
            self.bundle["lookup"] = PaperLookup(self.bundle["display"])
            self.key = key
        return self.bundle

    @modal.method()
    def burst(self, query: str, release: str = "2026-10-20", dest: str = "index", exclude: int = -1):
        bundle = self._bundle(release, dest)
        skip = [] if int(exclude) < 0 else [int(exclude)]

        def search(vector, k):
            return search_vectors(bundle["index"], bundle["faiss_ids"], vector, k)

        def vector_of(corpusid):
            return vector_at(bundle["index"], bundle["faiss_ids"], corpusid)

        result = burst_query(
            query,
            encode=self.encoder.encode,
            search=search,
            split=split_query,
            graph=bundle["graph"],
            exclude=skip,
            resolve=bundle["lookup"].resolve,
            vector_of=vector_of,
        )
        table = bundle["display"]
        papers = result["papers"]
        _prefetch_reader(papers["corpusids"][:10])
        return {
            "query": query,
            "subtopics": result["subtopics"],
            "first": _rows(result["first_ids"], None, table),
            "papers": _rows(papers["corpusids"], papers["scores"], table),
            "edges": papers["edges"],
            "seconds": result["seconds"],
        }


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


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


@app.local_entrypoint()
def main(query: str, release: str = "2026-10-20", dest: str = "index", exclude: int = -1):
    import json

    out = BurstSearch().burst.remote(query, release, dest, int(exclude))
    print(json.dumps(out, ensure_ascii=False))
