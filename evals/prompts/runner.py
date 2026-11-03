"""Tabla pass/fail. Offline por defecto. RRM_EVAL_LIVE=1 llama a Meta y no se usa en CI.

Al correr el módulo escribe el paquete que se copia a compass:
evals/prompts/cases.json, results/offline.json y REPORT.md.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from evals.prompts.cases import SECTIONS, judge_cases, verifier_cases
from evals.prompts.mock_model import recorded_complete, verifier_keep
from rrm.reader.feedback import _CHECK, _body, _dev, review
from rrm.reader.metacall import _IN, _OUT
from rrm.reader.promptguard import GUARD_ES, guard_on, wrap_user

# muse-spark-1.3-contributor, los mismos precios que rrm/reader/metacall.py.
_CALLS_PER_JUDGE = 2
_OUT_TOKENS = 80


def _box(parts):
    for name in ("coincide", "contradice", "sin_respaldo", "te_falto"):
        if parts.get(name):
            return name
    return "vacio"


def grade_judge(case, complete=None):
    citations = [{"paper": "1", "text": case["section"], "section": case["id"]}]
    call = complete or recorded_complete(case)
    parts, _note, _cost = review(case["answer"], citations, complete=call)
    return _box(parts)


def grade_verifier(case, *, live=False):
    if not live:
        return verifier_keep(case["part"], case["text"], case["cite"], case["answer"])
    from rrm.reader.metacall import parse_json, post_responses, response_text

    listed = f"0. {case['part']} | 1 | {case['cite']} | {case['text']}"
    phrases = f"1. paper 1: {case['cite']}"
    user = f"Frases:\n{phrases}\n\nPuntos:\n{listed}"
    if guard_on():
        user = wrap_user("CHEQUEO", user)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"keep": {"type": "array", "items": {"type": "boolean"}}},
        "required": ["keep"],
    }
    payload = post_responses(_body(user, "chequeo", schema, 800, _dev(_CHECK, quantity=True)))
    data = parse_json(response_text(payload)) or {}
    keep = data.get("keep")
    return bool(keep[0]) if isinstance(keep, list) and keep else False


def estimate(cases=None):
    """Un pase en vivo. Tokens ≈ caracteres/4, dos llamadas por caso del juez.

    Es un estimado, no una factura. Precios de contributor en metacall.py.
    """
    judges = cases if cases is not None else judge_cases()
    checks = verifier_cases()
    chars = 0
    for case in judges:
        one = len(case["section"]) + len(case["answer"]) + len(_CHECK) + len(GUARD_ES) + 900
        chars += one * _CALLS_PER_JUDGE
    for case in checks:
        chars += len(case["text"]) + len(case["cite"]) + len(_CHECK) + 500
    calls = len(judges) * _CALLS_PER_JUDGE + len(checks)
    incoming = max(1, chars // 4)
    outgoing = calls * _OUT_TOKENS
    cost = incoming * _IN + outgoing * _OUT
    return {
        "calls": calls,
        "input_tokens": incoming,
        "output_tokens": outgoing,
        "cost_usd": round(cost, 6),
        "model": "muse-spark-1.3-contributor",
    }


def live_on():
    return os.environ.get("RRM_EVAL_LIVE", "").strip() == "1"


def _live_complete(_case):
    from rrm.reader.metacall import post_responses

    def complete(body):
        return post_responses(body)

    return complete


def run(cases=None, *, live=None):
    judges = cases if cases is not None else judge_cases()
    use_live = live_on() if live is None else live
    rows = []
    for case in judges:
        call = _live_complete(case) if use_live else None
        got = grade_judge(case, complete=call)
        rows.append({
            "id": case["id"],
            "suite": "judge",
            "category": case["category"],
            "kind": case["kind"],
            "arxiv": case["arxiv"],
            "section": case["section"],
            "answer": case["answer"],
            "expected": case["expected"],
            "got": got,
            "ok": got == case["expected"],
        })
    for case in verifier_cases():
        got = grade_verifier(case, live=use_live)
        rows.append({
            "id": case["id"],
            "suite": "verifier",
            "category": case["category"],
            "kind": case["part"],
            "arxiv": case.get("arxiv", ""),
            "section": case["cite"],
            "answer": case["answer"],
            "expected": "keep" if case["expected_keep"] else "drop",
            "got": "keep" if got else "drop",
            "ok": got == case["expected_keep"],
        })
    return rows


def format_table(rows, cost):
    lines = ["prompt eval (live)" if live_on() else "prompt eval (offline)"]
    lines.append(f"{'id':<42} {'expected':<14} {'got':<14} result")
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        lines.append(f"{row['id']:<42} {row['expected']:<14} {row['got']:<14} {mark}")
    passed = sum(1 for row in rows if row["ok"])
    lines.append(f"{passed} passed, {len(rows) - passed} failed, {len(rows)} total")
    if live_on():
        lines.append("live: ran (RRM_EVAL_LIVE=1)")
    else:
        lines.append("live: not run. Set RRM_EVAL_LIVE=1 to call Meta. This process did not.")
    lines.append(
        "one live run estimate: ${cost} ({model}, {calls} calls, ~{inn} in / ~{out} out tokens)".format(
            cost=f"{cost['cost_usd']:.4f}",
            model=cost["model"],
            calls=cost["calls"],
            inn=cost["input_tokens"],
            out=cost["output_tokens"],
        )
    )
    return "\n".join(lines)


def _commit():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def write_bundle(rows, cost, root=None):
    """Casos, resultado y reporte en evals/prompts/. Sin claves."""
    folder = Path(root) if root else Path(__file__).resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results").mkdir(exist_ok=True)
    judges = judge_cases()
    checks = verifier_cases()
    payload = {
        "sections": SECTIONS,
        "categories": ["absurd", "sensible", "injection", "near-correct-but-wrong"],
        "judge": judges,
        "verifier": checks,
    }
    (folder / "cases.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    passed = sum(1 for row in rows if row["ok"])
    body = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "commit": _commit(),
        "model": "recorded-mock" if not live_on() else cost["model"],
        "live_model_if_enabled": cost["model"],
        "live": bool(live_on()),
        "passed": passed,
        "failed": len(rows) - passed,
        "total": len(rows),
        "cost_estimate_usd": cost["cost_usd"],
        "cost_estimate": cost,
        "results": rows,
    }
    (folder / "results" / "offline.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Prompt eval",
        "",
        f"- Fecha: {body['date']}",
        f"- Commit: `{body['commit']}`",
        f"- Modelo: {body['model']} (en vivo sería {cost['model']}; no se llamó a Meta en esta corrida)."
        if not body["live"]
        else f"- Modelo: {body['model']} (corrida en vivo).",
        f"- Resultado: {passed} passed, {len(rows) - passed} failed, {len(rows)} total",
        f"- Costo estimado de un pase en vivo: ${cost['cost_usd']:.4f} ({cost['calls']} llamadas, ~{cost['input_tokens']} in / ~{cost['output_tokens']} out).",
        "",
        "| id | categoría | esperado | obtuvo | |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        lines.append(f"| {row['id']} | {row['category']} | {row['expected']} | {row['got']} | {mark} |")
    lines.append("")
    (folder / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return folder


def main(write=False):
    # RRM_EVAL_LIVE=1 llama a Meta. Este módulo no lo prende solo.
    rows = run()
    cost = estimate()
    print(format_table(rows, cost))
    if write and not live_on():
        write_bundle(rows, cost)
    return 0 if all(row["ok"] for row in rows) else 1
