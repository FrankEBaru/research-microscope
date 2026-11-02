"""RRM-58 follow-up: vision on a click with no text label, and one Muse Image.

Appends to docs/research/rrm58/ledger.json. Stops at $0.28. Does not print the key.
"""

import base64, json, os, time, urllib.request, urllib.error
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path("docs/research/rrm58")
CAP = 0.28
API = "https://api.meta.ai/v1"


def spent(ledger):
    return round(sum(row.get("usd") or 0 for row in ledger), 8)


def post(url, body, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + os.environ["MODEL_API_KEY"], "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode()), round(time.perf_counter() - t0, 3)
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode("utf-8", "replace")[:240]}, round(time.perf_counter() - t0, 3)


def text_of(payload):
    chunks = []
    for item in (payload or {}).get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("text"):
                chunks.append(part["text"])
    return "\n".join(chunks)


def spark_cost(usage):
    usage = usage or {}
    incoming = int(usage.get("input_tokens") or 0)
    outgoing = int(usage.get("output_tokens") or 0)
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached = min(int(details.get("cached_tokens") or 0), incoming)
    return round(((incoming - cached) * 0.10 + cached * 0.002 + outgoing * 0.20) / 1_000_000, 8)


def dot(src, xy, dest):
    im = Image.open(src).convert("RGB")
    x, y = xy
    ImageDraw.Draw(im).ellipse([x - 7, y - 7, x + 7, y + 7], fill=(0, 180, 0), outline=(0, 0, 0))
    im.save(dest)
    return dest


def b64(path):
    return "data:image/png;base64," + base64.standard_b64encode(Path(path).read_bytes()).decode()


def main():
    ledger = json.loads((OUT / "ledger.json").read_text())
    done = {row["name"] for row in ledger}
    resnet = dot(OUT / "block.png", (409, 298), OUT / "resnet_plus_dot.png")
    dann = dot("/tmp/rrm58/preview/deepDA2.png", (812, 371), OUT / "dann_loss_dot.png")
    papers = json.loads(Path("/tmp/rrm58/parsed/papers/2871880.json").read_text())
    dann_bits = []
    for row in papers["rows"]:
        text = row.get("text") or ""
        if row.get("kind") == "p" and any(w in text.lower() for w in ("gradient reversal", "domain classifier", "domain classification loss")):
            dann_bits.append(f"[{row['id']}] {text[:500]}")
    dann_pack = "\n".join(dann_bits)[:8000]
    jobs = {
        "spark_vision_resnet_plus": (
            "A green dot marks the clicked part of this figure. Nearest PDF word is not given. "
            "Name the operation under the dot in one sentence, using only what is drawn and this caption: "
            "'Residual learning: a building block.' "
            'JSON: {"name":"","what":"","beyond_caption":false}'
        ),
        "spark_vision_dann_loss": (
            "A green dot marks one clicked part. The PDF text layer is empty or the nearest word may be wrong. "
            "Name the part from the picture, then explain it in under 90 words using only the passages. "
            "Each factual claim needs a verbatim quote that is an exact substring, with its id. "
            "Set beyond=false if the caption or a passage that cites the figure already says this. "
            'JSON: {"name":"","what":"","quotes":[{"id":"","quote":""}],"beyond":false,"why":""}\n'
            "Caption: proposed architecture with a feature extractor (green), a label predictor (blue), and a domain classifier (red) joined by a gradient reversal layer.\n"
            "Passages:\n" + dann_pack
        ),
    }
    results = {}
    for name, prompt in jobs.items():
        if name in done or spent(ledger) + 0.01 > CAP:
            continue
        image = resnet if "resnet" in name else dann
        status, payload, elapsed = post(API + "/responses", {
            "model": "muse-spark-1.3-contributor", "store": False,
            "reasoning": {"effort": "minimal"}, "max_output_tokens": 500,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": b64(image)},
            ]}],
        })
        usage = payload.get("usage") if status == 200 else {}
        cost = spark_cost(usage) if status == 200 else 0.0
        row = {"name": name, "model": "muse-spark-1.3-contributor", "status": status, "s": elapsed, "usd": cost, "usage": usage or {}}
        ledger.append(row)
        results[name] = {"status": status, "s": elapsed, "usd": cost, "text": text_of(payload)[:2500], "error": payload.get("error")}
        (OUT / "ledger.json").write_text(json.dumps(ledger, indent=2))
    if "muse_image_dct" not in done and spent(ledger) + 0.01 <= CAP:
        status, payload, elapsed = post(API + "/images/generations", {
            "model": "muse-image-1.0",
            "prompt": (
                "Clean white-background teaching schematic of one math claim: a generalized discrete cosine transform "
                "with three parameters, a new type of discrete cosine transform, and a generalized discrete W transform "
                "with three parameters. Orthogonality is proved for some new cases. Label only those three transforms "
                "and 'three parameters'. Do not draw JPEG, photos, cameras, neural networks, or medical scans."
            ),
            "n": 1, "output_format": "png", "reasoning_strength": "low",
            "tool_enablement": {"enable_web_search": False, "enable_image_search": False, "enable_shell": False},
        })
        images = payload.get("data") or []
        cost = 0.01 if status == 200 and images else 0.0
        if images and images[0].get("b64_json"):
            raw = base64.b64decode(images[0]["b64_json"])
            (OUT / "dct_schematic.png").write_bytes(raw)
        kept = {k: payload.get(k) for k in payload if k != "data"}
        kept["n_images"] = len(images)
        ledger.append({"name": "muse_image_dct", "model": "muse-image-1.0", "status": status, "s": elapsed, "usd": cost})
        results["muse_image_dct"] = {"status": status, "s": elapsed, "usd": cost, "meta": kept, "error": payload.get("error")}
        (OUT / "ledger.json").write_text(json.dumps(ledger, indent=2))
    (OUT / "follow.json").write_text(json.dumps({"results": results, "spent_usd": spent(ledger)}, indent=2))
    print("spent", spent(ledger))


if __name__ == "__main__":
    main()
