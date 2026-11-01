"""Cuatro partes de la caja. Solo frases ya elegidas. Capa 1 aquí; capa 2 es otra llamada."""

from rrm.reader.metacall import add_usage, meta_status, note_for, parse_json, post_responses, response_text, usage_cost
from rrm.reader.metacall import MODEL

PARTS = ("coincide", "contradice", "sin_respaldo", "te_falto")
_QUOTED = ("coincide", "contradice", "te_falto")
_PROMPT = (
    "Partes la explicación del lector en afirmaciones, una por oración. "
    "Cada afirmación se clasifica contra una frase numerada, con una sola clase: "
    "coincide si esa frase dice lo mismo, contradice si dice lo contrario, "
    "sin_respaldo si ninguna frase habla de eso. "
    "En coincide y contradice, cite es un trozo copiado tal cual de esa frase "
    "(al menos unas doce letras) y paper_id es el de la frase. "
    "En sin_respaldo, cite y paper_id van vacíos. "
    "te_falto va aparte: una cosa que las frases dicen y el lector no mencionó. "
    "Su texto habla de lo que dice la cita, y la cita es un trozo literal de esa frase. "
    "No des un veredicto de bien o mal."
)
_CHECK = (
    "Para cada punto, en orden: true si la cita respalda (coincide, te_falto), "
    "si contradice (contradice), o si ninguna frase lo respalda (sin_respaldo). "
    "Un punto dudoso es false. Responde solo el arreglo keep."
)


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
            text = " ".join(str(item.get("text") or "").split())
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
    user = f"Explicación:\n{explanation.strip()}\n\nFrases:\n{_phrases(citations)}"
    try:
        first = call(_body(user, "caja", _point_schema(), 1200, _PROMPT))
    except Exception:
        return empty, note_for("red"), usage_cost(None)
    cost = usage_cost(first.get("usage") if isinstance(first, dict) else None)
    data = parse_json(response_text(first))
    if data is None:
        return empty, note_for("parse"), cost
    passed = layer1(data, citations)
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
        second = call(_body(f"Frases:\n{_phrases(citations)}\n\nPuntos:\n{listed}", "chequeo", check, 800, _CHECK))
    except Exception:
        return passed, "", cost
    cost = add_usage(cost, usage_cost(second.get("usage") if isinstance(second, dict) else None))
    verdict = parse_json(response_text(second))
    kept = layer2(passed, (verdict or {}).get("keep") if isinstance(verdict, dict) else None)
    if kept is None:
        return passed, "", cost
    return kept, "", cost
