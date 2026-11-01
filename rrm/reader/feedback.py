"""Cuatro partes de la caja. Solo frases ya elegidas. Capa 1 aquí; capa 2 es otra llamada."""

from rrm.reader.metacall import add_usage, meta_status, note_for, parse_json, post_responses, response_text, usage_cost
from rrm.reader.metacall import MODEL

PARTS = ("coincide", "contradice", "sin_respaldo", "te_falto")
_QUOTED = ("coincide", "contradice", "te_falto")
_PROMPT = (
    "Separas la explicación del lector en cuatro listas y solo puedes usar las frases numeradas. "
    "No des un veredicto de bien o mal. "
    "coincide: lo que esas frases dicen, con cita textual y paper_id. "
    "contradice: lo que choca con una frase, con esa cita y paper_id. "
    "sin_respaldo: lo que ninguna frase menciona; cita y paper_id van vacíos. "
    "te_falto: lo que las frases dicen y el lector no tocó, una línea, con cita y paper_id. "
    "La cita es un trozo literal de una sola frase. paper_id es el de esa frase."
)
_CHECK = (
    "Para cada punto responde si la cita respalda el texto (coincide y te_falto), "
    "si lo contradice (contradice), o si ninguna frase lo respalda (sin_respaldo). "
    'JSON {"keep":[true,false]} en el mismo orden. Un punto dudoso es false.'
)


def _flat(text):
    import re
    return re.sub(r"\s+", "", text or "").casefold()


def _schema(name, schema):
    return {"type": "json_schema", "name": name, "strict": True, "schema": schema}


def _point_schema():
    point = {
        "type": "object", "additionalProperties": False,
        "properties": {"text": {"type": "string"}, "cite": {"type": "string"}, "paper_id": {"type": "string"}},
        "required": ["text", "cite", "paper_id"],
    }
    bare = {"type": "object", "additionalProperties": False, "properties": {"text": {"type": "string"}}, "required": ["text"]}
    props = {part: {"type": "array", "items": point if part in _QUOTED else bare} for part in PARTS}
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(PARTS)}


def _phrases(citations):
    return "\n".join(f"{row.get('paper')}: {row.get('text')}" for row in citations or [] if isinstance(row, dict) and row.get("text"))


def _body(user, name, schema, tokens, prompt):
    return {
        "model": MODEL, "store": False, "reasoning": {"effort": "low"}, "max_output_tokens": tokens,
        "input": [{"role": "developer", "content": prompt}, {"role": "user", "content": user}],
        "text": {"format": _schema(name, schema)},
    }


def _in_paper(cite, rows, paper_id):
    flat = _flat(cite)
    if len(flat) < 12:
        return False
    for row in rows:
        if str(row.get("paper")) != str(paper_id):
            continue
        blob = _flat((row.get("text") or "") + "".join(row.get("latex") or []))
        if flat in blob:
            return True
    return False


def layer1(data, citations):
    allowed = {str(row.get("paper")) for row in citations or [] if isinstance(row, dict)}
    out = {part: [] for part in PARTS}
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
            if paper_id not in allowed or not _in_paper(cite, citations, paper_id):
                continue
            out[part].append({"text": text, "cite": cite, "paper_id": paper_id})
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
        first = call(_body(user, "caja", _point_schema(), 2500, _PROMPT))
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
        second = call(_body(f"Frases:\n{_phrases(citations)}\n\nPuntos:\n{listed}", "chequeo", check, 2000, _CHECK))
    except Exception:
        return empty, note_for("red"), cost
    cost = add_usage(cost, usage_cost(second.get("usage") if isinstance(second, dict) else None))
    verdict = parse_json(response_text(second))
    kept = layer2(passed, (verdict or {}).get("keep") if isinstance(verdict, dict) else None)
    if kept is None:
        return empty, note_for("parse"), cost
    return kept, "", cost
