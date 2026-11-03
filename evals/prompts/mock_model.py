"""Modelo grabado. Repite el fallo del fixture y obedece inyecciones.

review() tiene que corregir esos dos casos. El resto ya viene bien.
"""

import json

from rrm.reader.promptguard import equivalent_claim, injection, shares


def naive_class(kind):
    if kind == "injection":
        return "coincide"
    if kind == "quantity_hedge":
        return "contradice"
    if kind in ("absurd", "off_topic"):
        return "sin_respaldo"
    if kind in ("almost", "quantity_conflict"):
        return "contradice"
    if kind in ("correct", "accurate"):
        return "coincide"
    if kind == "te_falto":
        return "te_falto"
    raise KeyError(kind)


def verifier_keep(part, text, cite, answer):
    """Reglas de _CHECK, más el rechazo a órdenes metidas en el dato."""
    if injection(text) or injection(answer or ""):
        return False
    if part == "coincide":
        return equivalent_claim(text, cite) or shares(text, cite)
    if part == "contradice":
        if equivalent_claim(text, cite):
            return False
        return True
    if part == "sin_respaldo":
        return not shares(text, cite)
    if part == "te_falto":
        return bool(cite) and shares(text, cite) and not shares(answer or "", cite)
    return False


def _payload(text):
    return {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 10, "output_tokens": 4, "input_tokens_details": {"cached_tokens": 0}},
    }


def recorded_complete(case):
    """Primera llamada: el veredicto grabado. Segunda: el verificador deja pasar."""
    state = {"n": 0}

    def complete(body):
        state["n"] += 1
        if state["n"] == 1:
            clase = naive_class(case["kind"])
            cite = case["gap"] if clase == "te_falto" else ("" if clase == "sin_respaldo" else case["section"])
            item = {
                "text": case["gap"] or case["answer"],
                "clase": clase if clase != "te_falto" else "sin_respaldo",
                "cite": cite,
                "paper_id": "" if clase == "sin_respaldo" else "1",
            }
            raw = {"afirmaciones": [], "te_falto": []}
            if clase == "te_falto":
                raw["te_falto"].append({"text": case["gap"], "cite": case["gap"], "paper_id": "1"})
            else:
                raw["afirmaciones"].append(item)
            return _payload(json.dumps(raw))
        listed = body["input"][1]["content"]
        n = sum(1 for line in listed.splitlines() if line[:1].isdigit() and ". " in line[:4])
        return _payload(json.dumps({"keep": [True] * max(n, 1)}))

    return complete
