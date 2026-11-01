"""Cita BibTeX → s2:<corpusid> por título y año de las refs del grafo."""

import re

_YEAR = re.compile(r"(?:19|20)\d{2}")
_WORD = re.compile(r"[a-z0-9]{4,}")


def _norm(text):
    return " ".join(_WORD.findall((text or "").lower()))


def bind_cites(bib, graph):
    """Clave de la bibliografía → s2:id cuando el título y el año coinciden. Si no, no entra."""
    out = {}
    graph = graph or {}
    for key, text in (bib or {}).items():
        raw = str(key)
        if re.fullmatch(r"s2:\d+", raw):
            out[raw] = raw
            continue
        bib_text = f"{raw} {text or ''}"
        year = _YEAR.search(bib_text)
        year = year.group(0) if year else ""
        bib_words = set(_norm(text or "").split())
        best, best_score = None, 0.0
        for gid, gtext in graph.items():
            if not re.fullmatch(r"s2:\d+", str(gid)):
                continue
            gyear = _YEAR.search(str(gtext or ""))
            if year and gyear and year != gyear.group(0):
                continue
            title_words = [word for word in _norm(gtext or "").split() if word != (gyear.group(0) if gyear else "")]
            if len(title_words) < 2:
                continue
            hit = sum(1 for word in title_words if word in bib_words)
            score = hit / len(title_words)
            if year and gyear and year == gyear.group(0):
                score += 0.2
            if score > best_score:
                best, best_score = str(gid), score
        if best is not None and best_score >= 0.6:
            out[raw] = best
    return out
