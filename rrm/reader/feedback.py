"""Cuatro partes de la caja. Solo frases ya elegidas. Capa 1 aquí; capa 2 es otra llamada."""

from rrm.reader.metacall import add_usage, meta_status, note_for, parse_json, post_responses, response_text, usage_cost
from rrm.reader.metacall import MODEL
from rrm.reader.promptguard import equivalent_claim, guard_on, injection, qty_on, with_guard, wrap_user
from rrm.textcase import cap_first

PARTS = ("coincide", "contradice", "sin_respaldo", "te_falto")
_QUOTED = ("coincide", "contradice", "te_falto")
_PROMPT = (
    "La explicación del lector es una afirmación. Clasifícala contra las frases numeradas, "
    "con una sola clase y una sola entrada en afirmaciones: "
    "coincide si dice lo mismo que una frase (si la repite, también); "
    "contradice si la niega, aunque la frase no contenga la palabra «no»; "
    "sin_respaldo si ninguna frase habla de eso. "
    "En coincide y contradice, cite es un trozo copiado tal cual de esa frase, "
    "sin reescribir el LaTeX, y paper_id es el de la frase. "
    "En sin_respaldo, cite y paper_id van vacíos. "
    "te_falto va aparte: una cosa que las frases dicen y el lector no mencionó. "
    "Su texto habla de lo que dice la cita, y la cita es un trozo literal de esa frase. "
    "No des un veredicto de bien o mal."
)
# RRM-49: la explicación llega ya cortada en oraciones numeradas; cada idea es una afirmación.
_PROMPT_CLAIMS = (
    "La explicación del lector viene en oraciones numeradas. Divídela en afirmaciones: "
    "una por oración, o más si una oración une dos ideas; no juntes oraciones. "
    "text es la afirmación con las palabras del lector. "
    "Clasifica cada una contra las frases numeradas: "
    "coincide si dice lo mismo que una frase (si la repite, también); "
    "contradice si la niega o afirma lo contrario, aunque la frase no contenga la palabra «no»; "
    "sin_respaldo si ninguna frase habla de eso. "
    "En coincide y contradice, cite es un trozo copiado tal cual de esa frase, "
    "sin reescribir el LaTeX, y paper_id es el de la frase. "
    "En sin_respaldo, cite y paper_id van vacíos. "
    "te_falto va aparte: hasta dos cosas importantes que las frases dicen y el lector no mencionó. "
    "Su texto habla de lo que dice la cita, y la cita es un trozo literal de esa frase. "
    "No des un veredicto de bien o mal."
)
_CHECK = (
    "keep[i] es true o false. "
    "Si la parte es contradice, true cuando el texto dice que la cita es falsa o afirma lo contrario. "
    "La frase «It is false that» seguida de lo que dice la cita es true. "
    "Si la parte es coincide, true cuando el texto repite la cita o dice lo mismo. "
    "Si la parte es sin_respaldo, true cuando el texto habla de otra cosa. "
    "Si la parte es te_falto, true cuando la cita aporta un hecho que el texto no dijo. "
    "No uses false solo porque la cita no contiene la palabra no."
)


def known_caja(data):
    """El JSON del juez tiene el esquema nuevo o el de cuatro partes. Otra forma no pasa."""
    if not isinstance(data, dict):
        return False
    if "afirmaciones" in data or "te_falto" in data:
        claims = data.get("afirmaciones", [])
        missed = data.get("te_falto", [])
        return isinstance(claims, list) and isinstance(missed, list)
    return any(isinstance(data.get(part), list) for part in PARTS)


def _dev(prompt, quantity=False):
    return with_guard(prompt, quantity=quantity)


def _pack(explanation, phrases):
    block = f"Explicación:\n{explanation}\n\nFrases:\n{phrases}"
    if not guard_on():
        return block
    return wrap_user("EXPLICACION", f"Explicación:\n{explanation}") + "\n\n" + wrap_user("FRASES", f"Frases:\n{phrases}")


def soften_quantities(parts, explanation):
    """Contradice pasa a coincide si la única diferencia es la misma magnitud."""
    if not qty_on():
        return parts
    kept, moved = [], []
    for item in parts.get("contradice") or []:
        cite = item.get("cite") or ""
        text = item.get("text") or ""
        if equivalent_claim(text, cite) or equivalent_claim(explanation, cite):
            moved.append(item)
        else:
            kept.append(item)
    out = {part: list(parts.get(part) or []) for part in PARTS}
    out["contradice"] = kept
    out["coincide"] = list(out["coincide"]) + moved
    return out


def refuse_injection(parts, explanation):
    """Un pedido de veredicto o de filtrar el prompt no se clasifica como respaldo."""
    if not guard_on() or not injection(explanation):
        return parts
    text = cap_first(" ".join((explanation or "").split()))[:240]
    out = {part: [] for part in PARTS}
    if text:
        out["sin_respaldo"].append({"text": text})
    return out


def _claims_on():
    import os
    return os.environ.get("RRM_CLAIMS", "").strip().lower() not in ("0", "off", "false", "no")


def _sentences(text):
    """Corte barato por oración; Meta afina dentro de la misma llamada."""
    import re
    flat = " ".join((text or "").split())
    # RRM-51: a semicolon is not a sentence end; the cut left «attention is only used…» lowercase.
    parts = re.split(r"(?<=[.!?])\s+(?=[^\W\d_¿¡]|[¿¡])", flat)
    return [part for part in (p.strip() for p in parts) if part]


def _flat(text):
    import re
    return re.sub(r"\s+", "", text or "").casefold()


def _schema(name, schema):
    return {"type": "json_schema", "name": name, "strict": True, "schema": schema}


def _point_schema():
    claim = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "text": {"type": "string"},
            "clase": {"type": "string", "enum": ["coincide", "contradice", "sin_respaldo"]},
            "cite": {"type": "string"},
            "paper_id": {"type": "string"},
        },
        "required": ["text", "clase", "cite", "paper_id"],
    }
    missed = {
        "type": "object", "additionalProperties": False,
        "properties": {"text": {"type": "string"}, "cite": {"type": "string"}, "paper_id": {"type": "string"}},
        "required": ["text", "cite", "paper_id"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "afirmaciones": {"type": "array", "items": claim},
            "te_falto": {"type": "array", "items": missed},
        },
        "required": ["afirmaciones", "te_falto"],
    }


def _phrases(citations):
    lines = []
    for index, row in enumerate(citations or [], 1):
        if isinstance(row, dict) and row.get("text"):
            lines.append(f"{index}. paper {row.get('paper')}: {row.get('text')}")
    return "\n".join(lines)


def _fold_claims(data):
    """El esquema nuevo (una clase por afirmación) entra al mismo verificador."""
    if not isinstance(data, dict) or not isinstance(data.get("afirmaciones"), list):
        return data
    folded = {part: [] for part in PARTS}
    for item in data.get("afirmaciones") or []:
        if not isinstance(item, dict):
            continue
        clase = str(item.get("clase") or "")
        if clase not in ("coincide", "contradice", "sin_respaldo"):
            continue
        folded[clase].append(item)
    for item in data.get("te_falto") or []:
        if isinstance(item, dict):
            folded["te_falto"].append(item)
    return folded


def _body(user, name, schema, tokens, prompt):
    return {
        "model": MODEL, "store": False, "reasoning": {"effort": "minimal"}, "max_output_tokens": tokens,
        "input": [{"role": "developer", "content": prompt}, {"role": "user", "content": user}],
        "text": {"format": _schema(name, schema)},
    }


def _words(text):
    import re
    return [word.casefold() for word in re.findall(r"[^\W\d_]{4,}", text or "", flags=re.UNICODE)]


def _in_paper(cite, rows, paper_id):
    flat = _flat(cite)
    if len(flat) < 12:
        return None
    for row in rows:
        if str(row.get("paper")) != str(paper_id):
            continue
        blob = _flat((row.get("text") or "") + "".join(row.get("latex") or []))
        if flat in blob:
            return row
    return None


def _cite_supports(text, cite):
    words = _words(text)
    if not words:
        return False
    blob = set(_words(cite))
    hit = sum(1 for word in words if word in blob)
    return hit >= max(1, (len(words) + 1) // 2)


def layer1(data, citations):
    allowed = {str(row.get("paper")) for row in citations or [] if isinstance(row, dict)}
    out = {part: [] for part in PARTS}
    data = _fold_claims(data)
    if not isinstance(data, dict):
        return out
    for part in PARTS:
        for item in data.get(part) or []:
            if not isinstance(item, dict):
                continue
            text = cap_first(" ".join(str(item.get("text") or "").split()))
            if part == "te_falto":
                text = text.split("\n", 1)[0][:240]
            if not text:
                continue
            if part == "sin_respaldo":
                out[part].append({"text": text})
                continue
            paper_id = str(item.get("paper_id") or "")
            cite = " ".join(str(item.get("cite") or "").split())
            row = _in_paper(cite, citations, paper_id) if paper_id in allowed else None
            if row is None:
                continue
            if part == "te_falto" and not _cite_supports(text, cite):
                continue
            kept = {"text": text, "cite": cite, "paper_id": paper_id}
            section = " ".join(str(row.get("section") or "").split())
            if section:
                kept["section"] = section
            out[part].append(kept)
    return out


def _flatten(parts):
    return [(part, item) for part in PARTS for item in parts.get(part) or []]


def layer2(parts, keep):
    rows = _flatten(parts)
    if not isinstance(keep, list) or len(keep) != len(rows):
        return None
    out = {part: [] for part in PARTS}
    for (part, item), flag in zip(rows, keep):
        if flag is True:
            kept = dict(item)
            kept["verified"] = True
            out[part].append(kept)
    return out


def review(explanation, citations, complete=None):
    empty = {part: [] for part in PARTS}
    status = meta_status()
    if status == "apagado" or (status and complete is None):
        return empty, note_for(status), usage_cost(None)
    if not (explanation or "").strip() or not citations:
        return empty, "", usage_cost(None)
    call = complete or post_responses
    phrases = _phrases(citations)
    if _claims_on():
        said = "\n".join(f"{i}. {line}" for i, line in enumerate(_sentences(explanation), 1))
        user, prompt = _pack(said, phrases), _dev(_PROMPT_CLAIMS, quantity=True)
    else:  # RRM_CLAIMS=0: RRM-43, una sola afirmación
        user, prompt = _pack(explanation.strip(), phrases), _dev(_PROMPT, quantity=True)
    try:
        first = call(_body(user, "caja", _point_schema(), 1600, prompt))
    except Exception:
        return empty, note_for("red"), usage_cost(None)
    cost = usage_cost(first.get("usage") if isinstance(first, dict) else None)
    data = parse_json(response_text(first))
    if not known_caja(data):
        return empty, note_for("parse"), cost
    passed = refuse_injection(soften_quantities(layer1(data, citations), explanation), explanation)
    rows = _flatten(passed)
    if not rows:
        return passed, "", cost
    check = {
        "type": "object", "additionalProperties": False,
        "properties": {"keep": {"type": "array", "items": {"type": "boolean"}}},
        "required": ["keep"],
    }
    listed = "\n".join(
        f"{i}. {part} | {item.get('paper_id', '')} | {item.get('cite', '')} | {item.get('text')}"
        for i, (part, item) in enumerate(rows)
    )
    try:
        check_user = wrap_user("CHEQUEO", f"Frases:\n{phrases}\n\nPuntos:\n{listed}") if guard_on() else f"Frases:\n{phrases}\n\nPuntos:\n{listed}"
        second = call(_body(check_user, "chequeo", check, 800, _dev(_CHECK, quantity=True)))
    except Exception:
        return passed, "", cost
    cost = add_usage(cost, usage_cost(second.get("usage") if isinstance(second, dict) else None))
    verdict = parse_json(response_text(second))
    kept = layer2(passed, (verdict or {}).get("keep") if isinstance(verdict, dict) else None)
    if kept is None:
        return passed, "", cost
    return kept, "", cost
