"""MinerU 2.5 OCR -> the same block schema as the LaTeX path.

One backend. The GPU function shells out to `mineru` with the vlm-auto-engine
(the 1.2B MinerU2.5 VLM). This module converts its content-list JSON, and can
turn a markdown fallback into blocks, without importing mineru.
"""

import json
import re
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
# ~4 pages per container. 15 pages -> 4 chunks; longer PDFs use at most 8.
PAGES_PER_PART = 4
MAX_OCR_PARTS = 8
# One attempt is killed at 120s so a hung chunk cannot sit for 13 min (QA 2026-10-29).
CHUNK_TIMEOUT_S = 120
CHUNK_TRIES = 2


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


def _failed_chunk_block(part: dict) -> dict:
    start = int(part.get("start") or 0)
    end = part.get("end")
    span = f"{start}-{int(end)}" if end is not None else str(start)
    reason = str(part.get("error") or "ocr failed")[:180]
    return {
        "kind": "p",
        "raw": True,
        "failed": True,
        "inlines": text_tokens(f"[ocr failed pages {span}: {reason}]"),
    }


def merge_ocr_parts(parts: list[dict]) -> list:
    """Concatenate per-chunk blocks in page order. A failed chunk becomes one raw block."""
    ordered = sorted(parts, key=lambda part: int(part.get("start") or 0))
    blocks = []
    for part in ordered:
        if part.get("failed") or part.get("ok") is False:
            blocks.append(_failed_chunk_block(part))
            continue
        for block in part.get("blocks") or []:
            item = {k: v for k, v in block.items() if k not in ("id", "sents")}
            blocks.append(item)
    if not blocks:
        return []
    return finalize(blocks)


class MineruError(RuntimeError):
    def __init__(self, message: str, engine: str = "unknown"):
        super().__init__(message)
        self.engine = engine


def engine_from_log(log: str) -> str:
    """Which VLM engine MinerU actually selected: vllm, transformers, or unknown."""
    low = (log or "").lower()
    named = re.search(r"(?:using|engine)[=:\s]+(vllm[\w.-]*|transformers)", low)
    if named:
        return "vllm" if named.group(1).startswith("vllm") else "transformers"
    if re.search(r"vllm[-_ ]engine|vlm-vllm", low):
        return "vllm"
    if re.search(r"transformers engine|vlm-transformers", low):
        return "transformers"
    has_vllm = "vllm" in low
    has_tf = "transformers" in low
    if has_vllm and not has_tf:
        return "vllm"
    if has_tf and not has_vllm:
        return "transformers"
    return "unknown"


def _proc_text(err: subprocess.TimeoutExpired) -> str:
    def dec(value):
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value)

    return dec(err.stderr) + "\n" + dec(err.stdout)


def run_mineru(pdf: Path, out_dir: Path, end_page: int | None = None, timeout: int = CHUNK_TIMEOUT_S):
    """Run the mineru CLI. Returns (output dir, engine). Raises MineruError with the tail of the log."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "mineru", "-p", str(pdf), "-o", str(out_dir),
        "-b", MINERU_BACKEND, "-l", "en", "-m", "ocr",
        "-f", "true", "-t", "true",
    ]
    if end_page is not None:
        cmd += ["-e", str(int(end_page))]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as err:
        engine = engine_from_log(_proc_text(err))
        raise MineruError(f"mineru timed out after {timeout}s", engine) from err
    log = (proc.stderr or "") + "\n" + (proc.stdout or "")
    engine = engine_from_log(log)
    if proc.returncode != 0:
        tail = (log or "mineru failed")[-800:]
        raise MineruError(tail or "mineru failed", engine)
    return out_dir, engine


def _mineru_runner(pdf, out_dir, timeout: int) -> str:
    _path, engine = run_mineru(Path(pdf), Path(out_dir), timeout=timeout)
    return engine


def _log_chunk(row: dict):
    span = f"{row.get('start')}-{row.get('end')}"
    print(
        f"mineru chunk={span} engine={row.get('engine')} seconds={row.get('seconds')} "
        f"ok={bool(row.get('ok'))} attempts={row.get('attempts')}",
        flush=True,
    )


def run_chunk(
    pdf,
    out_dir,
    start: int,
    end: int | None = None,
    *,
    timeout: int = CHUNK_TIMEOUT_S,
    tries: int = CHUNK_TRIES,
    runner=None,
    load_blocks=None,
) -> dict:
    """One chunk, `tries` attempts (the first plus one retry). A failed chunk stays in the merge."""
    runner = runner or _mineru_runner
    load_blocks = load_blocks or blocks_from_mineru_dir
    last = "ocr failed"
    engine = "unknown"
    elapsed = 0.0
    attempts = 0
    for _attempt in range(max(1, int(tries))):
        attempts += 1
        t = time.time()
        try:
            engine = runner(pdf, out_dir, timeout) or engine
            blocks = load_blocks(Path(out_dir))
            elapsed += time.time() - t
            row = {
                "start": int(start),
                "end": None if end is None else int(end),
                "blocks": blocks,
                "seconds": round(elapsed, 3),
                "engine": engine or "unknown",
                "ok": True,
                "failed": False,
                "attempts": attempts,
            }
            _log_chunk(row)
            return row
        except Exception as err:
            elapsed += time.time() - t
            last = str(err)[:300] or "ocr failed"
            engine = getattr(err, "engine", None) or engine
    row = {
        "start": int(start),
        "end": None if end is None else int(end),
        "blocks": [],
        "seconds": round(elapsed, 3),
        "engine": engine or "unknown",
        "ok": False,
        "failed": True,
        "attempts": attempts,
        "error": last,
    }
    _log_chunk(row)
    return row


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
