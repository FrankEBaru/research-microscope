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


MISSING_KEY = "no MODEL_API_KEY"
# PDF points. A header logo is about 30 pt; a panel or table is larger.
_MIN_REGION = 36.0
_MIN_AREA = 4000.0  # pt^2. Header logos survive the side check; a merged panel does not stay this small.
_IMAGE_GAP = 8.0


def api_key() -> str:
    return os.environ.get("MODEL_API_KEY") or ""


def key_blocks_crops(index_error, key: str) -> bool:
    """A stored missing-key error skips /crops only while the key is still absent."""
    return index_error == MISSING_KEY and not key


def segmented_pages(index: dict, key: str) -> set[int]:
    """Pages that do not need another SAM call.

    A stored `no MODEL_API_KEY` is not a finished page once the key exists.
    Crop rows from an earlier success still count.
    """
    pages = set()
    if index.get("error") != MISSING_KEY or not key:
        for n in index.get("done_pages") or []:
            pages.add(int(n))
    for row in index.get("crops") or []:
        if isinstance(row, dict) and row.get("page") is not None:
            pages.add(int(row["page"]))
    return pages


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


def _box4(raw):
    if raw is None:
        return None
    if hasattr(raw, "x0"):
        return [float(raw.x0), float(raw.y0), float(raw.x1), float(raw.y1)]
    try:
        if len(raw) < 4:
            return None
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None


def _clip_box(box, width, height):
    box = _box4(box)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(float(width), x1), min(float(height), y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return [x0, y0, x1, y1]


def _union_rects(rects, gap: float):
    rects = [list(r) for r in rects]
    changed = True
    while changed and rects:
        changed = False
        nxt = []
        used = [False] * len(rects)
        for i, a in enumerate(rects):
            if used[i]:
                continue
            used[i] = True
            x0, y0, x1, y1 = a
            grew = True
            while grew:
                grew = False
                for j, b in enumerate(rects):
                    if used[j]:
                        continue
                    if b[0] <= x1 + gap and b[2] >= x0 - gap and b[1] <= y1 + gap and b[3] >= y0 - gap:
                        used[j] = True
                        x0, y0 = min(x0, b[0]), min(y0, b[1])
                        x1, y1 = max(x1, b[2]), max(y1, b[3])
                        grew = True
                        changed = True
            nxt.append([x0, y0, x1, y1])
        rects = nxt
    return rects


def _drop_contained(rects, frac: float = 0.85):
    keep = []
    for i, a in enumerate(rects):
        area = (a[2] - a[0]) * (a[3] - a[1])
        if area <= 0:
            continue
        inside = False
        for j, b in enumerate(rects):
            if i == j:
                continue
            iw = min(a[2], b[2]) - max(a[0], b[0])
            ih = min(a[3], b[3]) - max(a[1], b[1])
            inter = max(0.0, iw) * max(0.0, ih)
            bigger = (b[2] - b[0]) * (b[3] - b[1]) > area
            if bigger and inter >= frac * area:
                inside = True
                break
        if not inside:
            keep.append(a)
    return keep


def _big_enough(box) -> bool:
    return box[2] - box[0] >= _MIN_REGION and box[3] - box[1] >= _MIN_REGION


def _area(box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap_frac(box, other) -> float:
    area = _area(box)
    if area <= 0:
        return 0.0
    iw = min(box[2], other[2]) - max(box[0], other[0])
    ih = min(box[3], other[3]) - max(box[1], other[1])
    return max(0.0, iw) * max(0.0, ih) / area


def page_regions(page) -> list[dict]:
    """Figure and table boxes in PDF points, from images, vector clusters, and tables.

    SAM's noun phrases return an empty lane on line drawings, alignment plots,
    and some tables. These boxes are the crop when that happens. Nearby image
    tiles (a grid) become one panel.
    """
    width, height = float(page.rect.width), float(page.rect.height)
    images = []
    for info in page.get_image_info() or []:
        box = _clip_box(info.get("bbox"), width, height)
        if box is not None:
            images.append(box)
    figures = [b for b in _union_rects(images, _IMAGE_GAP) if _big_enough(b) and _area(b) >= _MIN_AREA]
    tables = []
    try:
        found = page.find_tables()
        raw_tables = list(getattr(found, "tables", None) or [])
    except Exception:
        raw_tables = []
    for table in raw_tables:
        box = _clip_box(getattr(table, "bbox", None), width, height)
        if box is not None and _big_enough(box):
            tables.append(box)
    tables = _drop_contained(tables)
    # Vector clusters add axis labels around a raster panel. Skip a cluster that
    # is really the rules of a table, and skip header-sized leftovers.
    for cluster in page.cluster_drawings() or []:
        box = _clip_box(cluster, width, height)
        if box is None or not _big_enough(box) or _area(box) < _MIN_AREA:
            continue
        if _area(box) > 0.85 * width * height:
            continue
        if any(_overlap_frac(box, table) >= 0.5 for table in tables):
            continue
        figures.append(box)
    figures = [b for b in _drop_contained(_union_rects(figures, 4.0)) if _big_enough(b) and _area(b) >= _MIN_AREA]
    # Image tiles inside a table (result thumbnails) are the table, not a second figure.
    figures = [b for b in figures if not any(_overlap_frac(b, table) >= 0.5 for table in tables)]
    # A table already covered by a figure box would be a second crop of the same ink.
    kept_tables = []
    for box in tables:
        area = (box[2] - box[0]) * (box[3] - box[1])
        covered = False
        for fig in figures:
            iw = min(box[2], fig[2]) - max(box[0], fig[0])
            ih = min(box[3], fig[3]) - max(box[1], fig[1])
            if max(0.0, iw) * max(0.0, ih) >= 0.6 * area:
                covered = True
                break
        if not covered:
            kept_tables.append(box)
    rows = [{"phrase": "diagram", "bbox": b} for b in figures]
    rows += [{"phrase": "table", "bbox": b} for b in kept_tables]
    rows.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
    return rows


def _pdf_hits(pdf: Path, page_index: int, png: bytes) -> list[dict]:
    """PDF figure/table boxes in the rendered page's pixels. [] if the page has none."""
    import pymupdf

    try:
        doc = pymupdf.open(pdf)
    except Exception:
        return []
    try:
        if page_index < 0 or page_index >= len(doc):
            return []
        page = doc[page_index]
        pix = pymupdf.Pixmap(png)
        if page.rect.width <= 0 or page.rect.height <= 0:
            return []
        sx = pix.width / float(page.rect.width)
        sy = pix.height / float(page.rect.height)
        hits = []
        for region in page_regions(page):
            x0, y0, x1, y1 = region["bbox"]
            hit = {
                "x1": max(0, int(x0 * sx)),
                "y1": max(0, int(y0 * sy)),
                "x2": min(pix.width - 1, max(0, int(round(x1 * sx)) - 1)),
                "y2": min(pix.height - 1, max(0, int(round(y1 * sy)) - 1)),
                "phrase": region["phrase"],
                "source": "pdf",
            }
            if hit["x2"] > hit["x1"] and hit["y2"] > hit["y1"]:
                hits.append(hit)
        return hits
    except Exception:
        return []
    finally:
        doc.close()


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
        result["error"] = MISSING_KEY
        result["crops"] = kept
        _write_index(crops_dir, kept, result)
        return result
    # A previous run stored the missing key. The key is here now, so that error is stale.
    if result.get("error") == MISSING_KEY:
        result["error"] = None
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
    # PDF figure and table boxes are the crop when the page has them. Concept
    # prompts come back empty on these papers, or as fragments of a chart.
    # SAM runs only for a page the PDF does not already segment.
    pdf_hits = {}
    for page, png in pngs.items():
        hits = _pdf_hits(pdf, page, png)
        if hits:
            pdf_hits[page] = (png, hits)
    tasks = [(page, phrase) for page in pngs if page not in pdf_hits for phrase in phrases]
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
    checked = set(int(p) for p in (previous.get("pdf_checked") or []))
    for page, (png, hits) in pdf_hits.items():
        checked.add(page)
        counts = {}
        for hit in hits:
            phrase = hit["phrase"]
            n = counts.get(phrase, 0)
            counts[phrase] = n + 1
            name = f"p{page}_{phrase}_{n}.png"
            if _crop(png, hit, crops_dir / name):
                fresh.append({
                    "page": page,
                    "phrase": phrase,
                    "bbox": [hit["x1"], hit["y1"], hit["x2"], hit["y2"]],
                    "file": name,
                    "source": "pdf",
                })
    result["crops"] = kept + fresh
    result["pdf_checked"] = checked
    result["cost_usd"] = round(result["images"] * USD_PER_IMAGE, 6)
    _write_index(crops_dir, result["crops"], result)
    return result


def fill_pdf_crops(pdf: Path, crops_dir: Path, pages: list[int]) -> tuple[dict, bool]:
    """Crops from PDF boxes for pages SAM already finished with nothing.

    Does not call SAM. A page with no figure and no table is remembered in
    `pdf_checked` so the next read does not scan it again. The bool is whether
    the index was rewritten.
    """
    crops_dir.mkdir(parents=True, exist_ok=True)
    index = _load_index(crops_dir)
    if not pdf.is_file():
        return index, False
    by_page = {}
    for row in index.get("crops") or []:
        if isinstance(row, dict) and row.get("page") is not None:
            by_page.setdefault(int(row["page"]), []).append(row)
    checked = set(int(p) for p in (index.get("pdf_checked") or []))
    todo = []
    for n in pages:
        n = int(n)
        rows = by_page.get(n) or []
        if rows and all(r.get("source") == "pdf" for r in rows):
            continue
        if n in checked:
            continue
        # Empty, or SAM fragments. PDF boxes replace those when the page has any.
        todo.append(n)
    if not todo:
        return index, False
    try:
        pngs = render_selected(pdf, todo)
    except Exception:
        return index, False
    crops = list(index.get("crops") or [])
    for page, png in pngs.items():
        hits = _pdf_hits(pdf, page, png)
        checked.add(page)
        if not hits:
            continue
        crops = [row for row in crops if int(row.get("page", -1)) != page]
        counts = {}
        for hit in hits:
            phrase = hit["phrase"]
            n = counts.get(phrase, 0)
            counts[phrase] = n + 1
            name = f"p{page}_{phrase}_{n}.png"
            if _crop(png, hit, crops_dir / name):
                crops.append({
                    "page": page,
                    "phrase": phrase,
                    "bbox": [hit["x1"], hit["y1"], hit["x2"], hit["y2"]],
                    "file": name,
                    "source": "pdf",
                })
    result = {
        "images": int(index.get("images") or 0),
        "error": index.get("error"),
        "pages": index.get("pages") or 0,
        "done_pages": index.get("done_pages") or [],
        "pdf_checked": checked,
    }
    _write_index(crops_dir, crops, result)
    return _load_index(crops_dir), True


def segment_pdf(pdf: Path, crops_dir: Path, phrases=PHRASES, max_pages: int = 30) -> dict:
    """Render up to max_pages and ask SAM. Always returns a dict; errors do not raise."""
    key = api_key()
    crops_dir.mkdir(parents=True, exist_ok=True)
    result = {"crops": [], "images": 0, "cost_usd": 0.0, "error": None, "pages": 0}
    if not key:
        result["error"] = MISSING_KEY
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
        pdf_first = _pdf_hits(pdf, page_i, png)
        if pdf_first:
            page_hits = [(hit["phrase"], hit) for hit in pdf_first]
            counts = {}
            for phrase, hit in page_hits:
                n = counts.get(phrase, 0)
                counts[phrase] = n + 1
                name = f"p{page_i}_{phrase}_{n}.png"
                dest = crops_dir / name
                if _crop(png, hit, dest):
                    index.append({
                        "page": page_i,
                        "phrase": phrase,
                        "bbox": [hit["x1"], hit["y1"], hit["x2"], hit["y2"]],
                        "file": name,
                        "source": "pdf",
                    })
            continue
        page_hits = []
        failed = False
        for phrase in phrases:
            try:
                hits = segment_png(png, phrase, key)
            except urllib.error.HTTPError as err:
                result["error"] = f"sam http {err.code}"
                failed = True
                if err.code in (401, 403):
                    _write_index(crops_dir, index, result)
                    return result
                continue
            except Exception as err:
                result["error"] = f"sam error: {err}"
                failed = True
                continue
            result["images"] += 1
            page_hits.extend((phrase, hit) for hit in hits)
        counts = {}
        for phrase, hit in page_hits:
            n = counts.get(phrase, 0)
            counts[phrase] = n + 1
            name = f"p{page_i}_{phrase}_{n}.png"
            dest = crops_dir / name
            if _crop(png, hit, dest):
                row = {
                    "page": page_i,
                    "phrase": phrase,
                    "bbox": [hit["x1"], hit["y1"], hit["x2"], hit["y2"]],
                    "file": name,
                }
                if hit.get("source"):
                    row["source"] = hit["source"]
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
        "pdf_checked": sorted(int(p) for p in (result.get("pdf_checked") or [])),
    }
    (crops_dir / "index.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
