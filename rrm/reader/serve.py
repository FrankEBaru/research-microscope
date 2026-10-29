"""Modal app rrm-reader: CPU fetch + LaTeX, parallel MinerU 2.5 on L4, SAM on demand.

    modal run rrm/reader/serve.py::bench --ids 2048380074,123

Endpoints (CPU):
    POST /prepare   {"ids": [corpusid, ...]}  -> spawn, return per-id status
    GET  /paper?id=corpusid                   -> stub immediately, then the growing cache
    GET  /crops?id=corpusid&pages=0,1         -> SAM for those pages, in the background
    GET  /status?ids=1,2,3                    -> status, stage, per-stage progress

`paper` does not call SAM. Crops run only for the pages named in `crops`.
"""

import contextvars
import json
import os
import time
from pathlib import Path

import modal

import rrm.reader.fetch as _fetch
from rrm.reader.fetch import ARXIV, arxiv_index_at, arxiv_pdf, arxiv_slot_start, reader_identity
from rrm.reader.ocr import (
    merge_ocr_parts,
    page_spans,
    pdf_page_count,
    run_chunk,
    slice_pdf,
)
from rrm.reader.pipeline import (
    load_meta,
    load_paper,
    make_stub,
    mark_queued,
    parse_corpus,
    save_meta,
    save_paper,
    worker_alive,
)
from rrm.reader.queue import forget as forget_job
from rrm.reader.queue import note as note_job
from rrm.reader.queue import release as release_job
from rrm.reader.sam import parse_pages, segment_pages

DATA = "/data"
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
    .pip_install("pymupdf", "requests", "pyarrow", "numpy", "fastapi[standard]")
    .run_commands("npm install --prefix /opt/katex katex@0.19.1")
    .env({"NODE_PATH": "/opt/katex/node_modules"})
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

app = modal.App("rrm-reader")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
if modal.is_local():
    secret = modal.Secret.from_dict({"MODEL_API_KEY": os.environ.get("MODEL_API_KEY", "")})
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
    vol.commit()
    if not spans:
        return {"blocks": [], "seconds": 0.0, "gpu_s": 0.0, "page_count": 0, "chunks": []}
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
        vol.reload()
        _shared_arxiv_wait()
        return parse_corpus(int(corpusid), PAPERS, DISPLAY, sam=False, ocr=_ocr, commit=vol.commit)
    finally:
        _forget(int(corpusid))
        _JOB.reset(token)


# L4 first; A10G (24 GB) when L4 has no capacity (seen 2026-10-29: 10+ min queue).
# max_inputs=1 and max_containers=8: each chunk is its own container. No min_containers.
# Function timeout bounds a hung container; run_chunk itself stops an attempt at 120s and retries once.
@app.function(
    image=gpu_image, gpu=["L4", "A10G"], volumes={DATA: vol},
    timeout=400, memory=16384, cpu=2, max_containers=8,
)
@modal.concurrent(max_inputs=1)
def ocr_one(pdf: str, out: str, start: int = 0, end: int = 0) -> dict:
    vol.reload()
    result = run_chunk(Path(pdf), Path(out), int(start), int(end) or None)
    result["page_count"] = pdf_page_count(Path(pdf))
    vol.commit()
    return result


@app.function(image=cpu_image, volumes={DATA: vol}, cpu=2, memory=4096, timeout=900, secrets=[secret])
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
    paper = make_stub(info)
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


def _prepare_ids(ids) -> dict:
    vol.reload()
    _shared_arxiv_wait()
    try:
        _fetch.s2_batch(ids)  # one Graph API request for the whole burst
    except Exception:
        pass
    vol.commit()  # parse_one containers must see s2.json before they resolve
    rows = []
    for raw in ids or []:
        cid = int(raw)
        status = mark_queued(PAPERS / str(cid), cid)
        if status == "queued":
            parse_one.spawn(cid, False)
        rows.append({"id": cid, "status": status})
    vol.commit()
    return {"papers": rows}


@app.function(image=cpu_image, volumes={DATA: vol}, timeout=60, secrets=[secret])
@modal.fastapi_endpoint(method="POST")
def prepare(item: dict):
    return _prepare_ids(item.get("ids") or [])


# A web endpoint cannot be .spawn()ed from another app (InvalidError), so /burst spawns this.
@app.function(image=cpu_image, volumes={DATA: vol}, timeout=60, secrets=[secret])
def prefetch(ids: list) -> dict:
    return _prepare_ids(ids)


@app.function(image=cpu_image, volumes={DATA: vol}, timeout=60, secrets=[secret])
@modal.fastapi_endpoint(method="GET")
def paper(id: str):
    """Return whatever is already readable. Parsing continues in the background."""
    vol.reload()
    _shared_arxiv_wait()
    cid = int(id)
    folder = PAPERS / str(cid)
    folder.mkdir(parents=True, exist_ok=True)
    meta = load_meta(folder)
    if meta and meta.get("status") in ("done", "abstract_only", "failed"):
        return {"status": meta["status"], "meta": meta, "paper": load_paper(folder), "cached": True}
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
    meta = load_meta(folder) or {}
    return {"status": meta.get("status"), "meta": meta, "paper": paper_obj, "cached": False}


@app.function(image=cpu_image, volumes={DATA: vol}, cpu=2, memory=4096, timeout=600, secrets=[secret])
def crops_for(corpusid: int, pages: list):
    token = _JOB.set(int(corpusid))
    try:
        vol.reload()
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


@app.function(image=cpu_image, volumes={DATA: vol}, timeout=30, secrets=[secret])
@modal.fastapi_endpoint(method="GET")
def crops(id: str, pages: str = ""):
    """SAM for the pages in view. Returns the crops already on disk and keeps working in the background."""
    vol.reload()
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
    have = {row.get("page") for row in (index.get("crops") or [])} | {int(p) for p in (index.get("done_pages") or [])}
    fresh = [p for p in wanted if p not in have]
    meta = load_meta(folder) or {}
    inflight = {int(p) for p in (meta.get("crops_inflight") or [])}
    status = "done"
    if index.get("error") == "no MODEL_API_KEY":
        status = "skipped"
    elif fresh:
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
    rows = index.get("crops") or []
    if wanted:
        rows = [row for row in rows if row.get("page") in wanted]
    return {
        "id": cid,
        "status": status,
        "pages": wanted,
        "crops": rows,
        "error": index.get("error"),
        "images": index.get("images") or 0,
    }


@app.function(image=cpu_image, volumes={DATA: vol}, timeout=30)
@modal.fastapi_endpoint(method="GET")
def status(ids: str = ""):
    vol.reload()
    rows = []
    for raw in ids.split(","):
        raw = raw.strip()
        if not raw:
            continue
        cid = int(raw)
        meta = load_meta(PAPERS / str(cid))
        if not meta:
            rows.append({"id": cid, "status": "missing"})
        else:
            rows.append({
                "id": cid,
                "status": meta.get("status"),
                "stage": meta.get("stage"),
                "stages": meta.get("stages"),
                "reason": meta.get("reason"),
                "source": meta.get("source"),
                "upgraded_from": meta.get("upgraded_from"),
                "first_content_s": meta.get("first_content_s"),
                "sections_s": meta.get("sections_s"),
                "full_s": meta.get("full_s"),
            })
    return {"papers": rows}


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
