"""--live mode for liveart_stack.py: the five RRM-78 prompts against the real model.

One pass, no retries. Local 0.3 verifier + sandbox grade the code. Spend per call from
usage x contributor rate (rrm.reader.metacall). The key is only read by metacall.post_responses.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _call(stage, system, user, schema, tokens, effort):
    from rrm.reader.metacall import MODEL, parse_json, post_responses, response_text, usage_cost

    body = {
        "model": MODEL,
        "store": False,
        "reasoning": {"effort": effort},
        "max_output_tokens": tokens,
        "input": [{"role": "developer", "content": system}, {"role": "user", "content": user}],
        "text": {"format": {"type": "json_schema", "name": stage, "strict": True, "schema": schema}},
    }
    t0 = time.time()
    try:
        payload = post_responses(body, timeout=180 if stage == "codegen" else 120)
        err = ""
    except Exception as exc:  # one pass, no retries
        payload, err = {}, str(exc)[:200]
    text = response_text(payload)
    return {
        "stage": stage,
        "secs": round(time.time() - t0, 1),
        "error": err,
        "status": payload.get("status"),
        "usage": usage_cost(payload.get("usage")),
        "text": text,
        "json": parse_json(text),
    }


def _grade(node, root, rid, claim, widget, sandbox):
    blob = root / f".live-{rid}.json"
    out = blob.with_suffix(".out.json")
    blob.write_text(json.dumps([{"group": "stack", "id": rid, "claim": claim, "widget": widget}]), encoding="utf-8")
    cmd = ["node", str(node), "--in", str(blob), "--out", str(out)] + (["--sandbox"] if sandbox else [])
    try:
        subprocess.run(cmd, cwd=root, check=True, timeout=180, capture_output=True)
        got = json.loads(out.read_text(encoding="utf-8"))[0]
    except Exception as exc:
        got = {"verify": "error", "sandbox": "error", "reasons": [f"grader: {str(exc)[:120]}"]}
    blob.unlink(missing_ok=True)
    out.unlink(missing_ok=True)
    return got


def run_live(args, cases, node, root):
    from rrm.liveart import prompts as P

    sch = P.schemas()
    if args.ids:
        want = args.ids.split(",")
        by = {c["id"]: c for c in cases}
        try:  # RRM-78 probe lists (bank claims not in the select suite)
            from evals.liveart.probe_claims import claims as probe_claims
            for row in probe_claims():
                by.setdefault(row["id"], {"id": row["id"], "claim": row["claim"]})
        except Exception:
            pass
        cases = [by[i] for i in want if i in by]
    elif args.n > 0:
        cases = cases[: args.n]
    raw = Path(args.raw) if args.raw else None
    if raw:
        raw.mkdir(parents=True, exist_ok=True)
    total, rows, code_fails, code_seen = 0.0, [], 0, 0
    for case in cases:
        claim = case["claim"]
        calls, row = [], {"id": case["id"], "claim": claim.get("text", "")[:120], "cost": 0.0}

        def go(stage, msgs, tokens, effort="low"):
            nonlocal total
            c = _call(stage, msgs[0], msgs[1], sch[stage], tokens, effort)
            calls.append(c)
            total += c["usage"]["cost_usd"]
            row["cost"] += c["usage"]["cost_usd"]
            return c["json"] or {}

        sel = go("selector", P.selector_messages(claim), 600, "minimal")
        row.update(select=sel.get("merit", "parse_fail"), topic=sel.get("topic", ""), reason=sel.get("reason", ""))
        row.update(verify="skipped", sandbox="skipped", model_verifier="", reasons=[])
        if row["select"] == "widget" and total < args.cap:
            q = go("questions", P.question_messages(claim, row["topic"]), 900, "minimal").get("questions") or []
            ex = go("explain", P.explain_messages(claim, row["topic"]), 900, "minimal").get("explain") or ""
            w = go("codegen", P.codegen_messages(claim, q, ex), 6000, "low")
            code_seen += 1
            if not w.get("draw"):
                row.update(verify="no_output", reasons=[calls[-1]["error"] or f"empty/parse ({calls[-1]['status']})"])
            else:
                g = _grade(node, root, case["id"], claim.get("text", ""), w, args.sandbox)
                row.update(verify=g.get("verify"), sandbox=g.get("sandbox"), reasons=g.get("reasons") or [])
                mv = go("verifier", P.verifier_messages(claim, w), 900, "minimal")
                row["model_verifier"] = "accept" if mv.get("accept") else ("reject:" + ";".join(mv.get("reasons") or [])[:80])
            ok = row["verify"] == "pass" and (not args.sandbox or row["sandbox"] == "pass")
            row["outcome"] = "show" if ok else "fallback"
            code_fails += 0 if ok else 1
        else:
            row["outcome"] = "no_widget"
        row["cost"] = round(row["cost"], 6)
        rows.append(row)
        if raw:
            (raw / f"{case['id']}.json").write_text(json.dumps({"row": row, "calls": calls}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{row['id']:<20} {row['select']:<9} {row['verify']:<10} {row['sandbox']:<8} ${row['cost']:.5f} tot ${total:.4f} {','.join(map(str,row['reasons']))[:70]}", flush=True)
        if total >= args.cap:
            print("CAP HIT, stopping"); break
        if code_seen <= 8 and code_fails >= 5:
            print("EARLY STOP: 5 code fails in first 8"); break
    shown = sum(r["outcome"] == "show" for r in rows)
    summary = {"n": len(rows), "code": code_seen, "show": shown, "total_usd": round(total, 6), "rows": rows}
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"show {shown}/{code_seen} code outputs, {len(rows)} claims, total ${total:.5f}")
    return 0
