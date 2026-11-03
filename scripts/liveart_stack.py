#!/usr/bin/env python3
"""Emulated path: claim, selector, questions, explanation, code, verify, sandbox, fallback.

No Meta. The code step is the fixed bank (gold, else the first emulated widget of that topic).

  python3 scripts/liveart_stack.py --n 16 --sandbox --out /tmp/liveart-stack.json

The first 16 ids are the probe RRM-78 reserved for muse-spark-1.3-contributor.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NODE = ROOT / "apps" / "reader" / "scripts" / "liveart_audit.mjs"

# Order matches the probe in equipo-artefactos/STATUS-RRM-78.md.
PROBE = (
    "pe-formula",
    "softmax-temp",
    "attn-scale",
    "layernorm",
    "giou",
    "ppo",
    "nerf",
    "vit",
    "rope",
    "online-softmax",
    "chinchilla",
    "adam",
    "spec-cost",
    "yarn-parts",
    "batchnorm",
    "distill",
)


def _ordered_cases():
    from evals.liveart.cases import cases

    select = [case for case in cases() if case["suite"] == "select"]
    by_id = {case["id"]: case for case in select}
    ordered = [by_id[name] for name in PROBE if name in by_id]
    seen = {case["id"] for case in ordered}
    for case in select:
        if case["id"] not in seen:
            ordered.append(case)
    return ordered


def _stage(case):
    from rrm.liveart.offline import emulated_widget, explain_for, questions_for, select_claim

    claim = case["claim"]
    decision = select_claim(claim)
    questions = questions_for(claim)
    explain = explain_for(claim)
    row = {
        "id": case["id"],
        "claim": claim["text"],
        "select": decision["merit"],
        "topic": decision["topic"],
        "reason": decision["reason"],
        "questions": len(questions["questions"]),
        "explain": len(explain["explain"]),
        "code": "",
        "verify": "skipped",
        "sandbox": "skipped",
        "reasons": [],
        "outcome": "fallback",
    }
    if decision["merit"] != "widget":
        row["reasons"] = [decision["reason"] or decision["merit"]]
        return row, None
    widget = emulated_widget(claim)
    if widget is None:
        row["reasons"] = ["no_draw"]
        return row, None
    row["code"] = widget["id"]
    row["verify"] = "pending"
    return row, widget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--sandbox", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--live", action="store_true", help="call the model in --config (needs MODEL_API_KEY)")
    parser.add_argument("--config", default="spark", choices=("spark", "wonder", "hybrid"),
                        help="spark, wonder, or hybrid (Wonder: questions and explain; Spark: the rest)")
    parser.add_argument("--max-usd", type=float, default=None, dest="max_usd",
                        help="refuse the next call when spent + worst case would pass this")
    parser.add_argument("--dry-run", action="store_true", help="price the prompts; do not call the API")
    parser.add_argument("--raw", default="", help="dir for key-free raw outputs (--live)")
    parser.add_argument("--cap", type=float, default=None, help="stop after a call once total >= cap (default 1, or --max-usd)")
    parser.add_argument("--ids", default="", help="comma ids (--live), overrides --n order")
    args = parser.parse_args()
    if args.cap is None:
        args.cap = args.max_usd if args.max_usd is not None else 1.0
    if args.live or args.dry_run:
        sys.path.insert(0, str(ROOT / "scripts"))
        from scripts_live import run_live
        return run_live(args, _ordered_cases(), NODE, ROOT)
    chosen = _ordered_cases()
    if args.n > 0:
        chosen = chosen[: args.n]
    staged = [_stage(case) for case in chosen]
    payload = []
    for row, widget in staged:
        if widget is None:
            continue
        payload.append({"group": "stack", "id": row["id"], "claim": row["claim"], "widget": widget})
    results = {}
    if payload:
        blob = ROOT / ".liveart-stack-in.json"
        out = blob.with_suffix(".out.json")
        blob.write_text(json.dumps(payload), encoding="utf-8")
        cmd = ["node", str(NODE), "--in", str(blob), "--out", str(out)]
        if args.sandbox:
            cmd.append("--sandbox")
        subprocess.check_call(cmd, cwd=ROOT)
        for item in json.loads(out.read_text(encoding="utf-8")):
            results[item["id"]] = item
        blob.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
    report = []
    for row, widget in staged:
        got = results.get(row["id"])
        if got is not None:
            row["verify"] = got["verify"]
            row["sandbox"] = got["sandbox"]
            row["reasons"] = got["reasons"]
            row["pixels"] = got.get("pixels", 0)
            shown = got["verify"] == "pass" and (not args.sandbox or got["sandbox"] == "pass")
            row["outcome"] = "show" if shown else "fallback"
        report.append(row)
    shown = sum(1 for row in report if row["outcome"] == "show")
    fallback = len(report) - shown
    text = {
        "n": len(report),
        "show": shown,
        "fallback": fallback,
        "sandbox": bool(args.sandbox),
        "meta": "not called",
        "rows": report,
    }
    rendered = json.dumps(text, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    print(f"{shown} show, {fallback} fallback, {len(report)} cases. Meta not called.")
    for row in report:
        why = ",".join(row["reasons"])
        print(f"{row['id']:<28} {row['select']:<8} {row['outcome']:<9} {row['code']:<22} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
