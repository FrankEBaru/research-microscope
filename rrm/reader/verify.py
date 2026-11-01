"""Verificador de la línea final. Algoritmo, no una segunda llamada al modelo."""

import re

from rrm.reader.phrases import search_phrases

_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def _flat(text):
    return re.sub(r"\s+", "", text or "").casefold()


def _words(text):
    return [word.casefold() for word in _WORD.findall(text or "")]


def _contained(piece, texts):
    flat = _flat(piece)
    return bool(flat) and any(flat in _flat(text) for text in texts)


def verify_line(line, citations):
    """Ignora espacios y saltos. Tira la frase atribuida que no está en ese paper.

    Sin atribución, la oración se queda solo si cada palabra ya está en las citas.
    """
    if not (line or "").strip():
        return ""
    by_paper = {}
    all_text = []
    for row in citations or []:
        if not isinstance(row, dict):
            continue
        text = row.get("text") or ""
        all_text.append(text)
        by_paper.setdefault(str(row.get("paper")), []).append(text)
    vocab = {word for text in all_text for word in _words(text)}
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", line.strip()):
        sent = sent.strip()
        if not sent:
            continue
        quotes = [a or b for a, b in re.findall(r"«([^»]+)»|\"([^\"]+)\"", sent)]
        papers = [pid for pid in by_paper if pid and pid != "None" and pid in sent]
        targets = []
        for pid in papers:
            targets.extend(by_paper[pid])
        if not targets:
            targets = all_text
        if quotes:
            ok = all(_contained(quote, targets) for quote in quotes)
        elif papers:
            ok = _contained(sent, targets)
        else:
            ok = all(word in vocab for word in _words(sent))
        if ok:
            kept.append(sent)
    return " ".join(kept)


def linea_final(citas):
    """Core devuelve vacío, sin red. Meta se colgaría aquí cuando se elija el modelo."""
    del citas
    from rrm.features import core_mode

    if core_mode():
        return ""
    return ""


def answer(rows, text):
    hits = search_phrases(rows, text)
    draft = linea_final(hits)
    line = verify_line(draft, hits) if draft else ""
    seen = []
    for row in hits:
        key = row.get("paper")
        if key not in seen:
            seen.append(key)
    return {"extracts": hits, "papers": len(seen), "line": line, "empty": not hits}
