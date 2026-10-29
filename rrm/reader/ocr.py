"""MinerU 2.5 OCR -> the same block schema as the LaTeX path.

One backend. The GPU function shells out to `mineru` with the vlm-auto-engine
(the 1.2B MinerU2.5 VLM). This module converts its content-list JSON, and can
turn a markdown fallback into blocks, without importing mineru.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

from rrm.reader.latex import finalize, parse_inlines, text_tokens

# MinerU2.5 (1.2B) formula CDM 95.77 on OmniDocBench v1.6, above olmOCR 88.10
# and Marker 85.24 (C report, 2026-10-28). Apache-2.0 with a revenue threshold
# that this prototype is under. One backend: vlm-auto-engine. On Linux, MinerU
# 2.7 selects the vLLM engine when the vllm package is installed, and the
# transformers engine otherwise (QA 2026-10-29: ~20 s/page without vLLM).
# The 2.7 CLI rejects the literal name vlm-vllm-engine.
MINERU_BACKEND = "vlm-auto-engine"
# Chunks of about 4 pages, at most one chunk per GPU container (up to 8).
# 15 pages -> 4, 4, 4, 3. A 4-page chunk is the unit that has to fit in CHUNK_TIMEOUT_S.
PAGES_PER_PART = 4
MAX_OCR_PARTS = 8
CHUNK_TIMEOUT_S = 120
CHUNK_RETRIES = 1  # one retry after the first attempt


def page_spans(n: int, pages_per_part: int = PAGES_PER_PART, max_parts: int = MAX_OCR_PARTS) -> list[tuple[int, int]]:
    """Half-open page ranges, in order, at most max_parts of them."""
    n = int(n)
    if n <= 0:
        return []
    pages_per_part = max(1, int(pages_per_part))
    max_parts = max(1, int(max_parts))
    parts = min(max_parts, (n + pages_per_part - 1) // pages_per_part)
    base, extra = divmod(n, parts)
    spans = []
    start = 0
    for i in range(parts):
        size = base + (1 if i < extra else 0)
        if size <= 0:
            continue
        spans.append((start, start + size))
        start += size
    return spans


def slice_pdf(pdf: Path, dest: Path, start: int, end: int) -> Path:
    """Write pages [start, end) to dest. end is exclusive."""
    import pymupdf

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    part = pymupdf.open()
    try:
        last = min(int(end), len(doc)) - 1
        if last >= int(start):
            part.insert_pdf(doc, from_page=int(start), to_page=last)
        part.save(dest)
    finally:
        part.close()
        doc.close()
    return dest


def pdf_page_count(pdf: Path) -> int | None:
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return None


def merge_ocr_parts(parts: list[dict]) -> list:
    """Concatenate per-chunk blocks in ascending start-page order and reassign ids.

    A failed chunk contributes its raw/failed placeholder and stays in page order.
    """
    ordered = sorted(parts, key=lambda part: int(part.get("start") or 0))
    blocks = []
    for part in ordered:
        for block in part.get("blocks") or []:
            item = {k: v for k, v in block.items() if k not in ("id", "sents")}
            blocks.append(item)
    if not blocks:
        return []
    return finalize(blocks)


def failed_chunk(start: int, end: int, reason: str, seconds: float = 0, attempts: int = 1, engine: str = "") -> dict:
    """One raw block covering pages [start, end) that OCR did not return."""
    start, end = int(start), int(end)
    span = f"{start + 1}-{end}" if end > start + 1 else str(max(start + 1, end))
    note = f"OCR failed for pages {span}: {reason}"
    return {
        "start": start,
        "end": end,
        "failed": True,
        "reason": str(reason)[:300],
        "seconds": round(float(seconds or 0), 3),
        "attempts": int(attempts or 1),
        "engine": engine or "",
        "page_count": max(0, end - start),
        "blocks": [{
            "kind": "p",
            "raw": True,
            "failed": True,
            "pages": [start, end],
            "inlines": text_tokens(note),
        }],
    }


def chunk_summary(row: dict) -> dict:
    out = {
        "start": row.get("start"),
        "end": row.get("end"),
        "seconds": row.get("seconds"),
        "engine": row.get("engine") or "",
        "failed": bool(row.get("failed")),
        "attempts": row.get("attempts") or 1,
        "reason": row.get("reason"),
    }
    if "vllm_installed" in row:
        out["vllm_installed"] = bool(row.get("vllm_installed"))
    return out


def format_chunk_timings(chunks) -> str:
    """`start-end:seconds:engine:ok|fail:attempts` for the bench column."""
    bits = []
    for row in chunks or []:
        state = "fail" if row.get("failed") else "ok"
        engine = row.get("engine") or "?"
        bits.append(f"{row.get('start')}-{row.get('end')}:{row.get('seconds')}:{engine}:{state}:{row.get('attempts')}")
    return ";".join(bits)


_ENGINE_LINE = re.compile(r"Using ([A-Za-z0-9_-]+) as the inference engine", re.I)


def engine_from_log(log: str) -> str:
    """MinerU logs `Using vllm-engine as the inference engine for VLM.` (or transformers)."""
    found = _ENGINE_LINE.findall(log or "")
    if found:
        return found[-1]
    low = (log or "").lower()
    if "vllm" in low and "transformer" not in low:
        return "vllm"
    if "transformer" in low:
        return "transformers"
    return "unknown"


def _kill_group(pid: int):
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _reset_dir(out_dir: Path):
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)


def assemble_ocr(parts: list[dict], wall_s: float, page_count: int | None = None) -> dict:
    """Merge chunk results. Every chunk failed -> empty blocks plus an error; otherwise page order."""
    chunks = [chunk_summary(row) for row in parts]
    engines = []
    for row in chunks:
        name = str(row.get("engine") or "")
        if name and name not in engines and name != "unknown":
            engines.append(name)
    if not engines:
        engines = ["unknown"] if parts else []
    engine = engines[0] if len(engines) == 1 else "mixed:" + ",".join(engines)
    gpu_s = sum(float(row.get("seconds") or 0) for row in parts)
    pages = page_count
    if pages is None:
        pages = sum(int(row.get("page_count") or 0) for row in parts)
    base = {
        "seconds": round(float(wall_s), 3),
        "gpu_s": round(gpu_s, 3),
        "page_count": pages,
        "chunks": chunks,
        "engine": engine,
    }
    if parts and all(row.get("failed") for row in parts):
        reason = "; ".join(str(row.get("reason") or "failed") for row in parts)
        base["blocks"] = []
        base["error"] = f"all ocr chunks failed: {reason}"[:500]
        return base
    base["blocks"] = merge_ocr_parts(parts)
    base["error"] = None
    return base


def run_mineru(pdf: Path, out_dir: Path, end_page: int | None = None, timeout: int = CHUNK_TIMEOUT_S) -> str:
    """Run the mineru CLI. Returns the combined log. Raises TimeoutError or RuntimeError.

    The process group is killed when the timeout fires so a hung vLLM child cannot
    hold the GPU until the Modal function timeout.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "mineru", "-p", str(pdf), "-o", str(out_dir),
        "-b", MINERU_BACKEND, "-l", "en", "-m", "ocr",
        "-f", "true", "-t", "true",
    ]
    if end_page is not None:
        cmd += ["-e", str(int(end_page))]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        log, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        try:
            proc.communicate(timeout=5)
        except Exception:
            proc.kill()
        raise TimeoutError(f"mineru exceeded {timeout}s")
    log = log or ""
    if proc.returncode != 0:
        _kill_group(proc.pid)
        tail = log[-800:]
        raise RuntimeError(tail or "mineru failed")
    return log


def run_chunk(pdf: Path, out_dir: Path, *, timeout: int = CHUNK_TIMEOUT_S, retries: int = CHUNK_RETRIES, run=None) -> dict:
    """One MinerU attempt plus `retries` extra. `run` returns the log text or raises."""
    run = run or run_mineru
    started = time.time()
    last = "mineru failed"
    log = ""
    attempts = 0
    for _ in range(max(1, int(retries)) + 1):
        attempts += 1
        _reset_dir(Path(out_dir))
        try:
            log = run(pdf, Path(out_dir), timeout=timeout)
            return {
                "ok": True,
                "engine": engine_from_log(log),
                "attempts": attempts,
                "seconds": round(time.time() - started, 3),
                "error": None,
                "log": log or "",
            }
        except Exception as err:
            last = str(err)[:300] or "mineru failed"
            log = last
    return {
        "ok": False,
        "engine": engine_from_log(log),
        "attempts": attempts,
        "seconds": round(time.time() - started, 3),
        "error": last,
        "log": log,
    }


def _find_content_list(out_dir: Path) -> list | None:
    files = sorted(out_dir.rglob("*content_list*.json"))
    if not files:
        return None
    data = json.loads(files[0].read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("content_list"), list):
        return data["content_list"]
    return None


def _find_markdown(out_dir: Path) -> str:
    files = sorted(out_dir.rglob("*.md"))
    if not files:
        return ""
    return files[0].read_text(encoding="utf-8", errors="replace")


def _strip_math(text: str) -> str:
    t = text.strip()
    for a, b in (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)")):
        if t.startswith(a) and t.endswith(b) and len(t) > len(a) + len(b):
            return t[len(a):-len(b)].strip()
    return t


def _html_rows(html: str):
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
        parsed = []
        for c in cells:
            plain = re.sub(r"<[^>]+>", " ", c)
            plain = re.sub(r"\s+", " ", plain).strip()
            parsed.append(text_tokens(plain))
        if parsed:
            rows.append(parsed)
    return rows


def blocks_from_content_list(items: list) -> list:
    blocks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = (item.get("type") or "").lower()
        if kind in ("header", "footer", "page_number", "page_footnote"):
            continue
        if kind in ("text", "title", "paragraph"):
            text = item.get("text") or item.get("content") or ""
            level = item.get("text_level") or (1 if kind == "title" else 0)
            if level:
                blocks.append({
                    "kind": "h", "level": int(level), "unnumbered": False,
                    "number": None, "inlines": parse_inlines(str(text), {}),
                })
            elif str(text).strip():
                blocks.append({"kind": "p", "inlines": parse_inlines(str(text), {})})
        elif kind in ("equation", "formula", "interline_equation"):
            tex = _strip_math(str(item.get("text") or item.get("content") or ""))
            blocks.append({
                "kind": "eq", "tex": tex, "env": "display", "katex_ok": None,
                "source": "ocr", "raw": False,
            })
        elif kind in ("image", "figure", "chart"):
            cap = item.get("image_caption") or item.get("caption") or []
            if isinstance(cap, list):
                cap = " ".join(str(c) for c in cap)
            img = item.get("img_path") or ""
            blocks.append({"kind": "fig", "images": [img] if img else [], "caption": parse_inlines(str(cap), {})})
        elif kind == "table":
            cap = item.get("table_caption") or []
            if isinstance(cap, list):
                cap = " ".join(str(c) for c in cap)
            rows = _html_rows(str(item.get("table_body") or ""))
            if not rows and item.get("table_body"):
                rows = [[text_tokens(re.sub(r"<[^>]+>", " ", str(item["table_body"])))]]
            blocks.append({
                "kind": "table",
                "head": rows[:1],
                "body": rows[1:],
                "caption": parse_inlines(str(cap), {}),
            })
        elif kind == "list":
            raw_items = item.get("list_items") or []
            items_inl = [parse_inlines(str(x), {}) for x in raw_items if str(x).strip()]
            if items_inl:
                blocks.append({"kind": "list", "items": items_inl})
            elif item.get("text"):
                blocks.append({"kind": "p", "inlines": parse_inlines(str(item["text"]), {})})
        else:
            text = item.get("text") or item.get("content") or ""
            if str(text).strip():
                blocks.append({"kind": "p", "raw": True, "inlines": text_tokens(str(text).strip())})
    for b in blocks:
        if b.get("kind") == "eq":
            b["source"] = "ocr"
    return finalize(blocks)


def blocks_from_markdown(md: str) -> list:
    blocks = []
    i, n = 0, len(md)
    while i < n:
        if md.startswith("$$", i):
            end = md.find("$$", i + 2)
            if end < 0:
                blocks.append({"kind": "p", "raw": True, "inlines": text_tokens(md[i:].strip())})
                break
            blocks.append({
                "kind": "eq", "tex": md[i + 2:end].strip(), "env": "display",
                "katex_ok": None, "source": "ocr", "raw": False,
            })
            i = end + 2
            continue
        line_end = md.find("\n", i)
        if line_end < 0:
            line_end = n
        line = md[i:line_end]
        if line.startswith("#"):
            hashes = len(line) - len(line.lstrip("#"))
            blocks.append({
                "kind": "h", "level": min(hashes, 4), "unnumbered": False,
                "number": None, "inlines": parse_inlines(line.lstrip("#").strip(), {}),
            })
            i = line_end + 1
            continue
        # paragraph up to a blank line or $$ or heading
        j = i
        while j < n:
            if md.startswith("$$", j) or (j == 0 or md[j - 1] == "\n") and md[j] == "#":
                break
            if md.startswith("\n\n", j):
                break
            j += 1
        chunk = md[i:j].strip()
        if chunk:
            blocks.append({"kind": "p", "inlines": parse_inlines(chunk, {})})
        i = j + (2 if md.startswith("\n\n", j) else 0)
        if i == j:
            i += 1
    return finalize(blocks)


def blocks_from_mineru_dir(out_dir: Path) -> list:
    items = _find_content_list(out_dir)
    if items is not None:
        return blocks_from_content_list(items)
    md = _find_markdown(out_dir)
    if md.strip():
        return blocks_from_markdown(md)
    raise RuntimeError("mineru wrote no content_list or markdown")
