"""RRM-58 probes: click-a-region vs caption+paragraph. No product features.
Reads local tarballs already extracted under /tmp/rrm58. Does not download arXiv.
Meta calls run only with --live and stop at $0.28. The key stays in the header.
"""
import argparse, base64, json, os, re, time, urllib.error, urllib.request
from pathlib import Path
import pymupdf
LATEX = Path("/tmp/rrm58/latex")
PARSED = Path("/tmp/rrm58/parsed/papers")
OUT = Path("docs/research/rrm58")
SAM_USD = 0.0025
CAP = 0.28
API = "https://api.meta.ai/v1/responses"
def key():
    value = os.environ.get("MODEL_API_KEY") or ""
    if not value:
        raise SystemExit("MODEL_API_KEY is not set")
    return value
def post(url, body, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key(), "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
            return resp.status, payload, round(time.perf_counter() - t0, 3)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:240]
        return exc.code, {"error": detail}, round(time.perf_counter() - t0, 3)
def text_of(payload):
    chunks = []
    for item in (payload or {}).get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in ("output_text", "text") and part.get("text"):
                chunks.append(part["text"])
    if chunks:
        return "\n".join(chunks)
    return payload.get("output_text") or ""
def dollars(model, usage):
    usage = usage or {}
    incoming = int(usage.get("input_tokens") or 0)
    outgoing = int(usage.get("output_tokens") or 0)
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached = min(int(details.get("cached_tokens") or 0), incoming)
    if "wonder" in model:
        rates = (4.00, 0.20, 20.00)
    else:
        rates = (0.10, 0.002, 0.20)
    cost = (incoming - cached) * rates[0] + cached * rates[1] + outgoing * rates[2]
    return round(cost / 1_000_000, 8)
def render(pdf, scale):
    page = pymupdf.open(pdf)[0]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    path = OUT / (Path(pdf).stem + ".png")
    pix.save(path)
    words = []
    for w in page.get_text("words"):
        words.append({
            "t": w[4],
            "x": int(w[0] * pix.width / page.rect.width),
            "y": int(w[1] * pix.height / page.rect.height),
            "x2": int(w[2] * pix.width / page.rect.width),
            "y2": int(w[3] * pix.height / page.rect.height),
        })
    return {"png": str(path), "w": pix.width, "h": pix.height, "words": words, "page": page, "pdf": str(pdf)}
def px(fig, x, y):
    page = fig["page"]
    return int(x * fig["w"] / page.rect.width), int(y * fig["h"] / page.rect.height)
def nearest(fig, x, y, n=4):
    cx, cy = px(fig, x, y)
    ranked = sorted(fig["words"], key=lambda w: (w["x"] - cx) ** 2 + (w["y"] - cy) ** 2)
    return ranked[:n], {"x": cx, "y": cy}
def load_rows(cid):
    data = json.loads((PARSED / f"{cid}.json").read_text())
    return data["paper"], [r for r in data["rows"] if r.get("kind") == "p" and r.get("text")]
def citing(rows, label):
    return [r for r in rows if label in r["text"]]
def rank_rows(rows, words):
    want = {w.lower() for w in words if len(w) > 2}
    scored = []
    for row in rows:
        tokens = set(re.findall(r"[A-Za-z0-9-]{3,}", row["text"].lower()))
        scored.append((len(want & tokens), row))
    scored.sort(key=lambda item: -item[0])
    return [{"id": r["id"], "overlap": n, "text": r["text"][:280]} for n, r in scored[:4] if n]
def pack(rows, limit=24000):
    lines, used = [], 0
    for row in rows:
        bit = f"[{row['id']}] {row['text'].strip()}"
        if used + len(bit) > limit:
            break
        lines.append(bit)
        used += len(bit)
    return "\n".join(lines)
def prompt_for(click, rows, label):
    local = "\n".join(f"[{r['id']}] {r['text'].strip()}" for r in citing(rows, label))
    return (
        "A reader clicked one part of a paper figure. Explain THAT part in under 120 words. "
        "Use only the passages. Every factual sentence must include a verbatim quote that is an exact substring of one passage, with its id. "
        "If the caption plus the passages that cite the figure already say this, set beyond=false.\n"
        f"Clicked label from the PDF text layer (empty if none): {click['label']}\n"
        f"Caption: {click['caption']}\n"
        f"Passages that cite the figure:\n{local}\n"
        f"Other passages:\n{pack(rows)}\n"
        'Return JSON: {"what":"","quotes":[{"id":"","quote":""}],"beyond":false,"why":""}'
    )
def png_b64(path):
    return "data:image/png;base64," + base64.standard_b64encode(Path(path).read_bytes()).decode()
def sam(fig, text, name, ledger):
    body = {
        "model": "sam-3.1", "stream": False,
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": png_b64(fig["png"])},
        ]}],
    }
    delay = 1.0
    status, payload, elapsed = 0, {}, 0
    for attempt in range(4):
        status, payload, elapsed = post(API, body, timeout=90)
        if status == 200 or status not in (404, 429, 500, 502, 503):
            break
        time.sleep(delay)
        delay = min(delay * 2, 8)
    boxes = []
    raw = text_of(payload) if status == 200 else ""
    for obj, blob in re.findall(r"(\d+)<\|box;([^|]*)\|>", raw):
        fields = dict(part.split("=", 1) for part in blob.split(";") if "=" in part)
        box = {k: int(fields[k]) for k in ("x1", "y1", "x2", "y2") if k in fields}
        if "c" in fields:
            box["c"] = float(fields["c"])
        box["id"] = int(obj)
        boxes.append(box)
    cost = SAM_USD if status == 200 else 0.0
    ledger.append({"name": name, "model": "sam-3.1", "status": status, "s": elapsed, "usd": cost, "n_boxes": len(boxes)})
    return {"status": status, "s": elapsed, "usd": cost, "boxes": boxes, "chars": len(raw), "error": payload.get("error")}
def chat(model, text, image, name, ledger):
    content = [{"type": "input_text", "text": text}]
    if image:
        content.append({"type": "input_image", "image_url": png_b64(image)})
    body = {
        "model": model, "store": False, "reasoning": {"effort": "minimal"}, "max_output_tokens": 700,
        "input": [{"type": "message", "role": "user", "content": content}],
    }
    status, payload, elapsed = post(API, body, timeout=180)
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    cost = dollars(model, usage) if status == 200 else 0.0
    out = text_of(payload)
    ledger.append({"name": name, "model": model, "status": status, "s": elapsed, "usd": round(cost, 8), "usage": usage or {}})
    return {"status": status, "s": elapsed, "usd": round(cost, 8), "usage": usage or {}, "text": out[:4000], "error": (payload or {}).get("error")}
def spent(ledger):
    return round(sum(row["usd"] for row in ledger), 8)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    block = render(LATEX / "206594692/src/eps/block.pdf", 4)
    unet = render(LATEX / "3719281/src/u-net-illustration-correct-scale2.pdf", 2)
    clicks = {
        "resnet_shortcut": {"fig": block, "pdf": (150, 40), "label_hint": "identity", "caption": "Residual learning: a building block.", "cite": "fig:block"},
        "resnet_plus": {"fig": block, "pdf": (102.2, 74.5), "label_hint": "+", "caption": "Residual learning: a building block.", "cite": "fig:block"},
        "unet_upconv": {"fig": unet, "pdf": (342, 127), "label_hint": "up-conv", "caption": "U-net architecture. Each blue box is a multi-channel feature map. Numbers are channels and x-y size. White boxes are copied feature maps. Arrows denote the operations.", "cite": "fig:u-net"},
        "unet_white": {"fig": unet, "pdf": (221, 257), "label_hint": "copy", "caption": "U-net architecture. Each blue box is a multi-channel feature map. Numbers are channels and x-y size. White boxes are copied feature maps. Arrows denote the operations.", "cite": "fig:u-net"},
    }
    _, resnet_rows = load_rows("206594692")
    _, unet_rows = load_rows("3719281")
    rows_of = {"fig:block": resnet_rows, "fig:u-net": unet_rows}
    free = {}
    for name, click in clicks.items():
        near, at = nearest(click["fig"], *click["pdf"])
        rows = rows_of[click["cite"]]
        free[name] = {
            "at": at, "nearest": near,
            "code_hits": rank_rows(rows, [w["t"] for w in near] + [click["label_hint"]]),
            "citing_ids": [r["id"] for r in citing(rows, click["cite"])],
        }
    census = {"pdf": 0, "vector_text": 0, "raster": 0, "silent_vector": 0, "tikz_envs": 0}
    for path in LATEX.rglob("*"):
        if path.suffix == ".tex" and "literatur" not in path.name:
            census["tikz_envs"] += len(re.findall(r"\\begin\{tikzpicture\}", path.read_text(errors="replace")))
        if path.suffix != ".pdf" or "cont_normflow" in str(path) or "dataset_samples" in str(path):
            continue
        census["pdf"] += 1
        page = pymupdf.open(path)[0]
        words, images = len(page.get_text("words")), len(page.get_images())
        if words >= 5:
            census["vector_text"] += 1
        elif images:
            census["raster"] += 1
        else:
            census["silent_vector"] += 1
    (OUT / "free.json").write_text(json.dumps({"census": census, "clicks": free}, indent=2))
    print("free", census, "clicks", {k: v["nearest"][0]["t"] if v["nearest"] else "" for k, v in free.items()})
    if not args.live:
        return
    ledger = []
    if (OUT / "ledger.json").exists():
        ledger = json.loads((OUT / "ledger.json").read_text())
    done = {row["name"] for row in ledger}
    def room(est):
        return spent(ledger) + est <= CAP
    live = {}
    # One image, three point-objects: billed once per image.
    for fig, spec, name in (
        (block, [(1, 150, 40), (2, 102.2, 74.5), (3, 100, 28)], "sam_points_resnet"),
        (unet, [(1, 342, 127), (2, 221, 257), (3, 121.2, 223.6)], "sam_points_unet"),
    ):
        if name in done or not room(SAM_USD):
            continue
        parts = [f"{i}<|point;x={px(fig, x, y)[0]};y={px(fig, x, y)[1]};w={fig['w']};h={fig['h']}|>" for i, x, y in spec]
        live[name] = sam(fig, "<0f>" + ",".join(parts), name, ledger)
        (OUT / "ledger.json").write_text(json.dumps(ledger, indent=2))
    for fig, phrase, name in ((unet, "arrow", "sam_concept_unet_arrow"), (block, "arrow", "sam_concept_resnet_arrow")):
        if name in done or not room(SAM_USD):
            continue
        live[name] = sam(fig, phrase, name, ledger)
        (OUT / "ledger.json").write_text(json.dumps(ledger, indent=2))
    jobs = {
        "spark_resnet_shortcut": ("muse-spark-1.3-contributor", prompt_for({**clicks["resnet_shortcut"], "label": "identity"}, resnet_rows, "fig:block"), None),
        "spark_unet_upconv": ("muse-spark-1.3-contributor", prompt_for({**clicks["unet_upconv"], "label": "up-conv 2x2"}, unet_rows, "fig:u-net"), None),
        "wonder_unet_upconv": ("muse-wonder-1.0", prompt_for({**clicks["unet_upconv"], "label": "up-conv 2x2"}, unet_rows, "fig:u-net"), None),
    }
    for name, (model, text, image) in jobs.items():
        est = 0.02 if "wonder" in model else 0.005
        if name in done or not room(est):
            continue
        live[name] = chat(model, text, image, name, ledger)
        (OUT / "ledger.json").write_text(json.dumps(ledger, indent=2))
    (OUT / "live.json").write_text(json.dumps({"live": live, "spent_usd": spent(ledger), "ledger": ledger}, indent=2))
    print("spent", spent(ledger))
if __name__ == "__main__":
    main()
