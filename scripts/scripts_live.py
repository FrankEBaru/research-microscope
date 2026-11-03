"""--live mode for liveart_stack.py: the five RRM-78 prompts against a real model.

One pass. A 504 or a read timeout is retried once; that retry is not a model retry.
Any other error is not retried. Local 0.3 verifier + sandbox grade the code.

Configs: spark (contributor for every stage), wonder (muse-wonder-1.0 for every
stage), hybrid (Wonder writes the spec, Spark writes the code).
Prices are the per-1M rates in MODELOS-META. --max-usd refuses a call whose
worst-case cost would pass the cap. The key is only read by metacall.post_responses.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


# USD per token. MODELOS-META, 3 nov 2026: contributor and Wonder standard.
SPARK = "muse-spark-1.3-contributor"
WONDER = "muse-wonder-1.0"
_PER_M = {
    SPARK: (0.10, 0.002, 0.20),
    WONDER: (4.00, 0.20, 20.00),
}
_STAGES = ("selector", "spec", "codegen", "verifier")
CONFIGS = {
    "spark": {stage: SPARK for stage in _STAGES},
    "wonder": {stage: WONDER for stage in _STAGES},
    "hybrid": {"selector": SPARK, "spec": WONDER, "codegen": SPARK, "verifier": SPARK},
}
# Expected output tokens for a dry run. The live call may be shorter; the
# budget check uses max_output_tokens instead, so it stops early rather than late.
_EXPECT_OUT = {
    "selector": 200, "spec": 1200, "questions": 600, "explain": 250,
    "codegen": 2500, "repair": 2500, "verifier": 900,
}


def _infra(err):
    """A gateway 504 or a client read timeout. Nothing else is retried."""
    text = (err or "").lower()
    return "504" in text or "timed out" in text


def _rates(model):
    try:
        pin, pcache, pout = _PER_M[model]
    except KeyError:
        raise SystemExit(f"unknown model {model}") from None
    return pin / 1_000_000, pcache / 1_000_000, pout / 1_000_000


def cost_of(usage, model):
    """Measured tokens times the rate for this model. Empty usage is zero."""
    if not isinstance(usage, dict):
        usage = {}
    incoming = int(usage.get("input_tokens") or 0)
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached = min(int(details.get("cached_tokens") or 0), incoming)
    outgoing = int(usage.get("output_tokens") or 0)
    pin, pcache, pout = _rates(model)
    cost = (incoming - cached) * pin + cached * pcache + outgoing * pout
    return {
        "input_tokens": incoming,
        "cached_tokens": cached,
        "output_tokens": outgoing,
        "cost_usd": round(cost, 8),
    }


def _ceiling(model, chars, max_out):
    """Worst case before the call: input is chars/4, output is the cap."""
    pin, _pcache, pout = _rates(model)
    inn = max(1, (chars + 3) // 4)
    return inn * pin + int(max_out) * pout


def stop_early(args, code_seen, code_fails):
    """Five mount failures in the first eight. --no-early-stop keeps the probe going."""
    if getattr(args, "no_early_stop", False):
        return False
    return code_seen <= 8 and code_fails >= 5


def _spec_cut(call):
    """The spec stopped mid-JSON. An HTTP error is not a cut, so it is not retried."""
    if not call or call.get("error"):
        return False
    if call.get("status") == "incomplete":
        return True
    body = call.get("json")
    if not isinstance(body, dict):
        return True
    controls = body.get("controls")
    if not body.get("archetype") or not isinstance(controls, list) or not controls:
        return True
    if not str(body.get("explain") or "").strip():
        return True
    return False


def _call(stage, system, user, schema, tokens, effort, model=SPARK):
    from rrm.reader.metacall import parse_json, post_responses, response_text

    body = {
        "model": model,
        "store": False,
        "reasoning": {"effort": effort},
        "max_output_tokens": tokens,
        "input": [{"role": "developer", "content": system}, {"role": "user", "content": user}],
        "text": {"format": {"type": "json_schema", "name": stage, "strict": True, "schema": schema}},
    }
    t0 = time.time()
    payload, err = {}, ""
    for attempt in (0, 1):
        try:
            payload = post_responses(body, timeout=180 if stage in ("codegen", "repair") else 120)
            err = ""
            break
        except Exception as exc:
            payload, err = {}, str(exc)[:200]
            if attempt == 0 and _infra(err):
                continue
            break
    text = response_text(payload)
    return {
        "stage": stage,
        "model": model,
        "secs": round(time.time() - t0, 1),
        "error": err,
        "status": payload.get("status"),
        "usage": cost_of(payload.get("usage"), model),
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


# Live max_output_tokens. The dry run prices _EXPECT_OUT, which is shorter.
_MAX_OUT = {
    "selector": 600, "spec": 2400, "questions": 900, "explain": 900,
    "codegen": 6000, "repair": 6000, "verifier": 1400,
}
_EFFORT = {
    "selector": "minimal", "spec": "minimal", "questions": "minimal", "explain": "minimal",
    "codegen": "low", "repair": "low", "verifier": "minimal",
}


def _pick(args, cases):
    """--ids wins over --n. Probe-2/3 and the RRM-85 eight are addressable by id."""
    if not getattr(args, "ids", ""):
        n = getattr(args, "n", 0)
        return cases[:n] if n > 0 else list(cases)
    want = [item.strip() for item in args.ids.split(",") if item.strip()]
    by = {c["id"]: c for c in cases}
    from evals.liveart.probe_claims import claims as probe_claims, rrm85
    for row in probe_claims():
        by.setdefault(row["id"], {"id": row["id"], "claim": row["claim"]})
    for row in rrm85():
        by.setdefault(row["id"], {"id": row["id"], "claim": row["claim"]})
    missing = [item for item in want if item not in by]
    if missing:
        raise SystemExit("unknown ids: " + ",".join(missing))
    return [by[item] for item in want]


def _config(args):
    name = getattr(args, "config", None) or "spark"
    try:
        return name, CONFIGS[name]
    except KeyError:
        raise SystemExit(f"unknown config {name}") from None


def _limits(args):
    max_usd = getattr(args, "max_usd", None)
    cap = getattr(args, "cap", None)
    if cap is None:
        cap = max_usd if max_usd is not None else 1.0
    return max_usd, cap


def _blank():
    return {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0}


def _add(bucket, model, usage):
    slot = bucket.setdefault(model, _blank())
    slot["calls"] += 1
    slot["input_tokens"] += usage["input_tokens"]
    slot["cached_tokens"] += usage["cached_tokens"]
    slot["output_tokens"] += usage["output_tokens"]
    slot["cost_usd"] = round(slot["cost_usd"] + usage["cost_usd"], 8)


def _summary(config, dry, max_usd, cap, total, rows, bucket, stopped, code_seen, shown, extra=None):
    tokens = _blank()
    for slot in bucket.values():
        tokens["input_tokens"] += slot["input_tokens"]
        tokens["cached_tokens"] += slot["cached_tokens"]
        tokens["output_tokens"] += slot["output_tokens"]
    body = {
        "config": config,
        "dry_run": dry,
        "max_usd": max_usd,
        "cap_usd": cap,
        "total_usd": round(total, 6),
        "stopped": stopped,
        "tokens": {
            "input": tokens["input_tokens"],
            "cached": tokens["cached_tokens"],
            "output": tokens["output_tokens"],
        },
        "by_model": bucket,
        "n": len(rows),
        "code": code_seen,
        "show": shown,
        "rows": rows,
    }
    if extra:
        body.update(extra)
    return body


def _write_summary(args, summary):
    if getattr(args, "out", ""):
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


def _chars(msgs):
    return len(msgs[0]) + len(msgs[1])


def _estimate(model, msgs, stage):
    """Input is chars/4. Output is the expected length, not the cap."""
    inn = max(1, (_chars(msgs) + 3) // 4)
    out = _EXPECT_OUT[stage]
    pin, _pcache, pout = _rates(model)
    usage = {
        "input_tokens": inn,
        "cached_tokens": 0,
        "output_tokens": out,
        "cost_usd": round(inn * pin + out * pout, 8),
    }
    doubled = round(inn * pin + (out * 2) * pout, 8)
    return usage, doubled


def _dry_run(args, cases, models, config, cap, max_usd):
    """Price the real prompts. The spec reply is not known yet, so codegen is
    padded by that expected size. Repair is priced apart and not spent unless
    the gate rejects. No HTTP."""
    from rrm.liveart import prompts as P
    from rrm.liveart.archetypes import archetype_for, shots_for
    from rrm.liveart.offline import select_claim

    bucket, rows = {}, []
    total = total_x2 = ceiling_sum = 0.0
    repair_total = repair_ceiling_sum = 0.0
    spent_expect = allow = 0.0
    code_seen = 0
    for case in cases:
        claim = case["claim"]
        decision = select_claim(claim)
        topic = decision["topic"]
        stages = [("selector", P.selector_messages(claim))]
        repair_msgs = None
        if decision["merit"] == "widget":
            spec_msgs = P.spec_messages(claim, topic)
            pad = "x" * (_EXPECT_OUT["spec"] * 4)
            arch = archetype_for(topic)
            shots = shots_for(arch, topic, case["id"])
            spec = {
                "archetype": arch,
                "controls": [],
                "derived": [],
                "threshold_formula": "",
                "direction": [],
                "questions": [],
                "explain": pad,
            }
            code = P.codegen_messages(claim, [{"q": "?", "why": "?"}], pad, shots=shots, spec=spec)
            widget = {
                "id": "x", "topic": topic or "x", "title": "x",
                "explain": pad,
                "questions": [], "controls": [],
                "draw": "x" * (_EXPECT_OUT["codegen"] * 4),
            }
            check = P.verifier_messages(claim, widget, ["slop_inert:x"])
            stages.extend([("spec", spec_msgs), ("codegen", code), ("verifier", check)])
            repair_msgs = P.repair_messages(claim, pad, [], widget, ["direction"], shots=shots, spec=spec)
            code_seen += 1
        calls = []
        cost = cost_x2 = 0.0
        for stage, msgs in stages:
            model = models[stage]
            usage, doubled = _estimate(model, msgs, stage)
            ceiling = round(_ceiling(model, _chars(msgs), _MAX_OUT[stage]), 8)
            _add(bucket, model, usage)
            cost += usage["cost_usd"]
            cost_x2 += doubled
            calls.append({
                "stage": stage, "model": model, "usage": usage,
                "cost_x2_usd": doubled, "ceiling_usd": ceiling,
            })
            allow = max(allow, spent_expect + ceiling)
            spent_expect += usage["cost_usd"]
            ceiling_sum += ceiling
            print(
                f"  {stage:<10} {model} in {usage['input_tokens']} out {usage['output_tokens']} "
                f"${usage['cost_usd']:.5f} (outx2 ${doubled:.5f})",
                flush=True,
            )
        if repair_msgs is not None:
            model = models["codegen"]
            usage, _doubled = _estimate(model, repair_msgs, "repair")
            ceiling = round(_ceiling(model, _chars(repair_msgs), _MAX_OUT["repair"]), 8)
            repair_total += usage["cost_usd"]
            repair_ceiling_sum += ceiling
            allow = max(allow, spent_expect + ceiling)
            print(
                f"  {'repair':<10} {model} in {usage['input_tokens']} out {usage['output_tokens']} "
                f"${usage['cost_usd']:.5f} (only if the gate rejects)",
                flush=True,
            )
        total += cost
        total_x2 += cost_x2
        row = {
            "id": case["id"],
            "claim": claim.get("text", "")[:120],
            "select": decision["merit"],
            "topic": topic,
            "verify": "dry",
            "sandbox": "dry",
            "reasons": [],
            "outcome": "dry",
            "cost": round(cost, 6),
            "cost_x2_usd": round(cost_x2, 6),
            "calls": calls,
        }
        rows.append(row)
        print(f"{row['id']:<20} {row['select']:<9} dry ${cost:.5f} x2 ${cost_x2:.5f} tot ${total:.4f}", flush=True)
    summary = _summary(
        config, True, max_usd, cap, total, rows, bucket, "", code_seen, 0,
        {
            "output_x2_usd": round(total_x2, 6),
            "ceiling_usd": round(ceiling_sum, 6),
            "allow_usd": round(allow, 6),
            "repair_usd": round(repair_total, 6),
            "with_repair_usd": round(total + repair_total, 6),
            "with_repair_ceiling_usd": round(ceiling_sum + repair_ceiling_sum, 6),
        },
    )
    _write_summary(args, summary)
    print(
        f"dry-run {config}: {len(rows)} claims, {code_seen} widgets, "
        f"${total:.5f}, with repair ${total + repair_total:.5f}, "
        f"ceiling ${ceiling_sum:.5f}, with repair ceiling ${ceiling_sum + repair_ceiling_sum:.5f}"
    )
    return 0


def run_live(args, cases, node, root):
    from rrm.liveart import prompts as P

    config, models = _config(args)
    max_usd, cap = _limits(args)
    cases = _pick(args, cases)
    if getattr(args, "dry_run", False):
        return _dry_run(args, cases, models, config, cap, max_usd)

    sch = P.schemas()
    raw = Path(args.raw) if getattr(args, "raw", "") else None
    if raw:
        raw.mkdir(parents=True, exist_ok=True)
    total, rows, code_fails, code_seen = 0.0, [], 0, 0
    bucket, stopped = {}, ""
    for case in cases:
        if stopped:
            break
        claim = case["claim"]
        calls, row, final = [], {"id": case["id"], "claim": claim.get("text", "")[:120], "cost": 0.0}, None

        def go(stage, msgs):
            nonlocal total, stopped
            model = models[stage] if stage in models else models["codegen"]
            tokens = _MAX_OUT[stage]
            schema = sch["codegen"] if stage == "repair" else sch[stage]
            ceiling = _ceiling(model, _chars(msgs), tokens)
            if max_usd is not None and total + ceiling > max_usd:
                stopped = "budget"
                print(
                    f"BUDGET: next {stage} call would pass max-usd {max_usd:.4f} "
                    f"(ceiling ${ceiling:.4f}, spent ${total:.4f}), stopping",
                    flush=True,
                )
                return None
            if total >= cap:
                stopped = "cap"
                print("CAP HIT, stopping", flush=True)
                return None
            got = _call(stage, msgs[0], msgs[1], schema, tokens, _EFFORT[stage], model)
            calls.append(got)
            _add(bucket, model, got["usage"])
            total += got["usage"]["cost_usd"]
            row["cost"] += got["usage"]["cost_usd"]
            u = got["usage"]
            print(
                f"  {stage:<10} {model} in {u['input_tokens']} cache {u['cached_tokens']} "
                f"out {u['output_tokens']} ${u['cost_usd']:.5f}",
                flush=True,
            )
            return got

        sel = go("selector", P.selector_messages(claim))
        if sel is None:
            row.update(select="stopped", topic="", verify="skipped", sandbox="skipped", outcome="stopped", reasons=[stopped])
        else:
            parsed = sel["json"] or {}
            row.update(select=parsed.get("merit", "parse_fail"), topic=parsed.get("topic", ""), reason=parsed.get("reason", ""))
            row.update(verify="skipped", sandbox="skipped", model_verifier="", reasons=[])
            if row["select"] == "widget":
                from rrm.liveart.archetypes import archetype_for, shots_for
                from rrm.liveart.gate import (
                    finish_explain,
                    quality_gate,
                    regime_out_of_range,
                    sanitize_widget,
                    seal_widget,
                )

                spec_msgs = P.spec_messages(claim, row["topic"])
                spec_call = go("spec", spec_msgs)
                spec_body = spec_call.get("json") if spec_call and isinstance(spec_call.get("json"), dict) else {}
                if spec_call is not None and (_spec_cut(spec_call) or regime_out_of_range(spec_body)):
                    retried = go("spec", spec_msgs)
                    spec_call = retried if retried is not None else None
                if spec_call is None:
                    row["outcome"] = "stopped"
                    row["reasons"] = [stopped]
                elif _spec_cut(spec_call):
                    row["outcome"] = "fallback"
                    row["reasons"] = ["spec_incomplete"]
                    row["verify"] = "skipped"
                    row["sandbox"] = "skipped"
                elif regime_out_of_range(spec_call.get("json") if isinstance(spec_call.get("json"), dict) else {}):
                    row["outcome"] = "fallback"
                    row["reasons"] = ["regime_range"]
                    row["verify"] = "skipped"
                    row["sandbox"] = "skipped"
                else:
                    spec = spec_call["json"] if isinstance(spec_call.get("json"), dict) else {}
                    explain = finish_explain(spec.get("explain") or "", claim)
                    questions = spec.get("questions") or []
                    arch = spec.get("archetype") or archetype_for(row["topic"])
                    shots = shots_for(arch, row["topic"], case["id"])
                    w_call = go("codegen", P.codegen_messages(claim, questions, explain, shots=shots, spec=spec))
                    if w_call is None:
                        row["outcome"] = "stopped"
                        row["reasons"] = [stopped]
                    else:
                        w = w_call["json"] or {}
                        code_seen += 1
                        if not w.get("draw"):
                            row.update(verify="no_output", reasons=[w_call["error"] or f"empty/parse ({w_call['status']})"])
                        else:
                            w = sanitize_widget(seal_widget(w, explain, questions))
                            gate = quality_gate(w, claim, spec)
                            if gate:
                                fix = go("repair", P.repair_messages(claim, explain, questions, w, gate, shots=shots, spec=spec))
                                fixed = (fix or {}).get("json") or {}
                                if fixed.get("draw"):
                                    fixed = sanitize_widget(seal_widget(fixed, explain, questions))
                                    gate2 = quality_gate(fixed, claim, spec)
                                    if len(gate2) < len(gate):
                                        w, gate = fixed, gate2
                            w_call["json"] = w
                            final = w
                            g = _grade(node, root, case["id"], claim.get("text", ""), w, args.sandbox)
                            row.update(verify=g.get("verify"), sandbox=g.get("sandbox"), reasons=g.get("reasons") or [])
                            row["gate"] = gate
                            mv_call = go("verifier", P.verifier_messages(claim, w, (g.get("reasons") or []) + list(gate)))
                            if mv_call is None:
                                row["model_verifier"] = "stopped"
                            else:
                                mv = mv_call["json"] or {}
                                passed = bool(mv.get("accept")) and not gate
                                why = gate or (mv.get("reasons") or [])
                                row["model_verifier"] = "accept" if passed else ("reject:" + ";".join(why)[:80])
                        engine_ok = row["verify"] == "pass" and (not args.sandbox or row["sandbox"] == "pass")
                        row["outcome"] = "show" if engine_ok and not row.get("gate") else "fallback"
                        code_fails += 0 if engine_ok else 1
            else:
                row["outcome"] = "no_widget"
        row["cost"] = round(row["cost"], 6)
        rows.append(row)
        if raw:
            blob = {"row": row, "calls": calls}
            if final:
                blob["widget"] = final
            (raw / f"{case['id']}.json").write_text(json.dumps(blob, ensure_ascii=False, indent=1), encoding="utf-8")
        print(
            f"{row['id']:<20} {row.get('select',''):<9} {row.get('verify',''):<10} "
            f"{row.get('sandbox',''):<8} ${row['cost']:.5f} tot ${total:.4f} "
            f"{','.join(map(str, row.get('reasons') or []))[:70]}",
            flush=True,
        )
        if not stopped and max_usd is not None and total >= max_usd:
            stopped = "budget"
            print(f"BUDGET: spent ${total:.4f} reached max-usd {max_usd:.4f}, stopping", flush=True)
        if not stopped and total >= cap:
            stopped = "cap"
            print("CAP HIT, stopping", flush=True)
        if not stopped and stop_early(args, code_seen, code_fails):
            stopped = "early"
            print("EARLY STOP: 5 code fails in first 8", flush=True)
    shown = sum(r.get("outcome") == "show" for r in rows)
    summary = _summary(config, False, max_usd, cap, total, rows, bucket, stopped, code_seen, shown)
    summary["gate_pass"] = sum(r.get("gate") == [] for r in rows)
    _write_summary(args, summary)
    print(f"show {shown}/{code_seen} code outputs, {len(rows)} claims, total ${total:.5f}")
    return 0
