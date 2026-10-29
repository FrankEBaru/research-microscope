"""MinerU 2.5 OCR -> the same block schema as the LaTeX path.

One backend. The GPU function shells out to `mineru` with the vlm-auto-engine
(the 1.2B MinerU2.5 VLM). This module converts its content-list JSON, and can
turn a markdown fallback into blocks, without importing mineru.
"""

import json
import re
import subprocess
from pathlib import Path

from rrm.reader.latex import finalize, parse_inlines, text_tokens

# MinerU2.5 (1.2B) formula CDM 95.77 on OmniDocBench v1.6, above olmOCR 88.10
# and Marker 85.24 (C report, 2026-10-28). Apache-2.0 with a revenue threshold
# that this prototype is under. vlm-auto-engine is that VLM, not the older pipeline.
MINERU_BACKEND = "vlm-auto-engine"


def run_mineru(pdf: Path, out_dir: Path, end_page: int | None = None) -> Path:
    """Run the mineru CLI. Returns the output directory. Raises RuntimeError with the tail of stderr."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "mineru", "-p", str(pdf), "-o", str(out_dir),
        "-b", MINERU_BACKEND, "-l", "en", "-m", "ocr",
        "-f", "true", "-t", "true",
    ]
    if end_page is not None:
        cmd += ["-e", str(int(end_page))]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(tail or "mineru failed")
    return out_dir


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
