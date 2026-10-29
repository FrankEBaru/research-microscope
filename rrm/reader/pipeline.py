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

from rrm.reader.fetch import (
    arxiv_eprint,
    arxiv_pdf,
    fetch_url,
    graph_reference_map,
    reader_identity,
    s2_graph,
    s2_reference_map,
    unpack_eprint,
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
        # One Semantic Scholar attempt, no backoff. A retry would hold the stub
        # (QA 2026-10-29: 429 backoff made it ~65 s). Gaps are filled after publish.
        info = reader_identity(
            int(corpusid), display_path, remote=True, refs=False, shards=False,
            s2_tries=1, s2_timeout=5, s2_backoff=False,
        )
        meta["timings"]["resolve"] = time.time() - t
        meta["title"] = info.get("title") or ""
        meta["tldr"] = info.get("tldr") or ""
        meta["arxiv"] = info.get("arxiv") or ""
    except Exception as err:
        meta["status"] = "failed"
        meta["reason"] = f"resolve failed: {err}"
        return _finish(folder, meta, None, commit)

    publish(make_stub(info), "stub")
    info = _s2_fill_later(folder, info, publish)
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


def _s2_snapshot(info: dict) -> tuple:
    return (
        tuple(info.get("authors") or []),
        info.get("abstract") or "",
        info.get("tldr") or "",
        info.get("arxiv") or "",
        info.get("oa_pdf") or "",
        info.get("title") or "",
    )


def _s2_needed(info: dict) -> bool:
    if not info.get("authors"):
        return True
    if not (info.get("abstract") or "").strip():
        return True
    if not info.get("arxiv") and not info.get("oa_pdf"):
        return True
    return False


def _s2_fill_later(folder, info: dict, publish) -> dict:
    """Retry Semantic Scholar only after the stub is already readable."""
    if not _s2_needed(info):
        return info
    before = _s2_snapshot(info)
    try:
        extra = s2_graph(int(info.get("corpusid") or 0), tries=2, timeout=10, backoff=True)
    except Exception:
        return info
    for key, value in extra.items():
        if value and not info.get(key):
            info[key] = value
    if _s2_snapshot(info) != before and publish is not None:
        publish(make_stub(info), "stub")
    return info


def _note_reason(meta, text: str):
    text = (text or "")[:300]
    prev = meta.get("reason")
    meta["reason"] = f"{prev}; {text}"[:500] if prev else text[:500]


def _try_download(meta, kind, fn):
    """Record one download. Returns the bytes, or None when this source should be skipped."""
    t0 = time.time()
    try:
        data = fn()
    except Exception as err:
        reason = getattr(err, "reason", None) or str(err)
        meta.setdefault("downloads", []).append({
            "kind": kind,
            "seconds": round(time.time() - t0, 3),
            "ok": False,
            "bytes": 0,
            "reason": str(reason)[:200],
        })
        meta["timings"]["download"] += time.time() - t0
        _note_reason(meta, f"{kind} failed: {reason}")
        return None
    meta.setdefault("downloads", []).append({
        "kind": kind,
        "seconds": round(time.time() - t0, 3),
        "ok": True,
        "bytes": len(data) if data else 0,
        "reason": None,
    })
    meta["timings"]["download"] += time.time() - t0
    return data


def _pdf_from_sources(info, meta, pdf_path, kinds):
    """Try each (kind, fn) in order. Write the first PDF that arrives."""
    for kind, fn in kinds:
        if fn is None:
            continue
        blob = _try_download(meta, kind, fn)
        if blob:
            pdf_path.write_bytes(blob)
            return True
    return False


def _fetch_and_parse(folder, info, meta, pdf_path, ocr, publish=None):
    arxiv = info.get("arxiv") or ""
    src = folder / "src"
    oa = info.get("oa_pdf") or ""
    oa_fn = (lambda: fetch_url(oa)) if oa else None
    if arxiv:
        blob = _try_download(meta, "eprint", lambda: arxiv_eprint(arxiv))
        if blob:
            kind = unpack_eprint(blob, src)
            if kind == "pdf":
                got = src / "source.pdf"
                if not got.is_file():
                    pdfs = sorted(src.rglob("*.pdf"))
                    got = pdfs[0] if pdfs else got
                if got.is_file():
                    pdf_path.write_bytes(got.read_bytes())
                return _ocr_route(folder, info, meta, pdf_path, ocr, "e-print is a PDF", publish)
            if kind == "tex":
                t = time.time()
                parsed = parse_tree(src, arxiv_id=arxiv)
                meta["timings"]["parse"] += time.time() - t
                if parsed["route"] == "pdf":
                    _note_reason(meta, parsed["reason"] or "pdfpages wrapper")
                    if _pdf_from_sources(info, meta, pdf_path, (
                        ("arxiv_pdf", lambda: arxiv_pdf(arxiv)),
                        ("oa_pdf", oa_fn),
                    )):
                        return _ocr_route(folder, info, meta, pdf_path, ocr, parsed["reason"], publish)
                    return "abstract", abstract_paper(info), pdf_path
                paper = parsed["paper"]
                paper["arxivId"] = arxiv
                apply_s2_fields(paper, info)
                t = time.time()
                meta["timings"]["katex"] += _apply_katex(paper)
                if publish:
                    publish(paper, "sections")
                t = time.time()
                materialize_figures(paper["blocks"], src, folder / "figures")
                meta["timings"]["figures"] += time.time() - t
                return "latex", paper, pdf_path
        if _pdf_from_sources(info, meta, pdf_path, (
            ("arxiv_pdf", lambda: arxiv_pdf(arxiv)),
            ("oa_pdf", oa_fn),
        )):
            return _ocr_route(folder, info, meta, pdf_path, ocr, meta.get("reason") or "no tex e-print", publish)
        _note_reason(meta, "no tex and pdf failed")
        return "abstract", abstract_paper(info), pdf_path

    if oa_fn is not None:
        if not _pdf_from_sources(info, meta, pdf_path, (("oa_pdf", oa_fn),)):
            _note_reason(meta, "open-access pdf failed")
            return "abstract", abstract_paper(info), pdf_path
        return _ocr_route(folder, info, meta, pdf_path, ocr, "no arXiv id", publish)
    return "abstract", abstract_paper(info), pdf_path


def _ocr_route(folder, info, meta, pdf_path, ocr, why: str, publish=None):
    if ocr is None:
        meta["reason"] = f"{why}; ocr not run in this process"
        paper = abstract_paper(info)
        paper["full"] = False
        return "abstract", paper, pdf_path
    if publish:
        publish(abstract_paper(info), "ocr")
    t = time.time()
    try:
        result = ocr(pdf_path, folder / "ocr")
    except Exception as err:
        meta["timings"]["ocr"] += time.time() - t
        meta["reason"] = f"ocr failed: {err}"[:500]
        return "abstract", abstract_paper(info), pdf_path
    meta["timings"]["ocr"] += float(result.get("seconds") or (time.time() - t))
    meta["ocr_gpu_s"] = float(meta.get("ocr_gpu_s") or 0) + float(result.get("gpu_s") or result.get("seconds") or 0)
    if result.get("chunks") is not None:
        meta["ocr_chunks"] = result.get("chunks")
    if result.get("engine"):
        meta["ocr_engine"] = result.get("engine")
    blocks = result.get("blocks") or []
    if result.get("error") and not blocks:
        meta["reason"] = str(result["error"])[:500]
        return "abstract", abstract_paper(info), pdf_path
    if not blocks:
        meta["reason"] = f"{why}; ocr returned no blocks"
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
    meta["reason"] = why
    return "ocr", paper, pdf_path
