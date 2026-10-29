"""Resolve, download, parse, KaTeX-check, and (on open) SAM one corpus id.

Cache layout on the volume, under papers/{corpusid}/:

    paper.json   block schema
    meta.json    status, source, timings (seconds), counts
    figures/     rendered figure PNGs
    crops/       SAM crops + index.json
    src/         unpacked e-print (not the downloaded bytes)
    source.pdf   when a PDF was fetched
"""

import json
import threading
import time
from pathlib import Path

from rrm.reader.fetch import (
    DownloadError,
    arxiv_eprint,
    arxiv_pdf,
    fetch_pdf,
    graph_reference_map,
    merge_s2,
    race_pdf_bytes,
    reader_identity,
    s2_graph,
    s2_reference_map,
    unpack_eprint,
    valid_pdf,
)
from rrm.reader.latex import attach_katex, materialize_figures, parse_inlines, parse_tree, stats, text_tokens

STATUSES = ("queued", "parsing", "done", "abstract_only", "failed")
TIMING_KEYS = ("resolve", "download", "parse", "katex", "figures", "ocr", "sam")
STAGE_NAMES = ("stub", "sections", "figures", "crops")


def _blank_timings():
    return {k: 0.0 for k in TIMING_KEYS}


def meta_path(folder: Path) -> Path:
    return folder / "meta.json"


def load_meta(folder: Path) -> dict | None:
    path = meta_path(folder)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(folder: Path, meta: dict):
    folder.mkdir(parents=True, exist_ok=True)
    meta_path(folder).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def save_paper(folder: Path, paper: dict):
    (folder / "paper.json").write_text(json.dumps(paper, ensure_ascii=False), encoding="utf-8")


def _round(timings):
    return {k: round(float(timings.get(k) or 0), 4) for k in TIMING_KEYS}


def _stages_for(meta, stage: str) -> dict:
    stages = dict(meta.get("stages") or blank_stages())
    status = meta.get("status")
    if stage == "stub":
        stages["stub"] = "done"
    elif stage in ("resolve", "download"):
        stages["stub"] = "done"
        stages["sections"] = "pending"
    elif stage == "sections":
        stages["stub"] = "done"
        stages["sections"] = "done"
        stages["figures"] = "running"
    elif stage == "figures":
        stages["stub"] = "done"
        stages["figures"] = "running"
    elif stage == "ocr":
        stages["stub"] = "done"
        stages["sections"] = "running"
    elif stage == "done" or status in ("done", "abstract_only"):
        stages["stub"] = "done"
        if status == "abstract_only":
            stages["sections"] = "skipped"
            stages["figures"] = "skipped"
        else:
            stages["sections"] = "done"
            stages["figures"] = "done"
    elif stage == "failed" or status == "failed":
        stages["stub"] = stages.get("stub") or "done"
    return stages


def _publish(folder, meta, paper, commit, stage: str):
    """Write the snapshot a poll of paper?id= will read. Terminal snapshots record counts."""
    meta["stage"] = stage
    meta["stages"] = _stages_for(meta, stage)
    now = time.time()
    started = float(meta.get("started") or now)
    if paper is not None:
        paper["corpusid"] = meta.get("corpusid")
        paper["status"] = meta.get("status")
        paper["stage"] = stage
        paper["stages"] = meta["stages"]
        readable = bool(paper.get("title") or paper.get("abstract") or paper.get("tldr") or paper.get("blocks"))
        if readable and meta.get("first_content_s") is None:
            meta["first_content_s"] = round(now - started, 4)
        if stage == "sections" and meta.get("sections_s") is None:
            meta["sections_s"] = round(now - started, 4)
        save_paper(folder, paper)
    if meta.get("status") in ("done", "abstract_only", "failed"):
        meta["full_s"] = round(now - started, 4)
        if (
            paper is not None
            and meta.get("sections_s") is None
            and any(b.get("kind") in ("h", "eq", "p") for b in (paper.get("blocks") or []))
        ):
            meta["sections_s"] = meta["full_s"]
        if paper is not None and meta["status"] != "failed":
            meta.update(stats(paper))
    meta["timings"] = _round(meta.get("timings") or {})
    save_meta(folder, meta)
    if commit:
        commit()
    return {"status": meta["status"], "meta": meta, "paper": paper}


def _finish(folder, meta, paper, commit):
    stage = "failed" if meta.get("status") == "failed" else "done"
    return _publish(folder, meta, paper, commit, stage)


def blank_stages() -> dict:
    return {name: "pending" for name in STAGE_NAMES}


def abstract_paper(info: dict) -> dict:
    text = info.get("abstract") or ""
    inlines = parse_inlines(text, {}) if text else []
    blocks = []
    if inlines:
        blocks = [{"kind": "p", "id": "b0", "abs": True, "inlines": inlines, "sents": [inlines]}]
    return {
        "arxivId": info.get("arxiv") or "",
        "corpusid": info.get("corpusid"),
        "title": info.get("title") or "",
        "authors": info.get("authors") or [],
        "date": str(info.get("year") or ""),
        "abstract": text,
        "tldr": info.get("tldr") or "",
        "license": None,
        "authorNotes": [],
        "full": False,
        "source": "abstract",
        "refs": dict(info.get("refs") or {}),
        "blocks": blocks,
    }


_SOURCE_RANK = {"abstract": 1, "ocr": 2, "latex": 3}


def prefer_parsed(current: dict | None, incoming: dict | None, *, published: bool = False) -> dict | None:
    """Keep the stronger parse. Published OCR/abstract yields to later LaTeX.

    `upgraded_from` is set only when a parse that was already published is replaced.
    OCR never replaces LaTeX.
    """
    if incoming is None:
        return current
    if current is None:
        return incoming
    new = incoming.get("source") or ""
    cur = current.get("source") or ""
    if _SOURCE_RANK.get(new, 0) <= _SOURCE_RANK.get(cur, 0):
        return current
    upgraded = dict(incoming)
    if published and cur:
        upgraded["upgraded_from"] = cur
    return upgraded


def apply_s2_fields(paper: dict, info: dict) -> dict:
    """Fill gaps from Semantic Scholar. S2 authors replace the LaTeX list when S2 has any."""
    if paper is None:
        return paper
    paper["tldr"] = paper.get("tldr") or info.get("tldr") or ""
    if info.get("authors"):
        paper["authors"] = list(info["authors"])
    elif not paper.get("authors"):
        paper["authors"] = []
    if not paper.get("abstract"):
        paper["abstract"] = info.get("abstract") or ""
    if not paper.get("title"):
        paper["title"] = info.get("title") or ""
    if not paper.get("refs"):
        paper["refs"] = dict(info.get("refs") or {})
    if not paper.get("arxivId"):
        paper["arxivId"] = info.get("arxiv") or ""
    if paper.get("corpusid") is None:
        paper["corpusid"] = info.get("corpusid")
    return paper


def make_stub(info: dict) -> dict:
    """Readable title, authors, abstract, and tldr before sections exist."""
    paper = abstract_paper(info)
    paper["status"] = "parsing"
    paper["stage"] = "stub"
    stages = blank_stages()
    stages["stub"] = "done"
    paper["stages"] = stages
    return paper


def paper_from_ocr(info: dict, blocks: list) -> dict:
    paper = abstract_paper(info)
    paper["full"] = True
    paper["source"] = "ocr"
    paper["blocks"] = blocks
    apply_s2_fields(paper, info)
    paper["abstract"] = info.get("abstract") or paper.get("abstract") or ""
    paper["authors"] = list(info.get("authors") or paper.get("authors") or [])
    paper["tldr"] = info.get("tldr") or paper.get("tldr") or ""
    paper["refs"] = dict(info.get("refs") or paper.get("refs") or {})
    return paper


def load_paper(folder: Path) -> dict | None:
    path = folder / "paper.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def worker_alive(meta: dict | None, now: float | None = None) -> bool:
    if not meta or meta.get("status") not in ("queued", "parsing"):
        return False
    now = time.time() if now is None else now
    return now - float(meta.get("started") or 0) < STALE_S


STALE_S = 1800  # a parse older than the function timeout died; queue it again


def mark_queued(folder: Path, corpusid: int):
    current = load_meta(folder)
    if current and current.get("status") in ("done", "abstract_only"):
        return current["status"]
    if current and current.get("status") in ("parsing", "queued"):
        if time.time() - float(current.get("started") or 0) < STALE_S:
            return current["status"]
    save_meta(folder, {
        "corpusid": int(corpusid),
        "status": "queued",
        "reason": None,
        "source": None,
        "timings": _blank_timings(),
        "started": time.time(),
    })
    return "queued"


def _fill_refs(info: dict, display_path):
    if info.get("refs"):
        return
    root = None
    if display_path:
        path = Path(display_path)
        if path.name == "display.parquet" and path.parent.name == "index":
            root = path.parent
    if root is not None:
        try:
            info["refs"] = graph_reference_map(root, int(info.get("corpusid") or 0))
        except Exception:
            info["refs"] = {}
    if info.get("refs"):
        return
    try:
        info["refs"] = s2_reference_map(int(info.get("corpusid") or 0))
    except Exception:
        info["refs"] = info.get("refs") or {}


def _apply_katex(paper):
    t = time.time()
    try:
        attach_katex(paper["blocks"])
    except Exception as err:
        for b in paper["blocks"]:
            if b.get("kind") == "eq" and b.get("katex_ok") is None:
                b["katex_ok"] = False
        paper["katex_error"] = str(err)[:300]
    return time.time() - t


def parse_corpus(
    corpusid: int,
    papers_root: Path,
    display_path: Path | None = None,
    *,
    sam: bool = False,
    ocr=None,
    commit=None,
) -> dict:
    """Parse one paper. Cached terminal results return immediately.

    ocr(pdf_path, work_dir) -> {"blocks": [...], "seconds": float, "gpu_s": float} or raises.
    sam is ignored: crops are a separate request for the pages in view.
    The stub (title, authors, abstract, tldr) is written before download, and
    LaTeX sections are written before figures are rendered.
    """
    del sam  # crops are not part of this path
    folder = Path(papers_root) / str(int(corpusid))
    folder.mkdir(parents=True, exist_ok=True)
    cached = load_meta(folder)
    if cached and cached.get("status") in ("done", "abstract_only") and (folder / "paper.json").is_file():
        paper = json.loads((folder / "paper.json").read_text(encoding="utf-8"))
        return {"status": cached["status"], "meta": cached, "paper": paper, "cached": True}

    meta = {
        "corpusid": int(corpusid),
        "status": "parsing",
        "stage": "resolve",
        "stages": blank_stages(),
        "reason": None,
        "source": None,
        "timings": _blank_timings(),
        "page_count": None,
        "started": time.time(),
        "ocr_gpu_s": 0.0,
    }
    save_meta(folder, meta)
    if commit:
        commit()

    def publish(paper, stage):
        return _publish(folder, meta, paper, commit, stage)

    try:
        t = time.time()
        # Refs from the citation graph are local. The Graph API runs only for gaps,
        # and reference strings are filled here so the open request can stay on the stub.
        # No shard scan here: reading the 61 papers/abstracts shards on the volume took
        # 100-250 s per paper in QA (2026-10-29). The display row plus one Graph API call
        # fills authors and abstract.
        # Refs come after the stub: the citation graph is large, and the reference
        # API is a second request. Neither should delay the first readable snapshot.
        info = reader_identity(int(corpusid), display_path, remote=True, refs=False, shards=False)
        meta["timings"]["resolve"] = time.time() - t
        meta["title"] = info.get("title") or ""
        meta["tldr"] = info.get("tldr") or ""
        meta["arxiv"] = info.get("arxiv") or ""
    except Exception as err:
        meta["status"] = "failed"
        meta["reason"] = f"resolve failed: {err}"
        return _finish(folder, meta, None, commit)

    publish(make_stub(info), "stub")
    # One Graph retry may run after the stub is already on disk. A cache hit does not block.
    before = (tuple(info.get("authors") or []), info.get("abstract") or "", info.get("tldr") or "", info.get("oa_pdf") or "")
    info = _enrich_s2(info)
    after = (tuple(info.get("authors") or []), info.get("abstract") or "", info.get("tldr") or "", info.get("oa_pdf") or "")
    if after != before:
        meta["title"] = info.get("title") or meta.get("title") or ""
        meta["tldr"] = info.get("tldr") or ""
        meta["arxiv"] = info.get("arxiv") or meta.get("arxiv") or ""
        publish(make_stub(info), "stub")
    pdf_path = folder / "source.pdf"
    try:
        route, paper, pdf_path = _fetch_and_parse(folder, info, meta, pdf_path, ocr, publish)
    except Exception as err:
        meta["status"] = "failed"
        meta["reason"] = str(err)[:500]
        return _finish(folder, meta, load_paper(folder), commit)

    _fill_refs(info, display_path)
    if paper is not None:
        apply_s2_fields(paper, info)

    if route == "abstract":
        meta["status"] = "abstract_only"
        meta["source"] = "abstract"
        meta["reason"] = meta.get("reason") or "no arXiv e-print and no open-access PDF"
        return _finish(folder, meta, paper, commit)

    if paper is None:
        meta["status"] = "failed"
        meta["reason"] = meta.get("reason") or "empty parse"
        return _finish(folder, meta, load_paper(folder), commit)

    meta["status"] = "done"
    meta["source"] = paper.get("source")
    if paper.get("upgraded_from"):
        meta["upgraded_from"] = paper["upgraded_from"]
    if pdf_path and Path(pdf_path).is_file() and meta.get("page_count") is None:
        meta["page_count"] = _page_count(Path(pdf_path))
    return _finish(folder, meta, paper, commit)


def _page_count(pdf_path: Path) -> int | None:
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return None


def _s2_gap(info: dict) -> bool:
    if not info.get("authors"):
        return True
    if not (info.get("abstract") or "").strip():
        return True
    if not info.get("arxiv") and not info.get("oa_pdf"):
        return True
    return False


def _enrich_s2(info: dict) -> dict:
    """Read the s2.json cache, or one retry when the stub is still missing fields. Never raises."""
    cid = info.get("corpusid")
    if cid is None:
        return info
    remote = {}
    try:
        from rrm.reader.fetch import _s2_cache
        path = _s2_cache(int(cid))
        if path is not None and path.is_file():
            remote = s2_graph(int(cid), tries=1)
        elif _s2_gap(info):
            remote = s2_graph(int(cid), tries=2)
    except Exception:
        remote = {}
    return merge_s2(info, remote)


def _note_reason(meta, reason: str):
    if meta.get("source") == "latex":
        return
    meta["reason"] = reason


def _fetch_and_parse(folder, info, meta, pdf_path, ocr, publish=None):
    """Start the e-print and the PDF route together. Publish whichever parse finishes first.

    A later LaTeX parse replaces a published OCR paper (`source`, `upgraded_from`).
    OCR never replaces LaTeX. PDF bytes race arXiv vs the S2 open-access URL.
    """
    arxiv = info.get("arxiv") or ""
    oa = info.get("oa_pdf") or ""
    src = folder / "src"
    downloads = []
    meta["downloads"] = downloads
    lock = threading.Lock()
    state = {"best": None, "route": None, "pdf_path": pdf_path, "published": False, "eprint_pdf": None}
    eprint_dl = threading.Event()
    pdf_dl = threading.Event()

    def note_download(row):
        with lock:
            downloads.append(row)

    def offer(route, paper, reason):
        with lock:
            if paper is None:
                return
            src_name = paper.get("source") or ""
            if route == "abstract" or src_name == "abstract":
                if state["best"] is None:
                    state["best"] = paper
                    state["route"] = "abstract"
                    if reason:
                        meta["reason"] = reason
                return
            chosen = prefer_parsed(state["best"], paper, published=state["published"])
            if chosen is state["best"]:
                return
            if chosen.get("upgraded_from"):
                meta["upgraded_from"] = chosen["upgraded_from"]
            meta["source"] = chosen.get("source")
            if chosen.get("source") == "latex":
                meta["reason"] = None
            elif reason:
                meta["reason"] = reason
            state["best"] = chosen
            state["route"] = "latex" if chosen.get("source") == "latex" else route
            state["published"] = True
            if publish:
                stage = "sections" if chosen.get("source") == "latex" else "ocr"
                publish(chosen, stage)

    def eprint_worker():
        try:
            if not arxiv:
                return
            t0 = time.time()
            try:
                blob = arxiv_eprint(arxiv)
            except Exception as err:
                note_download({
                    "source": "arxiv_eprint", "seconds": round(time.time() - t0, 3),
                    "ok": False, "reason": str(err)[:200],
                })
                return
            note_download({
                "source": "arxiv_eprint", "seconds": round(time.time() - t0, 3),
                "ok": True, "bytes": len(blob),
            })
            kind = unpack_eprint(blob, src)
            if kind == "pdf":
                got = src / "source.pdf"
                if not got.is_file():
                    pdfs = sorted(p for p in src.rglob("*.pdf") if p.is_file())
                    got = pdfs[0] if pdfs else None
                if got is not None and got.is_file():
                    with lock:
                        state["eprint_pdf"] = got.read_bytes()
                return
            if kind != "tex":
                return
            eprint_dl.set()
            t_parse = time.time()
            parsed = parse_tree(src, arxiv_id=arxiv)
            with lock:
                meta["timings"]["parse"] += time.time() - t_parse
            if parsed.get("route") != "latex":
                with lock:
                    if meta.get("source") != "latex":
                        meta["reason"] = parsed.get("reason") or meta.get("reason")
                return
            paper = parsed["paper"]
            paper["arxivId"] = arxiv
            apply_s2_fields(paper, info)
            t_k = time.time()
            katex_s = _apply_katex(paper)
            with lock:
                meta["timings"]["katex"] += katex_s
            offer("latex", paper, None)
            t_f = time.time()
            materialize_figures(paper["blocks"], src, folder / "figures")
            with lock:
                meta["timings"]["figures"] += time.time() - t_f
                if state["best"] is not None and state["best"].get("source") == "latex" and publish:
                    publish(state["best"], "figures")
        except Exception as err:
            with lock:
                if meta.get("source") != "latex":
                    meta["reason"] = meta.get("reason") or f"e-print failed: {err}"
        finally:
            eprint_dl.set()

    def pdf_worker():
        try:
            stop = threading.Event()
            jobs = []
            if arxiv:
                jobs.append(("arxiv_pdf", lambda: arxiv_pdf(arxiv, cancel=stop.is_set)))
            if oa and not (arxiv and "arxiv.org" in oa):
                jobs.append(("oa_pdf", lambda: fetch_pdf(oa, cancel=stop.is_set)))
            won = None
            if jobs:
                try:
                    won = race_pdf_bytes(jobs, note=note_download, stop=stop)
                except DownloadError as err:
                    with lock:
                        _note_reason(meta, f"pdf failed: {err}")
            if won and valid_pdf(won.get("data") or b""):
                with lock:
                    meta["pdf_source"] = won.get("source")
                    pdf_path.write_bytes(won["data"])
            pdf_dl.set()
            if not pdf_path.is_file() or pdf_path.stat().st_size < 8:
                return
            why = f"pdf {meta.get('pdf_source') or 'fetched'}"
            route, paper, _path = _ocr_route(
                folder, info, meta, pdf_path, ocr, why, publish, announce=False,
            )
            offer(route, paper, meta.get("reason") if route == "abstract" else why)
        except Exception as err:
            with lock:
                _note_reason(meta, f"pdf route failed: {err}")
        finally:
            pdf_dl.set()

    t_dl = time.time()
    workers = []
    if arxiv:
        workers.append(threading.Thread(target=eprint_worker, name="rrm-eprint", daemon=True))
    else:
        eprint_dl.set()
    if arxiv or oa:
        workers.append(threading.Thread(target=pdf_worker, name="rrm-pdf", daemon=True))
    else:
        pdf_dl.set()
    for worker in workers:
        worker.start()
    eprint_dl.wait()
    pdf_dl.wait()
    with lock:
        meta["timings"]["download"] += time.time() - t_dl
    for worker in workers:
        worker.join()

    with lock:
        fallback = state.get("eprint_pdf")
        need_fallback = fallback and (state["best"] is None or state["route"] == "abstract")
    if need_fallback:
        pdf_path.write_bytes(fallback)
        note_download({"source": "arxiv_eprint_pdf", "seconds": 0.0, "ok": True, "bytes": len(fallback)})
        route, paper, _path = _ocr_route(
            folder, info, meta, pdf_path, ocr, "e-print is a PDF", publish, announce=False,
        )
        offer(route, paper, meta.get("reason") if route == "abstract" else "e-print is a PDF")

    with lock:
        best = state["best"]
        route = state["route"]
        out_path = state["pdf_path"]
    if best is None or route is None:
        meta["reason"] = meta.get("reason") or "no arXiv e-print and no open-access PDF"
        return "abstract", abstract_paper(info), pdf_path
    return route, best, out_path


def _ocr_route(folder, info, meta, pdf_path, ocr, why: str, publish=None, announce=True):
    if ocr is None:
        _note_reason(meta, f"{why}; ocr not run in this process")
        paper = abstract_paper(info)
        paper["full"] = False
        return "abstract", paper, pdf_path
    if announce and publish:
        publish(abstract_paper(info), "ocr")
    t = time.time()
    try:
        result = ocr(pdf_path, folder / "ocr")
    except Exception as err:
        meta["timings"]["ocr"] += time.time() - t
        chunks = getattr(err, "chunks", None)
        if chunks:
            meta["ocr_chunks"] = chunks
        _note_reason(meta, f"ocr failed: {err}"[:500])
        return "abstract", abstract_paper(info), pdf_path
    meta["timings"]["ocr"] += float(result.get("seconds") or (time.time() - t))
    meta["ocr_gpu_s"] = float(meta.get("ocr_gpu_s") or 0) + float(result.get("gpu_s") or result.get("seconds") or 0)
    if result.get("chunks"):
        meta["ocr_chunks"] = result["chunks"]
    blocks = result.get("blocks") or []
    if not blocks:
        _note_reason(meta, f"{why}; ocr returned no blocks")
        return "abstract", abstract_paper(info), pdf_path
    t = time.time()
    eqs = [b for b in blocks if b.get("kind") == "eq"]
    for b in eqs:
        b["source"] = "ocr"
    try:
        attach_katex(blocks)  # display and inline math, same check as the LaTeX path
    except Exception as err:
        for b in eqs:
            b["katex_ok"] = False
        meta["katex_error"] = str(err)[:300]
    meta["timings"]["katex"] += time.time() - t
    paper = paper_from_ocr(info, blocks)
    meta["page_count"] = result.get("page_count") or _page_count(pdf_path)
    _note_reason(meta, why)
    return "ocr", paper, pdf_path
