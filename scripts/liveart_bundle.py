#!/usr/bin/env python3
"""RRM-96: pack live rrm-widget/0.4 outputs for the reader.

Reads the raw per-claim files of `liveart_stack.py --live --raw DIR`, keeps a widget only if the engine
verifier and the sandbox pass, attaches the anchor from the claim (real LaTeX, quote, section; never
written by the model), verifies the final JSON again in Chrome, and seals it with a sha256.

  python3 scripts/liveart_bundle.py --raw DIR [--raw DIR2] --claims claims.json \
      [--passages passages.json] --out apps/reader/public/liveart96

No network, no Meta. The output dir is git-ignored: the bundle carries paper quotes and lives in compass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "apps" / "reader" / "scripts" / "liveart_audit.mjs"
FONT = ROOT / "apps" / "reader" / "node_modules" / "@fontsource-variable" / "instrument-sans" / "files" / "instrument-sans-latin-wght-normal.woff2"
NAMES = {"muse-wonder-1.0": "Muse Wonder", "muse-spark-1.3-contributor": "Muse Spark"}


def _model(calls):
    used = [c.get("model") for c in calls if c.get("stage") in ("codegen", "repair") and c.get("model")]
    name = used[-1] if used else ""
    return NAMES.get(name, name)


def _sha(widget):
    return hashlib.sha256(json.dumps(widget, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _grade(items):
    blob = ROOT / ".bundle96-in.json"
    out = ROOT / ".bundle96-out.json"
    blob.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, RRM_LIVEART_V04="1")
    subprocess.run(["node", str(NODE), "--in", str(blob), "--out", str(out), "--sandbox"], cwd=ROOT, check=True, env=env,
                   capture_output=True, timeout=600)
    got = {row["id"]: row for row in json.loads(out.read_text(encoding="utf-8"))}
    blob.unlink(missing_ok=True)
    out.unlink(missing_ok=True)
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="append", required=True, help="raw dir; a later dir wins for the same id")
    ap.add_argument("--claims", required=True)
    ap.add_argument("--passages", default="")
    ap.add_argument("--only", default="", help="comma ids to keep, in this order")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    claims = {row["id"]: row for row in json.loads(Path(args.claims).read_text(encoding="utf-8"))}
    passages = json.loads(Path(args.passages).read_text(encoding="utf-8")) if args.passages else {}
    raw = {}
    for d in args.raw:
        for f in sorted(Path(d).glob("*.json")):
            if f.name.startswith("_"):
                continue
            blob = json.loads(f.read_text(encoding="utf-8"))
            if blob.get("widget"):
                raw[f.stem] = (d, blob)

    staged, skipped = [], []
    for cid, (d, blob) in raw.items():
        row = blob["row"]
        if cid not in claims:
            skipped.append((cid, "no claim"))
            continue
        if row.get("verify") != "pass" or row.get("sandbox") != "pass":
            skipped.append((cid, f"run verdict {row.get('verify')}/{row.get('sandbox')} {','.join(row.get('reasons') or [])}"))
            continue
        c = claims[cid]
        meta = dict(c["meta"], arxiv=c["claim"]["arxiv"])
        widget = dict(blob["widget"])
        widget["anchor"] = {
            "latex": c["claim"].get("latex") or "",
            "quote": meta.get("quote") or "",
            "arxiv": meta["arxiv"],
            "section": "§" + meta["section"] if meta.get("section") else "",
            "eq": ("Eq. " + meta["eq"]) if str(meta.get("eq") or "").isdigit() else (meta.get("eq") or ""),
        }
        staged.append((cid, d, blob, meta, widget))

    graded = _grade([{"group": "stack", "id": cid, "claim": claims[cid]["claim"]["text"], "widget": w} for cid, _, _, _, w in staged])
    entries = []
    for cid, d, blob, meta, widget in staged:
        g = graded.get(cid, {})
        row = blob["row"]
        if g.get("verify") != "pass" or g.get("sandbox") != "pass":
            skipped.append((cid, f"final verdict {g.get('verify')}/{g.get('sandbox')} {','.join(g.get('reasons') or [])}"))
            continue
        meta.pop("quote", None)
        entries.append({
            "id": cid,
            "widget": widget,
            "meta": meta,
            "verdict": {"verify": g["verify"], "sandbox": g["sandbox"], "reasons": g.get("reasons") or [], "pixels": g.get("pixels", 0),
                        "gate": row.get("gate") or [], "model_verifier": row.get("model_verifier") or ""},
            "provenance": {"model": _model(blob.get("calls") or []), "config": "wonder", "run": Path(d).name, "date": "2026-11-04",
                           "cost_usd": round(float(row.get("cost") or 0), 5), "contract": widget.get("version") or "", "sha": _sha(widget)},
            "passage": passages.get(cid),
        })
    if args.only:
        order = [i.strip() for i in args.only.split(",") if i.strip()]
        entries = sorted([e for e in entries if e["id"] in order], key=lambda e: order.index(e["id"]))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bundle.json").write_text(json.dumps({"version": "rrm96-1", "entries": entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    if FONT.exists():
        shutil.copyfile(FONT, out / "ui.woff2")
    print(f"{len(entries)} entries -> {out / 'bundle.json'}")
    for e in entries:
        print(f"  ok   {e['id']:<16} {e['provenance']['model']:<12} ${e['provenance']['cost_usd']:.3f} gate={','.join(e['verdict']['gate']) or '-'} sha={e['provenance']['sha'][:7]}")
    for cid, why in skipped:
        print(f"  skip {cid:<16} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
