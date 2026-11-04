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
# RRM-95: one short call per group, all in parallel, so the slowest group sets
# the wait (not the sum). The prompt is minimal: the verifier below does the rest.
_PROMPT = (
    "Name the GROUP of papers in 2 to 4 English words that a reader would recognise as its topic, "
    "and that tells it apart from the OTHER groups. "
    "Use only words already written in the group's titles. Answer only the JSON."
)
CALL_TIMEOUT = float(os.environ.get("RRM_GROUP_NAMES_TIMEOUT", "6"))
_CACHE = {}
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


def _user(groups, others=None):
    lines = []
    for group in groups:
        lines.append(f"Grupo {group.get('id')}:")
        titles = [str(item).strip() for item in (group.get("titles") or []) if str(item).strip()]
        if not titles:
            lines.append("(sin títulos)")
            continue
        for title in titles[:12]:
            lines.append(f"- {title[:180]}")
    if others:
        lines.append("OTHER groups (do not name these):")
        for title in others:
            lines.append(f"- {str(title)[:120]}")
    return wrap_user("TITULOS", "\n".join(lines))


def _body(user, max_tokens=600):
    from rrm.reader.metacall import MODEL

    return {
        "model": MODEL,
        "store": False,
        "reasoning": {"effort": "minimal"},
        "max_output_tokens": max_tokens,
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


def _key(group):
    import hashlib

    raw = "\n".join(sorted(str(t) for t in (group.get("titles") or [])[:12]))
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def name_groups(groups, complete=None):
    """One call per group, in parallel, each capped at CALL_TIMEOUT s.

    Returns (accepted names, cost). A group whose call fails, times out or does
    not pass the verifier keeps its c-TF-IDF name. Cached per group titles.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, wait

    from rrm.reader.metacall import add_usage, parse_json, post_responses, response_text, usage_cost

    rows = [group for group in groups or [] if isinstance(group, dict) and (group.get("titles") or [])]
    if not rows:
        return [], usage_cost(None)
    if complete is None and not enabled():
        return [], usage_cost(None)
    t0 = time.perf_counter()
    call = complete or (lambda body: post_responses(body, timeout=CALL_TIMEOUT))

    def one(group):
        key = _key(group)
        if key in _CACHE:
            return _CACHE[key], usage_cost(None), True
        others = [t for g in rows if g is not group for t in (g.get("titles") or [])[:3]]
        payload = call(_body(_user([group], others)))
        cost = usage_cost(payload.get("usage") if isinstance(payload, dict) else None)
        data = parse_json(response_text(payload))
        if isinstance(data, dict) and isinstance(data.get("names"), list):
            for item in data["names"]:
                if isinstance(item, dict):
                    item["id"] = str(group.get("id"))
        got = accept([group], data)
        if got:
            _CACHE[key] = got
        return got, cost, False

    names, total, cached, failed = [], usage_cost(None), 0, 0
    pool = ThreadPoolExecutor(max_workers=max(1, min(8, len(rows))))
    futures = [pool.submit(one, group) for group in rows]
    done, _late = wait(futures, timeout=CALL_TIMEOUT + 1.5)
    pool.shutdown(wait=False, cancel_futures=True)
    used = set()
    for future in futures:
        if future not in done:
            failed += 1
            continue
        try:
            got, cost, hit = future.result()
        except Exception:
            failed += 1
            continue
        total = add_usage(total, cost)
        cached += int(hit)
        for row in got:
            folded = _fold(row["name"])
            if folded in used:
                continue
            used.add(folded)
            names.append(row)
    total = dict(total)
    total.update({"seconds": round(time.perf_counter() - t0, 3), "calls": len(rows) - cached, "cached": cached, "failed": failed})
    return names, total
