"""SAM 3.1 client (Meta Model API, model sam-3.1).

POST https://api.meta.ai/v1/responses with a noun phrase plus a page image.
The key is MODEL_API_KEY. No key, or any API error, returns no crops and
leaves the parse untouched. $0.0025 per image (one request, one phrase).

Output grammar: `<0f>0<|box;x1=;y1=;x2=;y2=;w=;h=|><|mask;...|>`. Boxes are
source pixels of the rendered page. Masks are kept beside the crop.
"""

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.meta.ai/v1/responses"
MODEL = "sam-3.1"
USD_PER_IMAGE = 0.0025
# "figure" and "equation" found nothing on Attention pages; "diagram" found every panel
# and "table" finds tables (QA 2026-10-29). Those two phrases only.
PHRASES = ("diagram", "table")
# One viewport. Page indexes at or above MAX_CROP_INDEX are ignored.
MAX_CROP_PAGES = 4
MAX_CROP_INDEX = 30
_TOK = re.compile(r"<\|(box|mask);(.*?)\|>", re.S)


def api_key() -> str:
    return os.environ.get("MODEL_API_KEY") or ""


def _fields(blob: str) -> dict:
    out = {}
    for part in blob.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def parse_sam_text(text: str) -> list[dict]:
    """Boxes (and mask payloads) from one image's output_text. Empty text -> []."""
    if not text or not text.strip():
        return []
    hits = []
    current = None
    for kind, blob in _TOK.findall(text):
        fields = _fields(blob)
        if kind == "box":
            try:
                current = {
                    "x1": int(fields["x1"]),
                    "y1": int(fields["y1"]),
                    "x2": int(fields["x2"]),
                    "y2": int(fields["y2"]),
                    "w": int(fields.get("w") or 0),
                    "h": int(fields.get("h") or 0),
                }
            except (KeyError, ValueError):
                current = None
                continue
            if "c" in fields:
                try:
                    current["c"] = float(fields["c"])
                except ValueError:
                    pass
            hits.append(current)
        elif kind == "mask" and current is not None:
            data = fields.get("data") or ""
            current["mask"] = data
            current = None
    return hits


def _output_text(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        return _text_from_obj(json.loads(raw))
    parts = []
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            ev = json.loads(data)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "response.output_text.delta":
            parts.append(ev.get("delta") or "")
        elif ev.get("type") == "response.completed":
            extra = _text_from_obj(ev.get("response") or {})
            if extra and not parts:
                parts.append(extra)
    return "".join(parts)


def _text_from_obj(obj: dict) -> str:
    if not isinstance(obj, dict):
        return ""
    chunks = []
    for item in obj.get("output") or []:
        for part in item.get("content") or []:
            if part.get("type") in ("output_text", "text") and part.get("text"):
                chunks.append(part["text"])
    if chunks:
        return "".join(chunks)
    if isinstance(obj.get("output_text"), str):
        return obj["output_text"]
    return ""


def segment_png(png: bytes, phrase: str, key: str, timeout: int = 90) -> list[dict]:
    """One image, one noun phrase. Raises urllib.error.HTTPError or RuntimeError."""
    data_url = "data:image/png;base64," + base64.standard_b64encode(png).decode("ascii")
    payload = {
        "model": MODEL,
        "stream": True,
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
        "input": [{
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": phrase},
                {"type": "input_image", "image_url": data_url},
            ],
        }],
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    # The API answers 404 model_not_found on a large share of valid sam-3.1 calls
    # (4 of 5 in a row, 2026-10-29), so 404, 429 and 5xx are retried.
    delay = 1.0
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as err:
            if attempt == 5 or not (err.code in (404, 429) or err.code >= 500):
                raise
            time.sleep(delay)
            delay = min(delay * 2, 8)
    return parse_sam_text(_output_text(raw))


def parse_pages(text: str, cap: int = MAX_CROP_PAGES, max_index: int = MAX_CROP_INDEX) -> list[int]:
    """`0,2,4-6` -> unique in-range page indexes, capped."""
    pages = []
    for bit in str(text or "").replace(" ", "").split(","):
        if not bit:
            continue
        if "-" in bit:
            left, right = bit.split("-", 1)
            if left.isdigit() and right.isdigit():
                lo, hi = int(left), int(right)
                if lo > hi:
                    lo, hi = hi, lo
                pages.extend(range(lo, hi + 1))
            continue
        if bit.isdigit():
            pages.append(int(bit))
    out = []
    for n in pages:
        if 0 <= n < max_index and n not in out:
            out.append(n)
        if len(out) >= cap:
            break
    return out


def render_pages(pdf: Path, max_pages: int = 30, dpi: int = 150):
    import pymupdf
    doc = pymupdf.open(pdf)
    n = min(len(doc), max_pages)
    for i in range(n):
        pix = doc[i].get_pixmap(dpi=dpi)
        yield i, pix.tobytes("png"), pix.width, pix.height
    doc.close()


def _crop(png: bytes, box: dict, dest: Path) -> bool:
    import pymupdf
    try:
        pix = pymupdf.Pixmap(png)
        x1 = max(0, min(box["x1"], pix.width - 1))
        y1 = max(0, min(box["y1"], pix.height - 1))
        x2 = max(x1 + 1, min(box["x2"] + 1, pix.width))
        y2 = max(y1 + 1, min(box["y2"] + 1, pix.height))
        rect = pymupdf.IRect(x1, y1, x2, y2)
        # Pixmap(pix, IRect) is not a pymupdf constructor; copy the region instead.
        out = pymupdf.Pixmap(pix.colorspace, rect, pix.alpha)
        out.copy(pix, rect)
        out.set_origin(0, 0)
        out.save(dest)
    except Exception:
        return False
    return True


def _load_index(crops_dir: Path) -> dict:
    path = crops_dir / "index.json"
    if not path.is_file():
        return {"crops": [], "images": 0, "cost_usd": 0.0, "error": None, "pages": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"crops": [], "images": 0, "cost_usd": 0.0, "error": None, "pages": 0}
    data.setdefault("crops", [])
    return data


def render_selected(pdf: Path, pages: list[int], dpi: int = 150) -> dict[int, bytes]:
    import pymupdf

    doc = pymupdf.open(pdf)
    out = {}
    try:
        n = len(doc)
        for i in pages:
            if i < 0 or i >= n:
                continue
            pix = doc[i].get_pixmap(dpi=dpi)
            out[i] = pix.tobytes("png")
    finally:
        doc.close()
    return out


def segment_pages(pdf: Path, crops_dir: Path, pages: list[int], phrases=PHRASES, max_pages: int = MAX_CROP_PAGES) -> dict:
    """Crops for the pages in view. Parallel phrase calls. Never raises."""
    key = api_key()
    crops_dir.mkdir(parents=True, exist_ok=True)
    wanted = []
    for n in pages:
        n = int(n)
        if 0 <= n < MAX_CROP_INDEX and n not in wanted:
            wanted.append(n)
        if len(wanted) >= max_pages:
            break
    previous = _load_index(crops_dir)
    result = {
        "crops": [],
        "images": int(previous.get("images") or 0),
        "cost_usd": 0.0,
        "error": previous.get("error"),
        "pages": len(wanted),
        # Pages SAM already answered, even with zero hits. Without this a page with no
        # diagram looked unfinished and every /crops poll re-ran SAM (QA 2026-10-29: 96 images for 2 pages).
        "done_pages": set(int(p) for p in (previous.get("done_pages") or [])),
    }
    kept = [row for row in (previous.get("crops") or []) if row.get("page") not in wanted]
    if not key:
        result["error"] = "no MODEL_API_KEY"
        result["crops"] = kept
        _write_index(crops_dir, kept, result)
        return result
    if not pdf.is_file():
        result["error"] = "no pdf"
        result["crops"] = kept
        _write_index(crops_dir, kept, result)
        return result
    try:
        pngs = render_selected(pdf, wanted)
    except Exception as err:
        result["error"] = f"render failed: {err}"
        result["crops"] = kept
        _write_index(crops_dir, kept, result)
        return result
    tasks = [(page, phrase) for page in pngs for phrase in phrases]
    fresh = []

    def _one(task):
        page, phrase = task
        try:
            hits = segment_png(pngs[page], phrase, key)
            return page, phrase, hits, None
        except urllib.error.HTTPError as err:
            return page, phrase, [], f"sam http {err.code}"
        except Exception as err:
            return page, phrase, [], f"sam error: {err}"

    if tasks:
        from concurrent.futures import ThreadPoolExecutor
        workers = min(8, len(tasks))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_one, tasks))
    else:
        rows = []
    failed_pages = {page for page, _, _, err in rows if err}
    result["done_pages"] |= {page for page in pngs if page not in failed_pages}
    for page, phrase, hits, err in rows:
        result["images"] += 1
        if err:
            result["error"] = err
            if err in ("sam http 401", "sam http 403"):
                break
            continue
        for n, hit in enumerate(hits):
            name = f"p{page}_{phrase}_{n}.png"
            if _crop(pngs[page], hit, crops_dir / name):
                row = {
                    "page": page,
                    "phrase": phrase,
                    "bbox": [hit["x1"], hit["y1"], hit["x2"], hit["y2"]],
                    "file": name,
                }
                if hit.get("c") is not None:
                    row["c"] = hit["c"]
                if hit.get("mask"):
                    mask_name = f"p{page}_{phrase}_{n}.mask.txt"
                    (crops_dir / mask_name).write_text(hit["mask"], encoding="utf-8")
                    row["mask"] = mask_name
                fresh.append(row)
    result["crops"] = kept + fresh
    result["cost_usd"] = round(result["images"] * USD_PER_IMAGE, 6)
    _write_index(crops_dir, result["crops"], result)
    return result


def segment_pdf(pdf: Path, crops_dir: Path, phrases=PHRASES, max_pages: int = 30) -> dict:
    """Render up to max_pages and ask SAM. Always returns a dict; errors do not raise."""
    key = api_key()
    crops_dir.mkdir(parents=True, exist_ok=True)
    result = {"crops": [], "images": 0, "cost_usd": 0.0, "error": None, "pages": 0}
    if not key:
        result["error"] = "no MODEL_API_KEY"
        _write_index(crops_dir, [], result)
        return result
    if not pdf.is_file():
        result["error"] = "no pdf"
        _write_index(crops_dir, [], result)
        return result
    try:
        pages = list(render_pages(pdf, max_pages=max_pages))
    except Exception as err:
        result["error"] = f"render failed: {err}"
        _write_index(crops_dir, [], result)
        return result
    result["pages"] = len(pages)
    index = []
    for page_i, png, _w, _h in pages:
        for phrase in phrases:
            try:
                hits = segment_png(png, phrase, key)
            except urllib.error.HTTPError as err:
                result["error"] = f"sam http {err.code}"
                if err.code in (401, 403):
                    _write_index(crops_dir, index, result)
                    return result
                continue
            except Exception as err:
                result["error"] = f"sam error: {err}"
                continue
            result["images"] += 1
            for n, hit in enumerate(hits):
                name = f"p{page_i}_{phrase}_{n}.png"
                dest = crops_dir / name
                if _crop(png, hit, dest):
                    row = {
                        "page": page_i,
                        "phrase": phrase,
                        "bbox": [hit["x1"], hit["y1"], hit["x2"], hit["y2"]],
                        "file": name,
                    }
                    if hit.get("c") is not None:
                        row["c"] = hit["c"]
                    if hit.get("mask"):
                        mask_name = f"p{page_i}_{phrase}_{n}.mask.txt"
                        (crops_dir / mask_name).write_text(hit["mask"], encoding="utf-8")
                        row["mask"] = mask_name
                    index.append(row)
    result["crops"] = index
    result["cost_usd"] = round(result["images"] * USD_PER_IMAGE, 6)
    _write_index(crops_dir, index, result)
    return result


def _write_index(crops_dir: Path, index: list, result: dict):
    payload = {
        "crops": index,
        "images": result["images"],
        "cost_usd": round(result["images"] * USD_PER_IMAGE, 6),
        "error": result["error"],
        "pages": result["pages"],
        "done_pages": sorted(int(p) for p in (result.get("done_pages") or [])),
    }
    (crops_dir / "index.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
