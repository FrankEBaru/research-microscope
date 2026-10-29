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
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.meta.ai/v1/responses"
MODEL = "sam-3.1"
USD_PER_IMAGE = 0.0025
PHRASES = ("figure", "table", "equation")
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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError:
        raise
    return parse_sam_text(_output_text(raw))


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
    doc = pymupdf.open(stream=png, filetype="png")
    pix = doc[0].get_pixmap()
    x1 = max(0, min(box["x1"], pix.width - 1))
    y1 = max(0, min(box["y1"], pix.height - 1))
    x2 = max(x1 + 1, min(box["x2"] + 1, pix.width))
    y2 = max(y1 + 1, min(box["y2"] + 1, pix.height))
    try:
        clipped = pymupdf.Pixmap(pix, pymupdf.IRect(x1, y1, x2, y2))
        clipped.save(dest)
    except Exception:
        doc.close()
        return False
    doc.close()
    return True


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
    }
    (crops_dir / "index.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
