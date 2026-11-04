#!/usr/bin/env python3
"""RRM-96: one Muse call per widget to fix the engine reasons and the reader-facing text of a 0.4 widget.

Input: the raw dir of `liveart_stack.py --live --raw`. Output: a raw dir of the same shape, with the
polish call (prompt and answer) appended, graded again by the engine verifier and the sandbox.
The draw stays unless a reason names it. Needs MODEL_API_KEY and RRM_LIVEART_V04=1.

  RRM_LIVEART_V04=1 python3 scripts/liveart_polish.py --raw-in A --claims claims.json --raw-out B --max-usd 1.2
  ... --dry-run   prices the prompts without HTTP
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
NODE = ROOT / "apps" / "reader" / "scripts" / "liveart_audit.mjs"


def notes(widget):
    """Reader-facing text the engine accepts but a newcomer would trip on. Hard limits are engine reasons."""
    out = []
    snake = re.compile(r"\b[a-z]+_[a-z0-9]+\b")
    if snake.search(widget.get("hook") or "") or len(widget.get("hook") or "") > 60:
        out.append("hook: símbolos con Unicode, hasta 60 caracteres")
    for c in widget.get("controls") or []:
        if snake.search(c.get("label") or "") or len(c.get("label") or "") > 16:
            out.append(f"control {c.get('id')}: label de lector, hasta 16")
    for r in widget.get("readouts") or []:
        if "_" in (r.get("label") or "") or len(r.get("label") or "") > 16:
            out.append(f"readout {r.get('id')}: label de lector, hasta 16")
    for g in widget.get("legend") or []:
        if "_" in (g.get("text") or "") or len(g.get("text") or "") > 16:
            out.append(f"legend «{g.get('text')}»: hasta 16")
    for m in widget.get("marks") or []:
        if len(m.get("label") or "") > 18:
            out.append(f"mark {m.get('id')}: label hasta 18")
    take = widget.get("takeaway")
    if isinstance(take, str) and snake.search(re.sub(r"\{\w+\}", "", take)):
        out.append("takeaway: sin identificadores fuera de {id}")
    return out


def merge_text(orig, new):
    """The verified draw stays; the polished reader-facing text is taken by id. Ranges, kinds and ids never move."""
    out = json.loads(json.dumps(orig))
    for key in ("hook", "title", "explain", "questions", "takeaway"):
        if new.get(key):
            out[key] = new[key]
    by = lambda rows: {r.get("id"): r for r in rows or [] if isinstance(r, dict)}
    nc, nr, nm = by(new.get("controls")), by(new.get("readouts")), by(new.get("marks"))
    for c in out.get("controls") or []:
        if c.get("id") in nc and nc[c["id"]].get("label"):
            c["label"] = nc[c["id"]]["label"]
    for r in out.get("readouts") or []:
        if r.get("id") in nr and nr[r["id"]].get("label"):
            r["label"] = nr[r["id"]]["label"]
    for m in out.get("marks") or []:
        if m.get("id") in nm and nm[m["id"]].get("label"):
            m["label"] = nm[m["id"]]["label"]
    old_lg, new_lg = out.get("legend") or [], new.get("legend") or []
    if len(old_lg) == len(new_lg) and all(a.get("color") == b.get("color") for a, b in zip(old_lg, new_lg)):
        out["legend"] = [dict(a, text=b.get("text") or a.get("text")) for a, b in zip(old_lg, new_lg)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-in", required=True)
    ap.add_argument("--raw-out", required=True)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--model", default="muse-wonder-1.0")
    ap.add_argument("--max-usd", type=float, required=True, dest="max_usd")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--note", action="append", default=[], help="extra reason for the polish prompt (repeatable)")
    ap.add_argument("--merge-only", action="store_true", help="no calls: re-grade the saved polish answers of --raw-out")
    args = ap.parse_args()

    from rrm.liveart import prompts as P
    from rrm.liveart.gate import sanitize_widget
    from scripts_live import _call, _ceiling, _chars, _estimate, _grade

    claims = {r["id"]: r["claim"] for r in json.loads(Path(args.claims).read_text(encoding="utf-8"))}
    want = [i.strip() for i in args.ids.split(",") if i.strip()]
    out = Path(args.raw_out)
    out.mkdir(parents=True, exist_ok=True)
    schema = P.schemas()["codegen"]
    total = 0.0
    for f in sorted(Path(args.raw_in).glob("*.json")):
        cid = f.stem
        if cid.startswith("_") or (want and cid not in want) or cid not in claims:
            continue
        blob = json.loads(f.read_text(encoding="utf-8"))
        if args.merge_only:
            prev = out / f"{cid}.json"
            if not prev.exists():
                continue
            done = json.loads(prev.read_text(encoding="utf-8"))
            if done["row"].get("polished"):
                print(f"{cid:<16} already polished[{done['row']['polished']}]")
                continue
            pol = (done.get("calls") or [{}])[-1]
            new = (pol.get("json") or {}) if pol.get("stage") == "polish" else {}
            if not new.get("draw"):
                continue
            merged = sanitize_widget(merge_text(blob["widget"], new))
            v2 = _grade(NODE, ROOT, cid, claims[cid].get("text", ""), merged, True)
            if v2.get("verify") == "pass" and v2.get("sandbox") == "pass":
                done["widget"] = merged
                done["row"].update(verify="pass", sandbox="pass", reasons=v2.get("reasons") or [], polished="text")
                done["row"].pop("polish_failed", None)
                prev.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{cid:<16} merge {v2.get('verify')}/{v2.get('sandbox')} {','.join(v2.get('reasons') or [])[:60]}")
            continue
        widget = blob.get("widget")
        if not widget:
            print(f"{cid:<16} no widget, skip")
            continue
        row = blob["row"]
        reasons = [r for r in (row.get("reasons") or [])] + notes(widget) + list(args.note)
        msgs = P.polish_messages(claims[cid], widget, reasons)
        ceiling = _ceiling(args.model, _chars(msgs), 6000)
        if args.dry_run:
            est, _ = _estimate(args.model, msgs, "codegen")
            print(f"{cid:<16} reasons={reasons} est ${est['cost_usd']:.4f} ceiling ${ceiling:.4f}")
            total += est["cost_usd"]
            continue
        if total + ceiling > args.max_usd:
            print(f"BUDGET: {cid} ceiling ${ceiling:.4f} would pass ${args.max_usd} (spent ${total:.4f}); stop")
            break
        got = _call("repair", msgs[0], msgs[1], schema, 6000, "low", args.model)
        got["stage"] = "polish"
        got["messages"] = {"system": msgs[0], "user": msgs[1]}
        total += got["usage"]["cost_usd"]
        new = got["json"] or {}
        verdict = {"verify": "no_output", "sandbox": "skipped", "reasons": [got["error"] or "empty"]}
        if new.get("draw"):
            new = sanitize_widget(new)
            verdict = _grade(NODE, ROOT, cid, claims[cid].get("text", ""), new, True)
        ok = verdict.get("verify") == "pass" and verdict.get("sandbox") == "pass"
        how = "full" if ok else ""
        if not ok and new.get("draw"):
            merged = sanitize_widget(merge_text(widget, new))
            v2 = _grade(NODE, ROOT, cid, claims[cid].get("text", ""), merged, True)
            if v2.get("verify") == "pass" and v2.get("sandbox") == "pass":
                new, verdict, ok, how = merged, v2, True, "text"
        keep = new if ok else widget
        row2 = dict(row, verify=verdict.get("verify"), sandbox=verdict.get("sandbox"), reasons=verdict.get("reasons") or [],
                    cost=round(float(row.get("cost") or 0) + got["usage"]["cost_usd"], 6), polished=how or False, polish_reasons=reasons)
        if not ok:
            row2.update(verify=row.get("verify"), sandbox=row.get("sandbox"), reasons=row.get("reasons") or [],
                        polish_failed=[verdict.get("verify"), verdict.get("sandbox")] + list(verdict.get("reasons") or []))
        (out / f"{cid}.json").write_text(json.dumps({"row": row2, "calls": (blob.get("calls") or []) + [got], "widget": keep},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{cid:<16} polish[{how or '-'}] {verdict.get('verify')}/{verdict.get('sandbox')} {','.join(verdict.get('reasons') or [])[:60]} "
              f"${got['usage']['cost_usd']:.4f} tot ${total:.4f}", flush=True)
    print(f"total ${total:.5f}{' (dry run estimate)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
