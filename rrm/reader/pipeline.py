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
import time
from pathlib import Path

from rrm.reader.fetch import arxiv_eprint, arxiv_pdf, fetch_url, resolve_identity, unpack_eprint
from rrm.reader.katex import check_tex
from rrm.reader.latex import attach_katex, materialize_figures, parse_inlines, parse_tree, stats, text_tokens
from rrm.reader.sam import segment_pdf

STATUSES = ("queued", "parsing", "done", "abstract_only", "failed")
TIMING_KEYS = ("resolve", "download", "parse", "katex", "figures", "ocr", "sam")


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


def _finish(folder, meta, paper, commit):
    meta["timings"] = _round(meta.get("timings") or {})
    if paper is not None:
        counts = stats(paper)
        meta.update(counts)
        paper["corpusid"] = meta.get("corpusid")
        paper["status"] = meta["status"]
        save_paper(folder, paper)
    save_meta(folder, meta)
    if commit:
        commit()
    return {"status": meta["status"], "meta": meta, "paper": paper}


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
        "refs": {},
        "blocks": blocks,
    }


def mark_queued(folder: Path, corpusid: int):
    current = load_meta(folder)
    if current and current.get("status") in ("done", "abstract_only", "parsing", "queued"):
        return current["status"]
    save_meta(folder, {
        "corpusid": int(corpusid),
        "status": "queued",
        "reason": None,
        "source": None,
        "timings": _blank_timings(),
    })
    return "queued"


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

    ocr(pdf_path, work_dir) -> {"blocks": [...], "seconds": float} or raises.
    sam=True is the user-open path: page crops for this paper only.
    """
    folder = Path(papers_root) / str(int(corpusid))
    folder.mkdir(parents=True, exist_ok=True)
    cached = load_meta(folder)
    paper = None
    if cached and cached.get("status") in ("done", "abstract_only") and (folder / "paper.json").is_file():
        paper = json.loads((folder / "paper.json").read_text(encoding="utf-8"))
        if not sam or cached.get("sam_done"):
            return {"status": cached["status"], "meta": cached, "paper": paper, "cached": True}
        return _run_sam(folder, cached, paper, commit)

    meta = {
        "corpusid": int(corpusid),
        "status": "parsing",
        "reason": None,
        "source": None,
        "timings": _blank_timings(),
        "page_count": None,
    }
    save_meta(folder, meta)
    if commit:
        commit()
    try:
        t = time.time()
        info = resolve_identity(int(corpusid), display_path)
        meta["timings"]["resolve"] = time.time() - t
        meta["title"] = info.get("title") or ""
        meta["arxiv"] = info.get("arxiv") or ""
    except Exception as err:
        meta["status"] = "failed"
        meta["reason"] = f"resolve failed: {err}"
        return _finish(folder, meta, None, commit)

    pdf_path = folder / "source.pdf"
    try:
        route, paper, pdf_path = _fetch_and_parse(folder, info, meta, pdf_path, ocr)
    except Exception as err:
        meta["status"] = "failed"
        meta["reason"] = str(err)[:500]
        return _finish(folder, meta, None, commit)

    if route == "abstract":
        meta["status"] = "abstract_only"
        meta["source"] = "abstract"
        meta["reason"] = meta.get("reason") or "no arXiv e-print and no open-access PDF"
        return _finish(folder, meta, paper, commit)

    if paper is None:
        meta["status"] = "failed"
        meta["reason"] = meta.get("reason") or "empty parse"
        return _finish(folder, meta, None, commit)

    meta["status"] = "done"
    meta["source"] = paper.get("source")
    if pdf_path and Path(pdf_path).is_file() and meta.get("page_count") is None:
        meta["page_count"] = _page_count(Path(pdf_path))
    if sam:
        pdf_path = _ensure_pdf(Path(pdf_path) if pdf_path else folder / "source.pdf", meta)
        _attach_sam(folder, meta, pdf_path)
    return _finish(folder, meta, paper, commit)


def _ensure_pdf(pdf_path: Path, meta: dict) -> Path:
    if pdf_path.is_file() or not meta.get("arxiv"):
        return pdf_path
    t = time.time()
    try:
        pdf_path.write_bytes(arxiv_pdf(meta["arxiv"]))
    except Exception as err:
        meta["sam_error"] = f"pdf download failed: {err}"
    meta["timings"]["download"] = float(meta["timings"].get("download") or 0) + time.time() - t
    return pdf_path


def _run_sam(folder, meta, paper, commit):
    pdf = folder / "source.pdf"
    if not pdf.is_file() and meta.get("arxiv"):
        t = time.time()
        try:
            pdf.write_bytes(arxiv_pdf(meta["arxiv"]))
            meta["timings"]["download"] = round(meta["timings"].get("download", 0) + time.time() - t, 4)
        except Exception as err:
            meta["sam_error"] = f"pdf download failed: {err}"
            meta["sam_done"] = False
            save_meta(folder, meta)
            if commit:
                commit()
            return {"status": meta["status"], "meta": meta, "paper": paper, "cached": True}
    _attach_sam(folder, meta, pdf if pdf.is_file() else None)
    save_meta(folder, meta)
    if commit:
        commit()
    return {"status": meta["status"], "meta": meta, "paper": paper, "cached": True}


def _attach_sam(folder, meta, pdf_path):
    t = time.time()
    if not pdf_path or not Path(pdf_path).is_file():
        meta["sam_done"] = False
        meta["sam_error"] = "no pdf"
        meta["timings"]["sam"] = 0
        return
    out = segment_pdf(Path(pdf_path), folder / "crops")
    meta["timings"]["sam"] = time.time() - t
    meta["sam_images"] = out["images"]
    meta["sam_cost_usd"] = out["cost_usd"]
    meta["sam_error"] = out["error"]
    # A missing key is not cached as done, so a later key still crops this paper.
    meta["sam_done"] = out["error"] is None or out["images"] > 0
    if meta.get("page_count") is None:
        meta["page_count"] = out.get("pages")


def _page_count(pdf_path: Path) -> int | None:
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return None


def _fetch_and_parse(folder, info, meta, pdf_path, ocr):
    t = time.time()
    arxiv = info.get("arxiv") or ""
    src = folder / "src"
    if arxiv:
        try:
            blob = arxiv_eprint(arxiv)
        except Exception as err:
            blob = None
            meta["reason"] = f"e-print failed: {err}"
        meta["timings"]["download"] += time.time() - t
        if blob:
            kind = unpack_eprint(blob, src)
            if kind == "pdf":
                got = src / "source.pdf"
                if not got.is_file():
                    pdfs = sorted(src.rglob("*.pdf"))
                    got = pdfs[0] if pdfs else got
                if got.is_file():
                    pdf_path.write_bytes(got.read_bytes())
                return _ocr_route(folder, info, meta, pdf_path, ocr, "e-print is a PDF")
            if kind == "tex":
                t = time.time()
                parsed = parse_tree(src, arxiv_id=arxiv)
                meta["timings"]["parse"] += time.time() - t
                if parsed["route"] == "pdf":
                    meta["reason"] = parsed["reason"]
                    t = time.time()
                    try:
                        pdf_path.write_bytes(arxiv_pdf(arxiv))
                    except Exception as err:
                        meta["reason"] = f"{parsed['reason']}; pdf failed: {err}"
                        return "abstract", abstract_paper(info), pdf_path
                    meta["timings"]["download"] += time.time() - t
                    return _ocr_route(folder, info, meta, pdf_path, ocr, parsed["reason"])
                paper = parsed["paper"]
                paper["arxivId"] = arxiv
                paper["title"] = paper.get("title") or info.get("title") or ""
                if not paper.get("authors"):
                    paper["authors"] = info.get("authors") or []
                t = time.time()
                meta["timings"]["katex"] += _apply_katex(paper)
                t = time.time()
                materialize_figures(paper["blocks"], src, folder / "figures")
                meta["timings"]["figures"] += time.time() - t
                return "latex", paper, pdf_path
        # e-print missing: the PDF is the source of truth for this id
        t = time.time()
        try:
            pdf_path.write_bytes(arxiv_pdf(arxiv))
            meta["timings"]["download"] += time.time() - t
            return _ocr_route(folder, info, meta, pdf_path, ocr, meta.get("reason") or "no tex e-print")
        except Exception as err:
            meta["timings"]["download"] += time.time() - t
            meta["reason"] = f"no tex and pdf failed: {err}"
            return "abstract", abstract_paper(info), pdf_path

    oa = info.get("oa_pdf") or ""
    if oa:
        t = time.time()
        try:
            pdf_path.write_bytes(fetch_url(oa))
        except Exception as err:
            meta["timings"]["download"] += time.time() - t
            meta["reason"] = f"open-access pdf failed: {err}"
            return "abstract", abstract_paper(info), pdf_path
        meta["timings"]["download"] += time.time() - t
        return _ocr_route(folder, info, meta, pdf_path, ocr, "no arXiv id")
    return "abstract", abstract_paper(info), pdf_path


def _ocr_route(folder, info, meta, pdf_path, ocr, why: str):
    if ocr is None:
        meta["reason"] = f"{why}; ocr not run in this process"
        paper = abstract_paper(info)
        paper["full"] = False
        return "abstract", paper, pdf_path
    t = time.time()
    try:
        result = ocr(pdf_path, folder / "ocr")
    except Exception as err:
        meta["timings"]["ocr"] += time.time() - t
        meta["reason"] = f"ocr failed: {err}"[:500]
        return "abstract", abstract_paper(info), pdf_path
    meta["timings"]["ocr"] += float(result.get("seconds") or (time.time() - t))
    blocks = result.get("blocks") or []
    if not blocks:
        meta["reason"] = f"{why}; ocr returned no blocks"
        return "abstract", abstract_paper(info), pdf_path
    t = time.time()
    eqs = [b for b in blocks if b.get("kind") == "eq"]
    if eqs:
        try:
            flags = check_tex([b.get("tex") or "" for b in eqs])
            for b, flag in zip(eqs, flags):
                b["katex_ok"] = bool(flag)
                b["source"] = "ocr"
        except Exception as err:
            for b in eqs:
                b["katex_ok"] = False
                b["source"] = "ocr"
            meta["katex_error"] = str(err)[:300]
    meta["timings"]["katex"] += time.time() - t
    paper = abstract_paper(info)
    paper["full"] = True
    paper["source"] = "ocr"
    paper["blocks"] = blocks
    paper["abstract"] = info.get("abstract") or ""
    meta["page_count"] = result.get("page_count") or _page_count(pdf_path)
    meta["reason"] = why
    return "ocr", paper, pdf_path
