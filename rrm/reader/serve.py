"""Modal app rrm-reader: CPU fetch + LaTeX, parallel MinerU 2.5 on L4, SAM on demand.

    modal run rrm/reader/serve.py::bench --ids 2048380074,123

HTTP is one ASGI app, `api` (not one host per route):
    POST /prepare   {"ids": [corpusid, ...]}  -> spawn, return per-id status
    GET  /paper?id=corpusid                   -> stub immediately, then the growing cache
    GET  /crops?id=corpusid&pages=0,1         -> SAM for those pages, in the background
    GET  /status?ids=1,2,3                    -> status, stage, per-stage progress
    GET  /file?id=&name=&k=                   -> a figure or crop file, or 404
    POST /panorama  {"question", "ids"}       -> selections [{id, statement, selections}]; reads only

`paper` does not call SAM. Crops run only for the pages named in `crops`.
"""

import contextvars
import json
import os
import threading
import time
from pathlib import Path

import modal

from rrm.demo_guard import add_error_json, check, cors_kwargs, failure
from rrm.demo_warm import scaledown_window
from rrm.features import core_mode, features_mode
from rrm.panorama import docs_for, parse_request, run as run_panorama
from rrm.search.qcache import CACHE_DIR, apply_status_cache, load_entry, save_entry, status_map
from rrm.reader.files import resolve_figure, resolve_source_pdf
from rrm.reader.rights import gate_ask, gate_file, gate_paper_response, gate_status_row, load_map, map_path, map_size, warn_map

import rrm.reader.fetch as _fetch
from rrm.reader.fetch import ARXIV, arxiv_index_at, arxiv_pdf, arxiv_slot_start, reader_identity
from rrm.reader.ocr import (
    heal_cached_ocr_figures,
    merge_ocr_parts,
    page_spans,
    pdf_page_count,
    place_ocr_figures,
    run_chunk,
    slice_pdf,
)
from rrm.reader.pipeline import (
    load_meta,
    load_paper,
    make_stub,
    mark_queued,
    paper_has_text,
    prefer_stub,
    seed_stub_from_cache,
    status_reason,
    parse_corpus,
    save_meta,
    save_paper,
    worker_alive,
)
from rrm.reader.queue import forget as forget_job
from rrm.reader.queue import note as note_job
from rrm.search.prefetch import load_burst_top, missing_status
from rrm.reader.queue import release as release_job
from rrm.reader.ocr_budget import claim_ocr_slot, ocr_gpu_from_env, ocr_limit_from_env
from rrm.reader.sam import api_key, fill_pdf_crops, key_blocks_crops, parse_pages, sam_enabled, segment_pages, segmented_pages

DATA = os.environ.get("RRM_DATA", "/data")  # RRM-100: local runs point it at a copy
PAPERS = Path(DATA) / "papers"
_fetch.S2_CACHE_DIR = PAPERS
DISPLAY = Path(DATA) / "2026-10-20" / "index" / "display.parquet"
# modal.com/pricing, fetched 2026-10-28, preemptible list price. GPU tasks also bill CPU and memory.
CPU_USD_PER_CORE_S = 0.0000131
L4_USD_PER_S = 0.000222
SAM_USD_PER_IMAGE = 0.0025

cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("nodejs", "npm", "ghostscript", "ca-certificates")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("pymupdf", "requests", "pyarrow", "numpy", "faiss-cpu", "fastapi[standard]", "transformers", "adapters")
    .run_commands(
        "npm install --prefix /opt/katex katex@0.19.1",
        "python -c \"from transformers import AutoTokenizer; from adapters import AutoAdapterModel; "
        "AutoTokenizer.from_pretrained('allenai/specter2_base'); "
        "m = AutoAdapterModel.from_pretrained('allenai/specter2_base'); "
        "m.load_adapter('allenai/specter2_adhoc_query', source='hf', load_as='adhoc_query', set_active=True); "
        "m.load_adapter('allenai/specter2', source='hf', load_as='proximity'); "
        "m.eval()\"",
    )
    .env({"NODE_PATH": "/opt/katex/node_modules", "RRM_PHRASE_VECTORS": "1"})
    .add_local_python_source("rrm")
)
# MinerU 2.5 is a 1.2B VLM. L4 (24 GB) is the smallest Modal GPU that fits it.
# vllm makes vlm-auto-engine pick the vLLM engine (MinerU 2.7, Linux). Without
# it the same backend falls back to transformers, ~20 s/page (QA 2026-10-29).
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "libgl1", "libglib2.0-0", "ca-certificates")
    # mineru 2.7.6 pins vllm<0.12 via its [vllm] extra; an unpinned vllm resolves to 0.3x
    # and its own torch. Let vllm choose torch (no separate cu124 torch install).
    .uv_pip_install("pymupdf", "mineru[core,vllm]>=2.5,<3")  # pip backtracks for 10+ min here; uv resolves in seconds
    .add_local_python_source("rrm")
)

# RRM-100: experiments deploy under another name; the demo app stays rrm-reader.
app = modal.App(os.environ.get("RRM_READER_APP", "rrm-reader"))
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
if os.environ.get("RRM_READER_RO") == "1":
    # RRM-100: an experiment reader reads the shared volume and never writes to it.
    vol = modal.Volume.from_name("rrm-data").read_only()
if modal.is_local():
    secret = modal.Secret.from_dict({
        "MODEL_API_KEY": os.environ.get("MODEL_API_KEY", ""),
        "S2_API_KEY": os.environ.get("S2_API_KEY", ""),
        "RRM_DEMO_TOKEN": os.environ.get("RRM_DEMO_TOKEN", ""),
        "RRM_FEATURES": os.environ.get("RRM_FEATURES", "core"),
        "RRM_PANORAMA_MODE": os.environ.get("RRM_PANORAMA_MODE", "sim"),
        # off/0/false/no: /crops does not call SAM. Default on. Read at deploy.
        "RRM_SAM": os.environ.get("RRM_SAM", "on"),
        # Empty keeps the 40s default in rrm.panorama (under the UI's 45s abort).
        "RRM_PANORAMA_TIMEOUT": os.environ.get("RRM_PANORAMA_TIMEOUT", ""),
        # Empty unless this deploy sets it. Unset = no OCR cap.
        "RRM_OCR_MAX": os.environ.get("RRM_OCR_MAX", ""),
        # RRM-49: 0 vuelve a la caja de una sola afirmación (RRM-43).
        "RRM_CLAIMS": os.environ.get("RRM_CLAIMS", ""),
        # Vacío: el lector no abre /data/passages. 1 consulta el índice por embedding.
        "RRM_PASSAGES": os.environ.get("RRM_PASSAGES", ""),
        # Demo personal: off muestra el texto completo. on/1 vuelve a la compuerta.
        "RRM_LICENSE_GATE": os.environ.get("RRM_LICENSE_GATE", "off"),
        # Vacío: /ask y /notes no adjuntan el prompt. Una ruta guarda el crudo en la respuesta.
        "RRM_RAW_DUMP": os.environ.get("RRM_RAW_DUMP", ""),
        # RRM-99: análisis v2 de notas (vacío = notes.py de siempre).
        "RRM_ANALYSIS": os.environ.get("RRM_ANALYSIS", ""),
        "RRM_ANALYSIS_CAND": os.environ.get("RRM_ANALYSIS_CAND", ""),
        # RRM-100: 0 vuelve a la caja anterior; PASSAGES=0 arma la hoja sin otros papers.
        "RRM_EXPLAIN": os.environ.get("RRM_EXPLAIN", ""),
        "RRM_EXPLAIN_PASSAGES": os.environ.get("RRM_EXPLAIN_PASSAGES", ""),
        "RRM_EXPLAIN_EFFORT": os.environ.get("RRM_EXPLAIN_EFFORT", ""),
        "RRM_EXPLAIN_DIR": os.environ.get("RRM_EXPLAIN_DIR", ""),
        "RRM_READER_RO": os.environ.get("RRM_READER_RO", ""),
        "RRM_READER_APP": os.environ.get("RRM_READER_APP", ""),
        "RRM_EXTRA_ORIGINS": os.environ.get("RRM_EXTRA_ORIGINS", ""),
    })
else:
    secret = modal.Secret.from_dict({})

_gate = None
_queue = None
_JOB = contextvars.ContextVar("rrm_reader_job", default=None)


def _queue_dict():
    global _queue
    if _queue is None:
        _queue = modal.Dict.from_name("rrm-reader-queue", create_if_missing=True)
    return _queue


def _blank_state():
    return {"order": [], "hot": [], "turn": None}


def _load_state(gate):
    try:
        state = gate["state"]
    except KeyError:
        state = None
    if not isinstance(state, dict):
        state = _blank_state()
    state.setdefault("order", [])
    state.setdefault("hot", [])
    state.setdefault("turn", None)
    return state


def _mutate(fn):
    """Serialize queue edits. A lock older than 20 s is dropped (the holder died)."""
    gate = _queue_dict()
    for _ in range(80):
        now = time.time()
        if gate.put("lock", now, skip_if_exists=True):
            try:
                state = _load_state(gate)
                result = fn(state)
                gate["state"] = {
                    "order": list(state.get("order") or []),
                    "hot": list(state.get("hot") or []),
                    "turn": state.get("turn"),
                }
                return result
            finally:
                try:
                    gate.pop("lock")
                except KeyError:
                    pass
        try:
            held = gate["lock"]
        except KeyError:
            held = None
        if isinstance(held, (int, float)) and now - held > 20:
            try:
                gate.pop("lock")
            except KeyError:
                pass
            continue
        time.sleep(0.05)
    raise TimeoutError("reader queue lock")


def _steal_stale(state):
    turn = state.get("turn")
    if not isinstance(turn, dict):
        return
    if time.time() - float(turn.get("ts") or 0) < 120:
        return
    dead = turn.get("cid")
    state["order"], state["hot"] = forget_job(state["order"], state["hot"], dead)
    state["turn"] = None


def prioritize(corpusid: int):
    cid = int(corpusid)

    def edit(state):
        state["order"], state["hot"] = note_job(state["order"], state["hot"], cid, front=True)

    _mutate(edit)


def _forget(corpusid: int):
    cid = int(corpusid)

    def edit(state):
        state["order"], state["hot"] = forget_job(state["order"], state["hot"], cid)
        turn = state.get("turn")
        if isinstance(turn, dict) and int(turn.get("cid") or -1) == cid:
            state["turn"] = None

    try:
        _mutate(edit)
    except Exception:
        return


def _shared_arxiv_wait():
    """One clock for every container: 4 requests in a 1 s burst, then a 1 s sleep."""
    global _gate
    if _gate is None:
        _gate = modal.Dict.from_name("rrm-arxiv-gate", create_if_missing=True)

    def rate_wait():
        # Slot only. The caller reads the body after wait() returns, so a slow transfer
        # does not hold the next paper's harvest slot.
        now = time.time()
        slot = arxiv_index_at(now)
        for _ in range(400):
            if _gate.put(f"slot:{slot}", 1, skip_if_exists=True):
                break
            slot += 1
        delay = arxiv_slot_start(slot) - time.time()
        if delay > 0:
            time.sleep(delay)

    def wait():
        cid = _JOB.get()
        if cid is None:
            rate_wait()
            return
        cid = int(cid)
        while True:
            def claim(state, cid=cid):
                _steal_stale(state)
                state["order"], state["hot"] = note_job(state["order"], state["hot"], cid, front=False)
                turn = state.get("turn")
                now = time.time()
                if isinstance(turn, dict) and int(turn.get("cid") or -1) != cid and now - float(turn.get("ts") or 0) < 120:
                    return False
                if not state["order"] or int(state["order"][0]) != cid:
                    return False
                state["turn"] = {"cid": cid, "ts": now}
                return True

            if _mutate(claim):
                try:
                    rate_wait()
                finally:
                    def done(state, cid=cid):
                        state["order"], state["hot"] = release_job(state["order"], state["hot"], cid)
                        turn = state.get("turn")
                        if isinstance(turn, dict) and int(turn.get("cid") or -1) == cid:
                            state["turn"] = None

                    try:
                        _mutate(done)
                    except Exception:
                        pass
                return
            time.sleep(0.05)

    ARXIV.wait = wait


def _chunk_rows(results: list) -> list:
    return [
        {
            "start": row.get("start"),
            "end": row.get("end"),
            "seconds": row.get("seconds"),
            "engine": row.get("engine") or "unknown",
            "ok": bool(row.get("ok")) and not row.get("failed"),
        }
        for row in results
    ]


def _ocr(pdf, work):
    """One container per chunk (spawn, not map). Merge blocks in page order.

    `seconds` is wall time (what the reader waits). `gpu_s` is the sum, which is what Modal bills.
    A failed chunk is a raw block; the other pages still come back. QA 2026-10-29: `.map` ran
    all four chunks inside one A10G, and the last one hung past 13 min.
    """
    pdf = Path(pdf)
    work = Path(work)
    n = pdf_page_count(pdf) or 0
    spans = page_spans(n)
    if not spans:
        return {"blocks": [], "seconds": 0.0, "gpu_s": 0.0, "page_count": 0, "chunks": []}
    limit = ocr_limit_from_env()
    if limit is not None:
        cid = _JOB.get()
        if cid is None or not claim_ocr_slot(_queue_dict(), limit, cid):
            return {
                "blocks": [], "seconds": 0.0, "gpu_s": 0.0, "page_count": n,
                "chunks": [], "skipped": "cap",
            }
    vol.commit()
    jobs = []
    for start, end in spans:
        part = work / f"part_{start}"
        slice_pdf(pdf, part / "in.pdf", start, end)
        jobs.append((str(part / "in.pdf"), str(part / "out"), start, end))
    vol.commit()
    t = time.time()
    calls = [ocr_one.spawn(path, out, start, end) for path, out, start, end in jobs]
    results = []
    for call, (_path, _out, start, end) in zip(calls, jobs):
        try:
            row = call.get()
        except Exception as err:
            row = {
                "start": start, "end": end, "failed": True, "ok": False, "blocks": [],
                "seconds": 0.0, "engine": "unknown", "error": str(err)[:300],
            }
        row.setdefault("start", start)
        row.setdefault("end", end)
        results.append(row)
    wall = time.time() - t
    chunks = _chunk_rows(results)
    usable = [row for row in results if row.get("ok") and not row.get("failed") and row.get("blocks")]
    if not usable:
        err = RuntimeError("all ocr chunks failed: " + "; ".join(
            str(row.get("error") or "failed")[:120] for row in results
        ))
        err.chunks = chunks
        raise err
    # Chunk images land under the MinerU out dir. /file only serves papers/{id}/figures.
    _reload()
    figures = Path(work).parent / "figures"
    for row, (_path, out, _start, _end) in zip(results, jobs):
        place_ocr_figures(row.get("blocks") or [], [out], figures)
    blocks = merge_ocr_parts(results)
    gpu_s = sum(float(row.get("seconds") or 0) for row in results)
    pages = sum(int(row.get("page_count") or 0) for row in results) or n
    return {
        "blocks": blocks,
        "seconds": round(wall, 3),
        "gpu_s": round(gpu_s, 3),
        "page_count": pages,
        "chunks": chunks,
    }


def _run(corpusid: int) -> dict:
    token = _JOB.set(int(corpusid))
    try:
        _reload()
        _shared_arxiv_wait()
        return parse_corpus(int(corpusid), PAPERS, DISPLAY, sam=False, ocr=_ocr, commit=vol.commit)
    finally:
        _forget(int(corpusid))
        _JOB.reset(token)


# L4 first; A10G (24 GB) when L4 has no capacity (seen 2026-10-29: 10+ min queue).
# max_inputs=1 and max_containers=8: each chunk is its own container. No min_containers.
# Function timeout bounds a hung container; run_chunk itself stops an attempt at 180s and retries once.
@app.function(
    image=gpu_image, gpu=ocr_gpu_from_env(), volumes={DATA: vol},
    timeout=400, memory=16384, cpu=2, max_containers=8,
)
@modal.concurrent(max_inputs=1)
def ocr_one(pdf: str, out: str, start: int = 0, end: int = 0) -> dict:
    _reload()
    result = run_chunk(Path(pdf), Path(out), int(start), int(end) or None)
    result["page_count"] = pdf_page_count(Path(pdf))
    vol.commit()
    return result


@app.function(image=cpu_image, volumes={DATA: vol}, cpu=2, memory=8192, timeout=900, secrets=[secret])
def parse_one(corpusid: int, sam: bool = False) -> dict:
    del sam
    return _run(int(corpusid))


def _view(folder: Path, meta: dict | None):
    paper = load_paper(folder)
    if not meta:
        meta = load_meta(folder)
    if not meta:
        return None
    return {
        "status": meta.get("status"),
        "meta": meta,
        "paper": paper,
    }


def _write_stub(folder: Path, corpusid: int):
    """Volume display row, plus one Graph API call when authors or abstract are missing."""
    current = load_paper(folder)
    if current and (current.get("full") or (current.get("blocks") and current.get("stage") not in (None, "stub", "ocr"))):
        return current
    try:
        info = reader_identity(int(corpusid), DISPLAY, remote=True, refs=False, shards=False)
    except Exception:
        info = {"corpusid": int(corpusid)}
    paper = prefer_stub(current, make_stub(info))
    if current and len(current.get("blocks") or []) > len(paper.get("blocks") or []):
        return current
    meta = load_meta(folder) or {}
    meta.update({
        "corpusid": int(corpusid),
        "status": meta.get("status") if meta.get("status") in ("queued", "parsing") else "parsing",
        "stage": meta.get("stage") or "stub",
        "stages": paper["stages"],
        "title": paper.get("title") or "",
        "tldr": paper.get("tldr") or "",
        "arxiv": info.get("arxiv") or meta.get("arxiv") or "",
        "reason": meta.get("reason"),
        "source": meta.get("source"),
        "timings": meta.get("timings") or {},
        "started": meta.get("started") or time.time(),
    })
    if meta.get("first_content_s") is None:
        meta["first_content_s"] = 0.0
    save_paper(folder, paper)
    save_meta(folder, meta)
    return paper


def _prepare_ids(ids, front=False) -> dict:
    _reload()
    _shared_arxiv_wait()
    try:
        _fetch.s2_batch(ids)  # one Graph API request for the whole burst
    except Exception:
        pass
    vol.commit()  # parse_one containers must see s2.json before they resolve
    rows = []
    ordered = []
    for raw in ids or []:
        try:
            ordered.append(int(raw))
        except (TypeError, ValueError):
            continue
    if front:
        for cid in reversed(ordered):
            try:
                prioritize(cid)
            except Exception:
                pass
    for cid in ordered:
        status = mark_queued(PAPERS / str(cid), cid)
        if status == "queued":
            seed_stub_from_cache(PAPERS / str(cid), cid)
            parse_one.spawn(cid, False)
        rows.append({"id": cid, "status": status})
    vol.commit()
    return {"papers": rows}


# A web endpoint cannot be .spawn()ed from another app (InvalidError), so /burst spawns this.
@app.function(image=cpu_image, volumes={DATA: vol}, timeout=60, secrets=[secret])
def prefetch(ids: list) -> dict:
    return _prepare_ids(ids)


def _heal_figures(folder: Path, paper):
    """One-time copy for OCR papers cached before figures lived in figures/."""
    try:
        if heal_cached_ocr_figures(folder, paper):
            vol.commit()
    except Exception:
        return


def _oa_url(corpusid, paper, meta):
    for src in (paper or {}, meta or {}):
        url = src.get("oa_pdf") or src.get("oaPdf") or ""
        if isinstance(url, str) and url.startswith("http"):
            return url
    try:
        from rrm.reader.fetch import _s2_cache

        path = _s2_cache(int(corpusid))
        if path is None or not path.is_file():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        oa = data.get("openAccessPdf") or {}
        return (oa.get("url") if isinstance(oa, dict) else "") or ""
    except Exception:
        return ""


def _attach_cites(paper):
    """Resuelve claves BibTeX con el grafo local. No llama a Semantic Scholar."""
    if not isinstance(paper, dict) or isinstance(paper.get("citeMap"), dict):
        return paper
    paper = dict(paper)
    try:
        from rrm.reader.cites import bind_cites
        from rrm.reader.fetch import graph_reference_map

        graph = graph_reference_map(DISPLAY.parent, int(paper.get("corpusid") or 0))
    except Exception:
        graph = {}
    paper["graphRefs"] = graph or paper.get("graphRefs") or {}
    paper["citeMap"] = bind_cites(paper.get("refs") or {}, paper["graphRefs"])
    return paper


def _with_pdf(folder: Path, body: dict, cites: bool = True) -> dict:
    meta = dict(body.get("meta") or {})
    paper = body.get("paper")
    meta["pdf"] = (Path(folder) / "source.pdf").is_file()
    meta["oa_pdf"] = _oa_url(folder.name, paper, meta)
    meta["arxiv"] = meta.get("arxiv") or (paper or {}).get("arxivId") or ""
    out = dict(body)
    if isinstance(paper, dict):
        if cites:
            out["paper"] = _attach_cites(paper)
        elif not isinstance(paper.get("citeMap"), dict):
            out["cites"] = "pending"
    out["meta"] = meta
    return out


def _ready_local(folder: Path):
    """Paper ya visible en este contenedor, sin recargar el volumen."""
    paper = load_paper(folder)
    if not isinstance(paper, dict) or not (paper.get("title") or paper.get("blocks")):
        return None
    meta = load_meta(folder) or {}
    return _with_pdf(
        folder,
        {"status": meta.get("status"), "meta": meta, "paper": paper, "cached": True},
        cites=False,
    )


def _ensure_folder(folder):
    """mkdir that survives a concurrent vol.reload (RRM-46: 3 of 9 /paper hit
    PermissionError or FileNotFoundError while /data was being remounted)."""
    # RRM-47 re-check: /data itself can vanish for >1 s mid-reload (EPERM on
    # /data/papers), so wait up to ~4 s before giving up.
    for attempt in range(8):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            return
        except OSError:
            if folder.is_dir():
                return
            if attempt == 7:
                raise
            time.sleep(0.5)


def _reload():
    """RRM-47: vol.reload() raises "open files preventing the operation" while
    an index file (display.parquet) is open in this container; that turned
    /paper and /prepare into 500s. A stale view is fine for one call."""
    try:
        vol.reload()
    except Exception as err:
        if "open files" not in str(err):
            raise
        print(f"vol.reload omitido: {type(err).__name__}", flush=True)


def _retry_os(fn, *args, **kw):
    """RRM-47: vol.reload() can remount /data under a running call; one retry."""
    try:
        return fn(*args, **kw)
    except OSError:
        time.sleep(0.5)
        return fn(*args, **kw)


def read_paper(id: str, cites: bool = False):
    """Devuelve el paper que ya está. Las citas llegan en una segunda lectura.

    Sin `cites`, no recarga el volumen ni resuelve el grafo si el archivo ya
    está en este contenedor. Con `cites`, resuelve los títulos y puede recargar.
    """
    cid = int(id)
    folder = PAPERS / str(cid)
    _ensure_folder(folder)
    if not cites:
        local = _ready_local(folder)
        if local is not None:
            _kick_phrases(cid)
            return local
    _reload()
    _shared_arxiv_wait()
    meta = load_meta(folder)
    if meta and meta.get("status") in ("done", "abstract_only", "failed"):
        paper = load_paper(folder)
        _heal_figures(folder, paper)
        _kick_phrases(cid)
        return _with_pdf(folder, {"status": meta["status"], "meta": meta, "paper": paper, "cached": True}, cites=cites)
    try:
        prioritize(cid)
    except Exception:
        pass
    if not worker_alive(meta):
        mark_queued(folder, cid)
        parse_one.spawn(cid, False)
    paper_obj = load_paper(folder)
    if paper_obj is None or paper_obj.get("stage") in (None, "stub"):
        paper_obj = _write_stub(folder, cid)
        vol.commit()
    else:
        _heal_figures(folder, paper_obj)
    meta = load_meta(folder) or {}
    _kick_phrases(cid)
    return _with_pdf(folder, {"status": meta.get("status"), "meta": meta, "paper": paper_obj, "cached": False}, cites=cites)


@app.function(image=cpu_image, volumes={DATA: vol}, cpu=2, memory=4096, timeout=600, secrets=[secret])
def crops_for(corpusid: int, pages: list):
    if not sam_enabled():
        return {"crops": [], "error": "RRM_SAM=off", "images": 0}
    token = _JOB.set(int(corpusid))
    try:
        _reload()
        _shared_arxiv_wait()
        try:
            prioritize(int(corpusid))
        except Exception:
            pass
        folder = PAPERS / str(int(corpusid))
        folder.mkdir(parents=True, exist_ok=True)
        pdf = folder / "source.pdf"
        meta = load_meta(folder) or {}
        if not pdf.is_file() and meta.get("arxiv"):
            try:
                pdf.write_bytes(arxiv_pdf(meta["arxiv"]))
                vol.commit()
            except Exception as err:
                meta["sam_error"] = f"pdf download failed: {err}"
                save_meta(folder, meta)
                vol.commit()
                return {"crops": [], "error": meta["sam_error"], "images": 0}
        out = segment_pages(pdf, folder / "crops", list(pages or []))
        meta = load_meta(folder) or meta
        done_pages = set(int(p) for p in (pages or []))
        meta["crops_inflight"] = [p for p in (meta.get("crops_inflight") or []) if int(p) not in done_pages]
        stages = dict(meta.get("stages") or {})
        stages["crops"] = "done" if not out.get("error") else "failed"
        meta["stages"] = stages
        meta["sam_images"] = out.get("images")
        meta["sam_error"] = out.get("error")
        meta["sam_cost_usd"] = out.get("cost_usd")
        save_meta(folder, meta)
        if (folder / "paper.json").is_file():
            paper_obj = load_paper(folder) or {}
            paper_obj["stages"] = stages
            save_paper(folder, paper_obj)
        vol.commit()
        return out
    finally:
        _JOB.reset(token)


def read_crops(id: str, pages: str = ""):
    """SAM for the pages in view. Returns the crops already on disk and keeps working in the background."""
    if core_mode():
        cid = int(id) if str(id).isdigit() else id
        return {"id": cid, "status": "skipped", "pages": [], "crops": [], "error": "core", "images": 0, "skipped": True}
    _reload()
    cid = int(id)
    wanted = parse_pages(pages)
    folder = PAPERS / str(cid)
    index_path = folder / "crops" / "index.json"
    index = {"crops": [], "error": None, "images": 0}
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            index = {"crops": [], "error": None, "images": 0}
    if not sam_enabled():
        rows = index.get("crops") or []
        if wanted:
            rows = [row for row in rows if row.get("page") in set(wanted)]
        return {
            "id": cid,
            "status": "skipped",
            "pages": wanted,
            "crops": rows,
            "error": None,
            "images": index.get("images") or 0,
        }
    meta = load_meta(folder) or {}
    inflight = {int(p) for p in (meta.get("crops_inflight") or [])}
    status = "done"
    # A missing key from an older run is not permanent. Retry when the key is set.
    if key_blocks_crops(index.get("error"), api_key()):
        status = "skipped"
        fresh = []
    else:
        have = segmented_pages(index, api_key())
        fresh = [p for p in wanted if p not in have]
    if fresh:
        status = "running"
        todo = [p for p in fresh if p not in inflight]
        if todo:
            meta["crops_inflight"] = sorted(inflight | set(todo))
            try:
                save_meta(folder, meta)
                vol.commit()
                crops_for.spawn(cid, todo)
            except Exception as err:
                status = "failed"
                index["error"] = str(err)[:300]
    # Pages SAM already closed with zero boxes stay empty until something fills
    # them. The PDF boxes do that here, with no new SAM call. Pages just spawned
    # are left to crops_for, which applies the same fallback after SAM.
    busy = set(inflight)
    if fresh:
        busy |= {p for p in fresh if p not in inflight}
    idle = [p for p in wanted if p not in busy]
    pdf = folder / "source.pdf"
    if idle and pdf.is_file():
        try:
            index, wrote = fill_pdf_crops(pdf, folder / "crops", idle)
            if wrote:
                vol.commit()
        except Exception:
            pass
    rows = index.get("crops") or []
    if wanted:
        rows = [row for row in rows if row.get("page") in wanted]
    error = index.get("error")
    if error == "no MODEL_API_KEY" and status != "skipped":
        error = None
    return {
        "id": cid,
        "status": status,
        "pages": wanted,
        "crops": rows,
        "error": error,
        "images": index.get("images") or 0,
    }


def _cache_root() -> Path:
    return Path(DATA) / CACHE_DIR


_phrase_jobs = set()
_phrase_guard = threading.Lock()
# reload() tira archivos sin commit. Escritura, commit y reload comparten este candado.
_phrase_lock = threading.Lock()


def prepare_paper_phrases(cid) -> dict:
    """Frases y vectores de un paper, commiteados antes de volver."""
    from rrm.reader.similar import commit_phrases

    if os.environ.get("RRM_PHRASE_VECTORS") != "1":
        return {"id": int(cid), "ready": False, "rows": 0, "had_phrases": False, "had_vectors": False, "seconds": 0.0, "error": "off"}
    folder = PAPERS / str(int(cid))
    folder.mkdir(parents=True, exist_ok=True)
    with _phrase_lock:
        out = commit_phrases(folder, vol.reload, vol.commit)
    out["id"] = int(cid)
    return out


def _kick_explain(cid):
    """RRM-100: hoja de respuestas de cada sección, en un hilo, al abrir el paper."""
    try:
        from rrm.reader.explain import service as explain
        from rrm.reader.similar import specter_encode

        explain.kick(int(cid), PAPERS / str(int(cid)), load_paper, encode=specter_encode,
                     lock=_phrase_lock, commit=vol.commit, log=lambda msg: print(msg, flush=True))
    except Exception as err:
        print(f"explain kick: {type(err).__name__}", flush=True)


def _kick_phrases(cid):
    """Al abrir, este paper va primero. El hilo usa el mismo candado que /ask."""
    _kick_explain(cid)
    if os.environ.get("RRM_PHRASE_VECTORS") != "1":
        return

    def work():
        try:
            prepare_paper_phrases(cid)
        except Exception:
            return

    threading.Thread(target=work, name="rrm-phrase-open", daemon=True).start()


def _needs_phrases(folder):
    """Un paper ya parseado sin frases: se reconstruyen del paper.json, sin volver a bajar."""
    from rrm.reader.phrases import read_phrases, text_rows
    from rrm.reader.pipeline import load_paper

    if text_rows(read_phrases(folder)):
        return False
    try:
        paper = load_paper(folder)
    except (OSError, ValueError):
        return False
    return isinstance(paper, dict) and bool(paper.get("blocks"))


def _phrase_vectors_missing(ids):
    from rrm.reader.phrases import read_phrases
    from rrm.reader.similar import read_vectors, text_rows

    pending = []
    for raw in ids or []:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        folder = PAPERS / str(cid)
        rows = text_rows(read_phrases(folder))
        if rows and read_vectors(folder, len(rows)) is None:
            pending.append(cid)
        elif not rows and _needs_phrases(folder):
            pending.append(cid)
    return pending


def _ensure_phrase_vectors(ids):
    """Encode fuera del request. /ask solo lee el .npy."""
    if os.environ.get("RRM_PHRASE_VECTORS") != "1":
        return
    try:
        pending = _phrase_vectors_missing(ids)
    except Exception:
        return
    if not pending:
        return
    with _phrase_guard:
        todo = [cid for cid in pending if cid not in _phrase_jobs]
        _phrase_jobs.update(todo)
    if not todo:
        return

    def work():
        for cid in todo:
            try:
                prepare_paper_phrases(cid)
            except Exception:
                pass
            finally:
                with _phrase_guard:
                    _phrase_jobs.discard(cid)

    threading.Thread(target=work, name="rrm-phrase-vectors", daemon=True).start()


def _ask_body(ids, text, stage, focus=None):
    from rrm.search.querylang import PREPARING
    from rrm.reader.phrases import store_progress
    from rrm.reader.similar import load_aligned, phrase_ids
    from rrm.reader.verify import answer

    # Con focus el paper abierto ya se preparó y se commiteó. No encodar los otros diez aquí.
    if not focus:
        _ensure_phrase_vectors(ids)
    store = store_progress(PAPERS, ids)
    if not str(text or "").strip():
        return {"extracts": [], "papers": 0, "line": "", "empty": True, "matched": 0, "parts": {}, "note": "", "store": store}
    rows, vectors, missing = load_aligned(PAPERS, phrase_ids(ids, focus))
    if vectors is None:
        note = PREPARING if missing else "No hay frases guardadas de estos papers."
        return {"extracts": [], "papers": 0, "line": "", "empty": True, "matched": 0, "parts": {}, "note": note, "store": store}
    from rrm.reader.similar import specter_encode

    def encode(texts):
        return specter_encode(texts)

    return answer(rows, text, ids=ids, root=PAPERS, encode=encode, vectors=vectors, stage=stage or "todo")


def _explain_body(focus, section, text, stage):
    """RRM-100: /ask de una sección del paper abierto. None si el paper no tiene texto."""
    from rrm.reader.explain import service as explain
    from rrm.reader.similar import specter_encode

    folder = PAPERS / str(int(focus))
    paper = load_paper(folder)
    if not isinstance(paper, dict) or not paper.get("blocks"):
        return None
    _kick_explain(int(focus))
    return explain.ask(folder, paper, section, text, stage=stage, encode=specter_encode)


def read_status(ids: str = "", pending=None, question: str = ""):
    try:
        _reload()
    except Exception:
        pass
    if pending is None:
        try:
            pending = load_burst_top()
        except Exception:
            pending = None
    rows = []
    asked = []
    for raw in (ids or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        asked.append(cid)
        try:
            meta = load_meta(PAPERS / str(cid))
        except Exception:
            meta = None
        if not meta:
            # Top-10 ids are noted before the volume commit lands. First poll
            # still sees queued; anything else with no meta.json stays missing.
            rows.append({"id": cid, "status": missing_status(cid, pending)})
        else:
            rows.append({
                "id": cid,
                "status": meta.get("status"),
                "stage": meta.get("stage"),
                "stages": meta.get("stages"),
                "reason": status_reason(meta),
                "source": meta.get("source"),
                "upgraded_from": meta.get("upgraded_from"),
                "first_content_s": meta.get("first_content_s"),
                "sections_s": meta.get("sections_s"),
                "full_s": meta.get("full_s"),
                "ocr_gpu_s": meta.get("ocr_gpu_s"),
                "ocr_invoked_at": meta.get("ocr_invoked_at"),
                "text": paper_has_text(meta),
            })
    _ensure_phrase_vectors(asked)
    saved = {}
    if question:
        try:
            entry = load_entry(_cache_root(), question) or {}
            saved = entry.get("papers") or {}
        except Exception:
            saved = {}
        rows = apply_status_cache(rows, saved)
        fresh = status_map(rows)
        if fresh:
            def persist():
                try:
                    save_entry(_cache_root(), question, papers=fresh)
                    vol.commit()
                except Exception:
                    return

            threading.Thread(target=persist, name="rrm-status-cache", daemon=True).start()
    return {"papers": rows}


_FILE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
}


# Same demo flag as the burst class. GPU functions are not kept warm.
_api_fn = dict(image=cpu_image, volumes={DATA: vol}, timeout=90, cpu=2, memory=8192, secrets=[secret])
if scaledown_window() is not None:
    _api_fn["scaledown_window"] = scaledown_window()


# One HTTP input at a time made each figure wait behind /status and /paper.
# max_inputs stays small: these handlers share the volume.
@app.function(**_api_fn)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def api():
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, Response

    web = FastAPI()
    _license_path = map_path()
    warn_map(_license_path, load_map(_license_path))
    if os.environ.get("RRM_PHRASE_VECTORS") == "1":
        def _warm_phrases():
            try:
                from rrm.reader.similar import specter_encode
                specter_encode(["warm"])
            except Exception:
                return

        threading.Thread(target=_warm_phrases, name="rrm-phrase-encoder", daemon=True).start()
    add_error_json(web)
    web.add_middleware(CORSMiddleware, **cors_kwargs())

    def gate(request: Request, allow_query: bool):
        header = request.headers.get("x-rrm-demo")
        query = request.query_params.get("k") if allow_query else None
        origin = request.headers.get("origin")
        code = check(header, query, origin)
        if code == 401:
            return JSONResponse({"error": failure(header, query) or "mismatch"}, status_code=401)
        if code:
            return Response(status_code=code)
        return None

    @web.get("/paper")
    def route_paper(request: Request, id: str, cites: int = 0):
        denied = gate(request, True)
        if denied:
            return denied
        return gate_paper_response(_retry_os(read_paper, id, cites=bool(cites)), load_map(map_path()))

    @web.get("/warm")
    def route_warm(request: Request):
        denied = gate(request, True)
        if denied:
            return denied
        return {"ready": True, "features": features_mode(), "licenses": map_size(load_map(map_path()))}

    @web.get("/status")
    def route_status(request: Request, ids: str = "", q: str = ""):
        denied = gate(request, True)
        if denied:
            return denied
        try:
            body = read_status(ids, question=q)
        except Exception:
            return {"papers": []}
        rows = body.get("papers") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            return body
        m = load_map(map_path())
        body = dict(body)
        body["papers"] = [gate_status_row(row, m) if isinstance(row, dict) else row for row in rows]
        return body

    @web.post("/ask")
    async def route_ask(request: Request):
        """Busca en el almacén. Meta entra solo aquí, con las frases ya elegidas."""
        denied = gate(request, False)
        if denied:
            return denied
        item = await request.json()
        item = item or {}
        focus = item.get("focus")
        section = str(item.get("section") or "")
        if str(focus or "").isdigit() and section and str(item.get("text") or "").strip():
            from rrm.reader.explain import service as explain

            if explain.explain_on():
                try:
                    body = _explain_body(focus, section, item.get("text") or "", item.get("stage") or "revisar")
                except Exception as err:
                    from rrm.reader.verify import ask_error_text
                    return JSONResponse({"error": ask_error_text(err)}, status_code=500)
                if body is not None:
                    from rrm.reader.verify import ask_http
                    code, payload = ask_http(body, item.get("stage") or "")
                    if code != 200:
                        return JSONResponse(payload, status_code=code)
                    return gate_ask(payload, load_map(map_path()))
        prep = None
        if focus not in (None, ""):
            try:
                prep = prepare_paper_phrases(focus)
            except Exception:
                prep = None
        else:
            with _phrase_lock:
                try:
                    _reload()
                except Exception:
                    pass
        try:
            body = _ask_body(item.get("ids") or [], item.get("text") or "", item.get("stage") or "todo", focus=focus or None)
        except Exception as err:
            from rrm.reader.verify import ask_error_text
            return JSONResponse({"error": ask_error_text(err)}, status_code=500)
        from rrm.reader.verify import ask_http
        code, payload = ask_http(body, item.get("stage") or "")
        if code != 200:
            return JSONResponse(payload, status_code=code)
        if prep is not None:
            payload["phrase_prep"] = prep
        return gate_ask(payload, load_map(map_path()))

    @web.post("/notes")
    async def route_notes(request: Request):
        """Una nota por paper. No escribe la clave ni el tex en el log."""
        denied = gate(request, False)
        if denied:
            return denied
        item = await request.json()
        item = item or {}
        empty = {"notes": [], "artifacts": [], "usage": {"model": "", "license": "", "cost_usd": 0.0}}
        try:
            cid = int(item.get("id"))
        except (TypeError, ValueError):
            return empty
        try:
            folder = PAPERS / str(cid)
            paper = load_paper(folder) or {}
            if paper.get("corpusid") is None:
                paper = dict(paper)
                paper["corpusid"] = cid
            from rrm.reader.metacall import raw_dump_on, take_raw
            from rrm.reader.notes import answer_notes
            from rrm.reader.phrases import read_phrases

            if raw_dump_on():
                take_raw()
            from rrm.reader.analysis.run import cached_or_kick, enabled

            if enabled() and paper.get("blocks"):
                try:
                    # RRM-99: caché v2 al instante; si no hay, se calcula en un hilo y aquí sigue notes.py.
                    got = cached_or_kick(paper, commit=getattr(vol, "commit", None))
                    if got:
                        return got
                except Exception:
                    pass
            body = answer_notes(paper, read_phrases(folder))
            if raw_dump_on() and isinstance(body, dict):
                body = dict(body)
                body["raw"] = take_raw()
            return body
        except Exception:
            return empty

    @web.post("/phrases")
    async def route_phrases(request: Request):
        """Un paper abierto: frases y vectores ahora, y commit antes de responder."""
        denied = gate(request, False)
        if denied:
            return denied
        item = await request.json()
        item = item or {}
        try:
            return prepare_paper_phrases(item.get("id"))
        except Exception as err:
            return {"ready": False, "rows": 0, "error": type(err).__name__}

    @web.post("/prepare")
    async def route_prepare(request: Request):
        denied = gate(request, False)
        if denied:
            return denied
        item = await request.json()
        item = item or {}
        return _retry_os(_prepare_ids, item.get("ids") or [], front=bool(item.get("front")))

    @web.post("/panorama")
    async def route_panorama(request: Request):
        denied = gate(request, False)
        if denied:
            return denied
        if core_mode():
            return {"skipped": True, "reason": "core", "claims": []}
        try:
            question, ids = parse_request(await request.json())
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        _reload()
        docs = docs_for(PAPERS, ids, load_meta, load_paper)
        try:
            return run_panorama(question, docs)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @web.get("/crops")
    def route_crops(request: Request, id: str, pages: str = ""):
        denied = gate(request, True)
        if denied:
            return denied
        if gate_file(id, load_map(map_path())):
            return {"crops": []}
        return read_crops(id, pages)

    @web.get("/file")
    def route_file(request: Request, id: str = "", name: str = ""):
        denied = gate(request, True)
        if denied:
            return denied
        if gate_file(id, load_map(map_path())):
            return Response(status_code=404)
        path = resolve_figure(PAPERS, id, name)
        if path is None and str(id).isdigit():
            try:
                _reload()
                folder = PAPERS / str(int(id))
                if heal_cached_ocr_figures(folder, load_paper(folder)):
                    vol.commit()
                path = resolve_figure(PAPERS, id, name)
            except Exception:
                path = None
        if path is None:
            pdf = resolve_source_pdf(PAPERS, id, name)
            if pdf is not None:
                return FileResponse(
                    pdf,
                    media_type="application/pdf",
                    headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
                )
            return Response(status_code=404)
        # RRM-47: is_file() can pass and the read still fail (volume view mid-
        # reload); FileResponse then died mid-stream as a 500. Read first: 404.
        try:
            data = path.read_bytes()
        except OSError:
            return Response(status_code=404)
        return Response(
            data,
            media_type=_FILE_TYPES[path.suffix.lower()],
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return web


def _fmt_ocr_chunks(meta: dict) -> str:
    bits = []
    for row in meta.get("ocr_chunks") or []:
        flag = "ok" if row.get("ok") else "fail"
        bits.append(f"{row.get('start')}-{row.get('end')}:{row.get('seconds')}:{row.get('engine')}:{flag}")
    return ",".join(bits)


def _fmt_downloads(meta: dict) -> str:
    bits = []
    for row in meta.get("downloads") or []:
        flag = "ok" if row.get("ok") else "fail"
        bits.append(f"{row.get('source')}:{row.get('seconds')}:{flag}")
    return ",".join(bits)


def _cost_row(meta: dict) -> dict:
    timings = meta.get("timings") or {}
    cpu_keys = ("resolve", "download", "parse", "katex", "figures", "sam")
    per_step = {}
    cpu_s = 0.0
    for key in cpu_keys:
        seconds = float(timings.get(key) or 0)
        cpu_s += seconds
        per_step[key] = round(seconds * 2 * CPU_USD_PER_CORE_S, 6)
    ocr_gpu = float(meta.get("ocr_gpu_s") or timings.get("ocr") or 0)
    per_step["ocr"] = round(ocr_gpu * L4_USD_PER_S, 6)
    images = int(meta.get("sam_images") or 0)
    per_step["sam_images"] = images
    return {
        "cpu_s": round(cpu_s, 3),
        "cpu_usd": round(cpu_s * 2 * CPU_USD_PER_CORE_S, 6),
        "ocr_s": round(float(timings.get("ocr") or 0), 3),
        "ocr_gpu_s": round(ocr_gpu, 3),
        "ocr_usd": per_step["ocr"],
        "sam_images": images,
        "sam_usd": round(images * SAM_USD_PER_IMAGE, 6),
        "steps": per_step,
    }


@app.local_entrypoint()
def bench(ids: str = ""):
    """Parse each corpus id. Times are seconds; dollars are the 2026-10-28 list price.

    first is time-to-first-content (stub). sections is time-to-sections. full is time-to-full.
    ocr is wall time; ocr_gpu_s is the summed GPU time used for ocr_usd.
    ocr_chunks is start-end:seconds:engine:ok per chunk. downloads is source:seconds:ok.
    """
    header = (
        "id", "status", "source", "eqs", "katex_ok", "inline", "inline_ok",
        "resolve", "download", "parse", "katex", "figures", "ocr", "ocr_gpu_s", "sam",
        "first", "sections", "full",
        "cpu_usd", "ocr_usd", "sam_usd",
        "resolve_usd", "download_usd", "parse_usd", "katex_usd", "figures_usd",
        "ocr_chunks", "downloads",
    )
    print("\t".join(header))
    for raw in ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        out = parse_one.remote(int(raw), False)
        meta = out.get("meta") or {}
        timings = meta.get("timings") or {}
        cost = _cost_row(meta)
        steps = cost["steps"]
        print("\t".join(str(x) for x in (
            raw,
            out.get("status"),
            meta.get("source"),
            meta.get("equations"),
            meta.get("katex_ok"),
            meta.get("inline_math"),
            meta.get("inline_katex_ok"),
            timings.get("resolve"),
            timings.get("download"),
            timings.get("parse"),
            timings.get("katex"),
            timings.get("figures"),
            timings.get("ocr"),
            cost["ocr_gpu_s"],
            timings.get("sam"),
            meta.get("first_content_s"),
            meta.get("sections_s"),
            meta.get("full_s"),
            cost["cpu_usd"],
            cost["ocr_usd"],
            cost["sam_usd"],
            steps.get("resolve"),
            steps.get("download"),
            steps.get("parse"),
            steps.get("katex"),
            steps.get("figures"),
            _fmt_ocr_chunks(meta),
            _fmt_downloads(meta),
        )))
