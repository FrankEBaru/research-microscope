#!/usr/bin/env python3
"""Run draws through the 0.3 verifier and, with --sandbox, the iframe.

No Meta. RRM-80's catalog is read from that branch. RRM-78's emulated
widgets and the widgets its eval expects to reject are imported from this tree.

  python3 scripts/liveart_audit.py --sandbox --out /tmp/liveart-audit.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NODE = ROOT / "apps" / "reader" / "scripts" / "liveart_audit.mjs"
MOCKUPS_REF = "origin/cursor/rrm-80-mockups-2121:rrm/liveart/mockups.json"


def _mockups():
    raw = subprocess.check_output(["git", "show", MOCKUPS_REF], cwd=ROOT, text=True)
    payload = json.loads(raw)
    return payload["widgets"]


def _rows():
    from evals.liveart.cases import cases
    from rrm.liveart.emulated import CATALOG
    from rrm.liveart.offline import gold_widget

    rows = []
    for widget in _mockups():
        rows.append({"group": "rrm80", "id": widget["id"], "claim": "", "widget": widget})
    seen = set()
    for name in ("positional_encoding", "softmax_temperature", "attention_scale", "stddev"):
        widget = gold_widget(name)
        seen.add(widget["id"])
        rows.append({"group": "rrm78", "id": widget["id"], "claim": "", "widget": widget})
    for row in CATALOG:
        widget = row["widget"]
        if widget["id"] in seen:
            continue
        seen.add(widget["id"])
        rows.append({
            "group": "rrm78",
            "id": widget["id"],
            "claim": row["claim"]["text"],
            "widget": widget,
        })
    for case in cases():
        if case["suite"] != "verify" or case.get("accept") is not False:
            continue
        widget = case["widget"]
        rows.append({
            "group": "rrm78-reject",
            "id": case["id"],
            "claim": case["claim"]["text"],
            "widget": widget,
            "expect": case.get("reason", ""),
        })
    return rows


def _bucket(reasons):
    if not reasons:
        return "ok"
    head = reasons[0]
    if head.startswith("slop_inert"):
        return "slop_inert"
    if head.startswith("sandbox"):
        return "sandbox"
    return head


def summarize(rows):
    lines = ["# Auditoría 0.3", ""]
    for group in ("rrm80", "rrm78", "rrm78-reject"):
        got = [row for row in rows if row["group"] == group]
        if not got:
            continue
        verify_pass = sum(1 for row in got if row["verify"] == "pass")
        sandbox_pass = sum(1 for row in got if row["sandbox"] == "pass")
        lines.append(f"## {group}")
        lines.append(f"{len(got)} widgets. Verifier pass {verify_pass}. Sandbox pass {sandbox_pass}.")
        lines.append("")
        counts = Counter(_bucket(row["reasons"]) for row in got if row["verify"] == "fail" or row["sandbox"] == "fail")
        if counts:
            lines.append("Fallos:")
            for name, n in counts.most_common():
                lines.append(f"- {name}: {n}")
            lines.append("")
        lines.append("| id | verify | sandbox | reasons |")
        lines.append("| --- | --- | --- | --- |")
        for row in got:
            why = ", ".join(row["reasons"]) or ""
            lines.append(f"| {row['id']} | {row['verify']} | {row['sandbox']} | {why} |")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--summary", default="")
    args = parser.parse_args()
    payload = _rows()
    blob = ROOT / ".liveart-audit-in.json"
    blob.write_text(json.dumps(payload), encoding="utf-8")
    cmd = ["node", str(NODE), "--in", str(blob), "--out", str(blob.with_suffix(".out.json"))]
    if args.sandbox:
        cmd.append("--sandbox")
    subprocess.check_call(cmd, cwd=ROOT)
    rows = json.loads(blob.with_suffix(".out.json").read_text(encoding="utf-8"))
    # The node script drops the expect field. Join it back for the reject group.
    expect = {row["id"]: row.get("expect", "") for row in payload if row["group"] == "rrm78-reject"}
    for row in rows:
        if row["group"] == "rrm78-reject":
            row["expect"] = expect.get(row["id"], "")
    text = json.dumps(rows, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    summary = summarize(rows)
    if args.summary:
        Path(args.summary).write_text(summary, encoding="utf-8")
    print(summary.split("## rrm78-reject")[0][:4000])
    agreed = 0
    holes = []
    for row in rows:
        if row["group"] != "rrm78-reject":
            continue
        if row["verify"] == "fail":
            agreed += 1
        else:
            holes.append(row["id"])
    print(f"rrm78-reject agreed {agreed}, holes {holes}")
    blob.unlink(missing_ok=True)
    blob.with_suffix(".out.json").unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
