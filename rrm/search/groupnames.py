"""Nombres de grupo con una llamada. Apagado salvo RRM_GROUP_NAMES=1.

La UI pinta el nombre c-TF-IDF y solo lo cambia si cada palabra de contenido
del nombre nuevo está en los títulos o abstracts de ese grupo.
"""

import os
import re
import unicodedata

from rrm.reader.promptguard import with_guard, wrap_user

_ON = {"1", "true", "yes", "on"}
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "using",
    "via", "are", "was", "were", "been", "being", "have", "has", "had", "not",
    "but", "its", "their", "our", "you", "your", "how", "what", "why", "when",
    "del", "los", "las", "una", "uno", "para", "con", "por", "que", "como",
    "más", "mas", "entre", "sobre", "hacia", "desde",
}
_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
_PROMPT = (
    "Ponle a cada grupo un nombre distinto de 2 a 5 palabras. "
    "Cada palabra tiene que estar ya escrita en los títulos de ese grupo. "
    "No inventes un tema y no repitas un nombre entre grupos. "
    "Responde solo el JSON."
)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["id", "name"],
            },
        }
    },
    "required": ["names"],
}


def enabled() -> bool:
    return os.environ.get("RRM_GROUP_NAMES", "").strip().lower() in _ON


def _fold(text):
    raw = unicodedata.normalize("NFKD", str(text or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return raw.casefold()


def _tokens(text):
    return _WORD.findall(_fold(text))


def content_words(text):
    return [word for word in _tokens(text) if word not in _STOP and len(word) >= 3]


def name_ok(name, blob) -> bool:
    """2 a 5 palabras, y cada palabra de contenido está en el grupo."""
    parts = [part for part in str(name or "").split() if part]
    if not 2 <= len(parts) <= 5:
        return False
    words = content_words(name)
    if not words:
        return False
    hay = set(content_words(blob))
    flat = _fold(blob)
    return all(word in hay or word in flat for word in words)


def _blob(group):
    titles = group.get("titles") or []
    abstracts = group.get("abstracts") or []
    return "\n".join(str(item) for item in list(titles) + list(abstracts) if item)


def _user(groups):
    lines = []
    for group in groups:
        lines.append(f"Grupo {group.get('id')}:")
        titles = [str(item).strip() for item in (group.get("titles") or []) if str(item).strip()]
        if not titles:
            lines.append("(sin títulos)")
            continue
        for title in titles[:12]:
            lines.append(f"- {title[:180]}")
    return wrap_user("TITULOS", "\n".join(lines))


def _body(user):
    from rrm.reader.metacall import MODEL

    return {
        "model": MODEL,
        "store": False,
        "reasoning": {"effort": "minimal"},
        "max_output_tokens": 800,
        "input": [
            {"role": "developer", "content": with_guard(_PROMPT)},
            {"role": "user", "content": user},
        ],
        "text": {"format": {"type": "json_schema", "name": "grupos", "strict": True, "schema": _SCHEMA}},
    }


def accept(groups, data):
    """Nombres que pasan el verificador. El resto se queda en c-TF-IDF."""
    by_id = {}
    for group in groups or []:
        if isinstance(group, dict) and group.get("id") is not None:
            by_id[str(group.get("id"))] = group
    if not isinstance(data, dict):
        return []
    used = set()
    out = []
    for item in data.get("names") or []:
        if not isinstance(item, dict):
            continue
        gid = str(item.get("id") if item.get("id") is not None else "")
        name = " ".join(str(item.get("name") or "").split())
        group = by_id.get(gid)
        if group is None or not name_ok(name, _blob(group)):
            continue
        key = _fold(name)
        if key in used:
            continue
        used.add(key)
        from rrm.textcase import cap_first

        out.append({"id": gid, "name": cap_first(name)})
    return out


def name_groups(groups, complete=None):
    """Una llamada. Devuelve (nombres aceptados, costo). Sin flag y sin mock: vacío."""
    from rrm.reader.metacall import parse_json, post_responses, response_text, usage_cost

    rows = [group for group in groups or [] if isinstance(group, dict) and (group.get("titles") or [])]
    if not rows:
        return [], usage_cost(None)
    if complete is None and not enabled():
        return [], usage_cost(None)
    call = complete or post_responses
    try:
        payload = call(_body(_user(rows)))
    except Exception:
        return [], usage_cost(None)
    cost = usage_cost(payload.get("usage") if isinstance(payload, dict) else None)
    return accept(rows, parse_json(response_text(payload))), cost
