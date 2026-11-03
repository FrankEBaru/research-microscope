"""Tabla pass/fail. Offline. No abre la red y no escribe un reporte con cifras."""

from rrm.liveart.contract import LIMITS
from rrm.liveart.fewshots import DRAWS
from rrm.liveart.offline import TOPICS, explain_for, gold_widget, questions_for, select_claim, verify_widget

from evals.liveart.cases import cases


def _grade(case):
    suite = case["suite"]
    if suite == "select":
        got = select_claim(case["claim"])
        ok = got["merit"] == case["merit"] and got["topic"] == case["topic"] and got["reason"] == case["reason"]
        shown = f"{got['merit']}/{got['topic'] or '-'}/{got['reason']}"
        return ok, shown
    if suite == "questions":
        got = questions_for(case["claim"])
        ok = got["reason"] == case["reason"]
        if case["reason"] == "bank":
            blob = " ".join(item["q"] for item in got["questions"]).casefold()
            ok = ok and LIMITS["questions_min"] <= len(got["questions"]) <= LIMITS["questions_max"]
            ok = ok and all(item["q"].endswith("?") and "ignore previous" not in item["q"].casefold() for item in got["questions"])
            ok = ok and case["mark"] in blob and "fetch" not in blob
        else:
            ok = ok and got["questions"] == []
        return ok, got["reason"]
    if suite == "explain":
        got = explain_for(case["claim"])
        ok = got["reason"] == case["reason"]
        if case["reason"] == "bank":
            text = got["explain"]
            ok = ok and 0 < len(text) <= LIMITS["explain"] and case["mark"] in text.casefold()
            ok = ok and "ignore previous" not in text.casefold()
        else:
            ok = ok and got["explain"] == ""
        return ok, got["reason"] or "vacio"
    if suite == "verify":
        got = verify_widget(case["claim"], case["widget"])
        ok = got["accept"] is case["accept"]
        if "reason" in case:
            ok = ok and case["reason"] in got["reasons"]
        shown = "accept" if got["accept"] else ",".join(got["reasons"])
        return ok, shown
    if suite == "bank":
        for topic in TOPICS:
            text = topic["explain"]
            if not (0 < len(text) <= LIMITS["explain"] and topic["mark"] in text.casefold()):
                return False, "explain:" + topic["name"]
            if not LIMITS["questions_min"] <= len(topic["questions"]) <= LIMITS["questions_max"]:
                return False, "count:" + topic["name"]
            for q, why in topic["questions"]:
                if not q.endswith("?") or not (12 <= len(q) <= LIMITS["question"]) or not why.strip() or len(why) > LIMITS["why"]:
                    return False, "question:" + topic["name"]
        for name in DRAWS:
            got = verify_widget(_claim_for(name), gold_widget(name))
            if got["accept"] is not True:
                return False, name + ":" + ",".join(got["reasons"])
        return True, "bounds"
    raise KeyError(suite)


def _claim_for(topic):
    from evals.liveart.cases import PE, SCALE, STD, TEMP

    return {
        "positional_encoding": PE,
        "softmax_temperature": TEMP,
        "attention_scale": SCALE,
        "stddev": STD,
    }[topic]


def run(rows=None):
    out = []
    for case in rows if rows is not None else cases():
        ok, shown = _grade(case)
        out.append({"id": case["id"], "suite": case["suite"], "got": shown, "ok": ok})
    return out


def format_table(rows):
    lines = ["liveart prompts (offline)"]
    lines.append(f"{'id':<24} {'got':<42} result")
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        lines.append(f"{row['id']:<24} {row['got']:<42} {mark}")
    passed = sum(1 for row in rows if row["ok"])
    lines.append(f"{passed} passed, {len(rows) - passed} failed, {len(rows)} total")
    lines.append("live: not run. This process did not call Meta.")
    return "\n".join(lines)


def main():
    rows = run()
    print(format_table(rows))
    return 0 if all(row["ok"] for row in rows) else 1
