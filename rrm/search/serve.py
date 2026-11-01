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

from rrm.demo_guard import add_error_json, check, cors_kwargs
from rrm.demo_warm import burst_scaledown
from rrm.features import core_mode, features_mode
from rrm.search.burst import burst_query
from rrm.search.layout import map_rows, place_papers
from rrm.search.qcache import CACHE_DIR, cached_burst, load_entry, normalize_question, save_entry
from rrm.search.vecfill import fill_encoded, read_cache
from rrm.search.prefetch import detach_queue, note_burst_top
from rrm.search.display import IdTable, PaperLookup, is_identifier
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
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "sentencepiece", "fastapi[standard]")
    .run_commands(
        "python -c \"from transformers import MarianTokenizer, MarianMTModel; "
        "MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-es-en'); "
        "MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-es-en')\""
    )
    # RRM-47: SPECTER2 base + both adapters live in the image, so a cold start
    # does not download them from Hugging Face (12 s in RRM-46).
    .run_commands(
        "python -c \"from adapters import AutoAdapterModel; from transformers import AutoTokenizer; "
        "AutoTokenizer.from_pretrained('allenai/specter2_base'); "
        "m = AutoAdapterModel.from_pretrained('allenai/specter2_base'); "
        "m.load_adapter('allenai/specter2_adhoc_query', source='hf', load_as='adhoc_query'); "
        "m.load_adapter('allenai/specter2', source='hf', load_as='proximity')\""
    )
    .add_local_python_source("rrm")
)
app = modal.App("rrm-burst")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
if modal.is_local():
    model_secret = modal.Secret.from_dict({
        "MODEL_API_KEY": os.environ.get("MODEL_API_KEY", ""),
        "RRM_DEMO_TOKEN": os.environ.get("RRM_DEMO_TOKEN", ""),
        "RRM_FEATURES": os.environ.get("RRM_FEATURES", "core"),
        "RRM_GROUP_NAMES": os.environ.get("RRM_GROUP_NAMES", ""),
        "RRM_LOOKUP_SYNC": os.environ.get("RRM_LOOKUP_SYNC", ""),
    })
else:
    model_secret = modal.Secret.from_dict({})


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


# Ten minutes between questions (burst_scaledown). The demo flag still means
# 20 minutes. min_containers stays 0. See scripts/warm.sh.
# Memory snapshot stays off. On this 32 GB class the restore was not clearly
# faster than a full load (128.0 s, 125.6 s, 101.0 s). memory stays 32768.
_burst_cls = dict(
    image=image,
    volumes={MOUNT: vol},
    cpu=2,
    memory=32768,
    timeout=900,
    secrets=[model_secret],
    scaledown_window=burst_scaledown(),
)


@app.cls(**_burst_cls)
@modal.concurrent(max_inputs=8)  # /subtopics waits seconds on Muse; /burst must not queue behind it
class BurstSearch:
    @modal.enter()
    def load(self):
        """Read the index into RAM when the container starts.

        What this loads, from the volume (sizes from the RRM-3 build): FAISS
        index (~999 MB) plus faiss_ids, the citation graph (~2.13 GB of npy),
        node_meta, display.parquet (~2.66 GB), display_ext.parquet, and the
        SPECTER2 query encoder (torch + two adapters). Abstracts are a separate
        dataset and are not loaded here. One short encode warms the tokenizer
        so the first real question does not pay that setup.
        """
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
        self.encoder = QueryEncoder()
        self.encoder.load()
        try:
            self.encoder.encode(["warm"])
        except Exception:
            pass
        # RRM-47: PaperLookup took 66 s of a 114 s cold start (RRM-46). It is
        # built after the encoder, in a thread; _resolve waits for it only for
        # an exact DOI, arXiv, or corpus id. RRM_LOOKUP_SYNC=1 restores the wait.
        self.lookup = None
        self._lookup_ready = threading.Event()

        def build_lookup():
            try:
                self.lookup = PaperLookup(display)
            finally:
                self._lookup_ready.set()

        if os.environ.get("RRM_LOOKUP_SYNC") == "1":
            build_lookup()
        else:
            threading.Thread(target=build_lookup, name="rrm-lookup", daemon=True).start()
        self.loaded = ["faiss", "faiss_ids", "graph", "node_meta", "display", "display_ext", "encoder"]

    @modal.enter()
    def resume(self):
        """Reopen the volume so a cache write sees the latest commit."""
        try:
            vol.reload()
        except Exception:
            return

    def _resolve(self, query):
        """Title matches do not wait for the lookup; SPECTER2 answers meanwhile."""
        ready = getattr(self, "_lookup_ready", None)
        if ready is not None and not ready.is_set():
            if not is_identifier(query):
                return None
            ready.wait(120)
        return self.lookup.resolve(query) if self.lookup is not None else None

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
                row = {"corpusid": cid, "title": None, "year": None, "venue": None, "citationcount": None, "tldr": None, "abstract": None}
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
        root = Path(MOUNT) / CACHE_DIR
        try:
            hit = cached_burst(load_entry(root, query), n)
        except Exception:
            hit = None
        from rrm.search.querylang import cache_miss_spanish

        if hit is not None and cache_miss_spanish(query, hit):
            hit = None
        if hit is not None:
            scored_rows = list(hit.get("papers") or []) + list(hit.get("similar") or [])
            needs_cosine = hit.get("qvec") is not None and (
                hit.get("topic_cosine") is None
                or any(isinstance(row, dict) and row.get("query_cosine") is None for row in scored_rows)
            )
            if needs_cosine:
                self._fill_topic(hit)
            papers = hit.get("papers") or []
            saved = {}
            try:
                entry = load_entry(root, query) or {}
                saved = entry.get("papers") or {}
            except Exception:
                saved = {}
            settled = True
            for row in papers[:10]:
                cid = row.get("corpusid") if isinstance(row, dict) else None
                status = (saved.get(str(cid)) or {}).get("status")
                if status not in ("done", "abstract_only", "failed"):
                    settled = False
                    break
            if papers and not settled:
                _prefetch_reader([row.get("corpusid") for row in papers[:10]])
            hit.pop("qvec", None)
            return self._with_layout(hit)
        out = self._compute(query, n)
        _store_burst(query, out)
        out.pop("qvec", None)
        return self._with_layout(out)

    def _vector_cache(self):
        return Path(MOUNT) / CACHE_DIR / "vectors"

    def _stored_slots(self, rows):
        """Index vector, else the encode cache. Does not run the encoder."""
        index = getattr(self, "index", None)
        faiss_ids = getattr(self, "faiss_ids", None)
        cache = self._vector_cache()
        slots = []
        missing = []
        for row in rows:
            vec = None
            if index is not None and faiss_ids is not None:
                vec = vector_at(index, faiss_ids, int(row["corpusid"]))
            if vec is None:
                vec = read_cache(cache, row["corpusid"])
            if vec is None:
                missing.append(int(row["corpusid"]))
            slots.append(vec)
        return slots, missing

    def _remember_vectors(self, key, matrix):
        if not key or matrix is None:
            return
        if not hasattr(self, "_vectors"):
            self._vectors = {}
        self._vectors[key] = matrix

    def _remember_layout(self, key, layout):
        if not key:
            return
        if not hasattr(self, "_layouts"):
            self._layouts = {}
        self._layouts[key] = layout

    def _refine_layout(self, key, rows, edges, slots):
        """Encode the holes off the response path, then swap in the kNN map."""
        encode = getattr(getattr(self, "encoder", None), "encode", None)
        if not key or encode is None or not rows:
            return
        if not hasattr(self, "_refining"):
            self._refining = set()
        if key in self._refining:
            return
        self._refining.add(key)
        cache = self._vector_cache()
        if not hasattr(self, "_encode_lock"):
            self._encode_lock = threading.Lock()
        lock = self._encode_lock

        def work():
            try:
                with lock:
                    matrix, still = fill_encoded(rows, slots, encode, cache)
                if matrix is not None:
                    layout = place_papers(rows, edges, matrix)
                    self._remember_vectors(key, matrix)
                else:
                    layout = dict(place_papers(rows, edges, missing_vectors=still))
                    layout["pending_vectors"] = []
                self._remember_layout(key, layout)
                try:
                    vol.commit()
                except Exception:
                    return
            finally:
                self._refining.discard(key)

        threading.Thread(target=work, name="rrm-map-refine", daemon=True).start()

    def _with_layout(self, payload):
        """Map of the ranked list plus every FAISS hit. Encoding holes does not block the first paint."""
        out = dict(payload)
        rows = map_rows(out)
        edges = out.get("edges") or []
        key = normalize_question(out.get("query") or payload.get("query") or "")
        ready = getattr(self, "_layouts", {}).get(key) if key else None
        if isinstance(ready, dict):
            ids = {int(row["corpusid"]) for row in rows}
            have = {int(point.get("corpusid")) for point in ready.get("points") or [] if isinstance(point, dict)}
            if ids and ids <= have:
                out["layout"] = ready
                return out
        slots, missing = self._stored_slots(rows)
        if rows and not missing:
            import numpy as np

            matrix = np.stack(slots)
            out["layout"] = place_papers(rows, edges, matrix)
            self._remember_layout(key, out["layout"])
            self._remember_vectors(key, matrix)
            return out
        out["layout"] = place_papers(rows, edges, missing_vectors=missing or None)
        if missing:
            out["layout"] = dict(out["layout"])
            out["layout"]["pending_vectors"] = missing
            self._refine_layout(key, rows, edges, slots)
        return out

    def _fill_topic(self, payload):
        from rrm.search.labels import cosine
        from rrm.search.querylang import topic_fields

        ids = []
        for key in ("papers", "similar"):
            for row in payload.get(key) or []:
                if isinstance(row, dict) and row.get("corpusid") is not None:
                    ids.append(row.get("corpusid"))

        def vector_of(corpusid):
            return vector_at(self.index, self.faiss_ids, corpusid)

        payload.update(topic_fields(payload.get("qvec"), ids, vector_of, cosine))
        _stamp_cosines(payload)

    def _compute(self, query, n):
        def search(vector, k):
            return search_vectors(self.index, self.faiss_ids, vector, k)

        def vector_of(corpusid):
            return vector_at(self.index, self.faiss_ids, corpusid)

        from rrm.search.labels import cosine
        from rrm.search.querylang import retrieval_query, topic_fields

        encoded, query_en = retrieval_query(query)
        result = burst_query(
            encoded,
            encode=self.encoder.encode,
            search=search,
            graph=self.graph,
            cc=self.cc,
            n=int(n),
            resolve=self._resolve,
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
            "query_en": query_en,
            "mode": result["mode"],
            "first": first,
            "papers": self._rows(papers["corpusids"], papers["scores"]),
            "similar": self._rows([row["corpusid"] for row in result["similar"]], None),
            "edges": result["edges"],
            "subtopics": result["subtopics"],
            "seconds": result["seconds"],
        }
        if result.get("qvec"):
            out["qvec"] = result["qvec"]
        out.update(topic_fields(result.get("qvec"), list(papers["corpusids"]) + [row["corpusid"] for row in result["similar"]], vector_of, cosine))
        _stamp_cosines(out)
        out["seconds"]["hydrate"] = round(time.perf_counter() - t0, 4)
        out["n"] = int(n)
        out["cached"] = False
        # After the payload exists: a spawn failure must not drop the papers.
        # The top-10 ids are noted for /status here. The volume commit that
        # used to run inside queue_top stays off this return.
        _prefetch_reader(papers["corpusids"][:10])
        return out

    def _labels(self, query: str):
        from rrm.search.labelnet import candidate_ids, cosines_for, lookup_meta, review_ids
        from rrm.search.labels import label_payload

        root = Path(MOUNT) / CACHE_DIR
        try:
            entry = load_entry(root, query)
        except Exception:
            entry = None
        burst = entry.get("burst") if isinstance(entry, dict) else None
        if not isinstance(burst, dict):
            from rrm.search.labels import pending_payload

            return pending_payload([])
        ids = candidate_ids(burst)
        meta = lookup_meta(ids, Path(MOUNT) / "label_cache", timeout=6)
        encode = getattr(getattr(self, "encoder", None), "encode", None)
        index = getattr(self, "index", None)
        faiss_ids = getattr(self, "faiss_ids", None)

        def vector_of(corpusid):
            if index is None or faiss_ids is None:
                return None
            return vector_at(index, faiss_ids, corpusid)

        scores = cosines_for(review_ids(meta), None if burst.get("qvec") else encode, vector_of, query, query_vec=burst.get("qvec")) if meta else {}
        return label_payload(burst.get("papers"), burst.get("similar"), meta, scores)

    @modal.method()
    def run_burst(self, q: str, n: int = 50):
        return self._answer(q, n)

    def _measure_one(self, q: str):
        """One question: first paint, then the kNN map once missing vectors are filled."""
        t0 = time.perf_counter()
        first = self._answer(q, 10)
        t_first = round(time.perf_counter() - t0, 3)
        key = normalize_question(q)
        ready = first.get("layout") if isinstance(first, dict) else None
        waited = 0.0
        if isinstance(ready, dict) and ready.get("pending_vectors"):
            t1 = time.perf_counter()
            while time.perf_counter() - t1 < 40:
                nxt = getattr(self, "_layouts", {}).get(key)
                if isinstance(nxt, dict) and not nxt.get("pending_vectors"):
                    ready = nxt
                    break
                time.sleep(0.25)
            else:
                nxt = getattr(self, "_layouts", {}).get(key)
                if isinstance(nxt, dict):
                    ready = nxt
            waited = round(time.perf_counter() - t1, 3)
        rows = map_rows(first if isinstance(first, dict) else {})
        groups = []
        for group in (ready or {}).get("groups") or []:
            if isinstance(group, dict):
                groups.append({"name": group.get("name"), "n": group.get("n")})
        layout = ready if isinstance(ready, dict) else {}
        return {
            "query": q,
            "t_first_s": t_first,
            "t_refine_s": waited,
            "ranked": len((first or {}).get("papers") or []),
            "faiss": len((first or {}).get("similar") or []),
            "map": len(rows),
            "method": layout.get("method"),
            "pending": layout.get("pending_vectors") or [],
            "neighbors": layout.get("neighbors"),
            "groups": groups,
            "seconds": (first or {}).get("seconds"),
            "cached": (first or {}).get("cached"),
            "layout": {key: layout.get(key) for key in ("method", "points", "groups", "links", "neighbors", "width", "height")},
            "rows": [_slim_row(row) for row in rows],
            "edges": (first or {}).get("edges") or [],
            "vectors": _rounded_vectors(getattr(self, "_vectors", {}).get(key)),
        }

    @modal.method()
    def measure_query(self, q: str):
        return self._measure_one(q)

    @modal.method()
    def measure_queries(self, queries: list[str]):
        """All questions in one container so the index loads once."""
        return [self._measure_one(q) for q in queries]

    @modal.asgi_app()
    def api(self):
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import Response

        web = FastAPI()
        add_error_json(web)
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

        @web.get("/warm")
        def route_warm(request: Request):
            """Returns only after load() has finished, so the UI can wait once."""
            denied = gate(request)
            if denied:
                return denied
            return {"ready": True, "features": features_mode(), "loaded": list(getattr(self, "loaded", []))}

        @web.post("/group-names")
        async def route_group_names(request: Request):
            """Un nombre por grupo, después de pintar. Apagado si el flag no está."""
            denied = gate(request)
            if denied:
                return denied
            from rrm.search.groupnames import enabled, name_groups

            if not enabled():
                return {"enabled": False, "names": []}
            try:
                item = await request.json()
            except Exception:
                item = {}
            names, meta = name_groups((item or {}).get("groups") or [])
            return {"enabled": True, "names": names, "meta": meta}

        @web.get("/labels")
        def route_labels(request: Request, q: str):
            """Abstract, survey y retractación. No bloquea /burst ni vuelve a correr FAISS."""
            denied = gate(request)
            if denied:
                return denied
            return self._labels(q)

        @web.get("/map")
        def route_map(request: Request, q: str):
            """Layout after missing SPECTER2 vectors are filled. The first /burst does not wait for that."""
            denied = gate(request)
            if denied:
                return denied
            key = normalize_question(q)
            layout = getattr(self, "_layouts", {}).get(key) if key else None
            pending = bool(key and key in getattr(self, "_refining", set()))
            if isinstance(layout, dict) and layout.get("pending_vectors"):
                pending = True
            return {"layout": layout, "pending": pending or layout is None}

        @web.get("/burst")
        def route_burst(request: Request, q: str, n: int = 50):
            denied = gate(request)
            if denied:
                return denied
            body = self._answer(q, n)
            if isinstance(body, dict):
                from rrm.search.groupnames import enabled

                body["group_names"] = enabled()
            return body

        @web.get("/subtopics")
        def route_subtopics(request: Request, q: str):
            """Muse labels for the same query. The UI does not call this in core."""
            denied = gate(request)
            if denied:
                return denied
            if core_mode():
                return {"query": q, "subtopics": [], "seconds": 0, "skipped": True, "reason": "core", "usage": None}
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


def _stamp_cosines(payload):
    """Copia query_cosines a cada paper y lo quita del cuerpo suelto."""
    if not isinstance(payload, dict):
        return
    scores = payload.pop("query_cosines", None) or {}
    if not isinstance(scores, dict):
        return
    for key in ("papers", "similar"):
        for row in payload.get(key) or []:
            if not isinstance(row, dict):
                continue
            score = scores.get(str(row.get("corpusid")))
            if isinstance(score, (int, float)):
                row["query_cosine"] = float(score)


def _store_burst(query, payload):
    """Write the question cache off the response path. A commit must not slow /burst."""
    body = dict(payload)
    body.pop("cached", None)

    def work():
        try:
            save_entry(Path(MOUNT) / CACHE_DIR, query, burst=body)
            vol.commit()
        except Exception:
            return

    threading.Thread(target=work, name="rrm-qcache", daemon=True).start()


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


def _rounded_vectors(matrix):
    if matrix is None:
        return None
    import numpy as np

    arr = np.asarray(matrix, dtype=np.float64)
    if arr.ndim != 2 or arr.size == 0:
        return None
    return np.round(arr, 4).tolist()


def _slim_row(row):
    if not isinstance(row, dict):
        return {}
    out = {}
    for key in ("corpusid", "title", "year", "venue", "citationcount", "abstract", "authors", "tldr"):
        val = row.get(key)
        if val is None or val == "":
            continue
        if key == "abstract":
            val = str(val)[:500]
        out[key] = val
    return out


@app.local_entrypoint()
def measure():
    """Three real questions, one container. Prints JSON lines with the map, not full papers."""
    import json

    questions = [
        "what learning algorithm is in-context learning",
        "neural radiance field anti-aliasing",
        "survey of graph neural networks",
    ]
    rows = BurstSearch().measure_queries.remote(questions)
    dest = os.environ.get("RRM_MEASURE_OUT", "")
    if dest:
        Path(dest).write_text(json.dumps(rows), encoding="utf-8")
    for summary in rows:
        public = dict(summary)
        public.pop("vectors", None)
        print(json.dumps(public, ensure_ascii=False), flush=True)
