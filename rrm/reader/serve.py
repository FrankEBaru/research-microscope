"""Modal app rrm-reader: CPU fetch + LaTeX, a separate L4 function for MinerU 2.5, SAM over HTTP.

    modal run rrm/reader/serve.py::bench --ids 2048380074,123

Endpoints (CPU):
    POST /prepare   {"ids": [corpusid, ...]}  -> spawn, return per-id status
    GET  /paper?id=corpusid                   -> cached parse, or parse now
    GET  /status?ids=1,2,3                    -> queued | parsing | done | abstract_only | failed
"""

import os
import time
from pathlib import Path

import modal

from rrm.reader.fetch import ARXIV
from rrm.reader.ocr import blocks_from_mineru_dir, run_mineru
from rrm.reader.pipeline import load_meta, mark_queued, parse_corpus

DATA = "/data"
PAPERS = Path(DATA) / "papers"
DISPLAY = Path(DATA) / "2026-10-20" / "index" / "display.parquet"
# modal.com/pricing, fetched 2026-10-28, preemptible list price. GPU tasks also bill CPU and memory.
CPU_USD_PER_CORE_S = 0.0000131
L4_USD_PER_S = 0.000222
SAM_USD_PER_IMAGE = 0.0025

cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("nodejs", "npm", "ghostscript", "ca-certificates")
    .pip_install("pymupdf", "requests", "pyarrow", "fastapi[standard]")
    .run_commands("npm install --prefix /opt/katex katex@0.19.1")
    .env({"NODE_PATH": "/opt/katex/node_modules"})
    .add_local_python_source("rrm")
)
# MinerU 2.5 is a 1.2B VLM. L4 (24 GB) is the smallest Modal GPU that fits it.
# The older pipeline's "0.5-2 pages/s on L4" note is not this model; see the PR.
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "libgl1", "libglib2.0-0", "ca-certificates")
    .pip_install("torch", "torchvision", extra_index_url="https://download.pytorch.org/whl/cu124")
    .pip_install("pymupdf", "mineru[core]>=2.5,<3")
    .add_local_python_source("rrm")
)

app = modal.App("rrm-reader")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
if modal.is_local():
    secret = modal.Secret.from_dict({"MODEL_API_KEY": os.environ.get("MODEL_API_KEY", "")})
else:
    secret = modal.Secret.from_dict({})

_gate = None


def _shared_arxiv_wait():
    """One clock for every container, so arXiv stays at 1 request / 3.2 s."""
    global _gate
    if _gate is None:
        _gate = modal.Dict.from_name("rrm-arxiv-gate", create_if_missing=True)

    def wait():
        for _ in range(40):
            now = time.time()
            nxt = float(_gate.get("next") or 0)
            if now >= nxt:
                _gate["next"] = now + 3.2
                return
            time.sleep(min(3.2, nxt - now))

    ARXIV.wait = wait


def _ocr(pdf, work):
    vol.commit()
    return ocr_one.remote(str(pdf), str(work))


def _run(corpusid: int, sam: bool) -> dict:
    vol.reload()
    _shared_arxiv_wait()
    return parse_corpus(int(corpusid), PAPERS, DISPLAY, sam=sam, ocr=_ocr, commit=vol.commit)


# L4 first; A10G (24 GB) when L4 has no capacity (seen 2026-10-29: 10+ min queue).
@app.function(image=gpu_image, gpu=["L4", "A10G"], volumes={DATA: vol}, timeout=1800, memory=16384, cpu=2)
def ocr_one(pdf: str, out: str) -> dict:
    vol.reload()
    t = time.time()
    run_mineru(Path(pdf), Path(out))
    blocks = blocks_from_mineru_dir(Path(out))
    pages = None
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        pages = len(doc)
        doc.close()
    except Exception:
        pages = None
    vol.commit()
    return {"blocks": blocks, "seconds": round(time.time() - t, 3), "page_count": pages}


@app.function(image=cpu_image, volumes={DATA: vol}, cpu=2, memory=4096, timeout=900, secrets=[secret])
def parse_one(corpusid: int, sam: bool = False) -> dict:
    return _run(int(corpusid), bool(sam))


@app.function(image=cpu_image, volumes={DATA: vol}, timeout=30, secrets=[secret])
@modal.fastapi_endpoint(method="POST")
def prepare(item: dict):
    vol.reload()
    _shared_arxiv_wait()
    rows = []
    for raw in item.get("ids") or []:
        cid = int(raw)
        status = mark_queued(PAPERS / str(cid), cid)
        if status == "queued":
            parse_one.spawn(cid, False)
        rows.append({"id": cid, "status": status})
    vol.commit()
    return {"papers": rows}


@app.function(image=cpu_image, volumes={DATA: vol}, cpu=2, memory=4096, timeout=900, secrets=[secret])
@modal.fastapi_endpoint(method="GET")
def paper(id: str):
    return _run(int(id), True)


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
            rows.append({"id": cid, "status": meta.get("status"), "reason": meta.get("reason"), "source": meta.get("source")})
    return {"papers": rows}


def _cost_row(meta: dict) -> dict:
    timings = meta.get("timings") or {}
    cpu_s = sum(float(timings.get(k) or 0) for k in ("resolve", "download", "parse", "katex", "figures", "sam"))
    ocr_s = float(timings.get("ocr") or 0)
    images = int(meta.get("sam_images") or 0)
    return {
        "cpu_s": round(cpu_s, 3),
        "cpu_usd": round(cpu_s * 2 * CPU_USD_PER_CORE_S, 6),
        "ocr_s": round(ocr_s, 3),
        "ocr_usd": round(ocr_s * L4_USD_PER_S, 6),
        "sam_images": images,
        "sam_usd": round(images * SAM_USD_PER_IMAGE, 6),
    }


@app.local_entrypoint()
def bench(ids: str = ""):
    """Parse each corpus id and print seconds and a priced estimate per step."""
    header = (
        "id", "status", "source", "eqs", "katex_ok", "inline", "inline_ok",
        "resolve", "download", "parse", "katex", "figures", "ocr", "sam",
        "cpu_usd", "ocr_usd", "sam_usd",
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
            timings.get("sam"),
            cost["cpu_usd"],
            cost["ocr_usd"],
            cost["sam_usd"],
        )))
