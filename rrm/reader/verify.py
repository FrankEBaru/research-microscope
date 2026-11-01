"""Verificador de citas. La capa 1 es este archivo; la capa 2 vive en feedback.py."""

import os
import re

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
    """La caja ya no usa una sola línea. Se queda vacío para no llamar a Meta por otro camino."""
    del citas
    return ""


def ask_error_text(err):
    """Texto para la UI. Sin clave, sin URL y sin el cuerpo crudo de la red."""
    raw = str(err or "").strip() or "La revisión falló."
    secret = os.environ.get("MODEL_API_KEY") or ""
    if secret and secret in raw:
        raw = raw.replace(secret, "")
    raw = re.sub(r"Bearer\s+\S+", "Bearer", raw)
    raw = re.sub(r"https?://\S+", "", raw)
    raw = " ".join(raw.split())
    return (raw[:180] or "La revisión falló.")


def ask_http(body, stage):
    """Un fallo de la revisión no sale como 200 vacío."""
    from rrm.reader.metacall import note_for

    note = str((body or {}).get("note") or "")
    parts = (body or {}).get("parts") or {}
    filled = any(parts.get(name) for name in ("coincide", "contradice", "sin_respaldo", "te_falto"))
    if (stage or "") == "revisar" and note in {note_for("red"), note_for("parse")} and not filled:
        return 502, {"error": note}
    return 200, body


def answer(rows, text, *, ids=None, root=None, encode=None, stage="todo", vectors=None):
    from rrm.reader.feedback import PARTS, review
    from rrm.reader.phrases import store_progress
    from rrm.reader.similar import rank_similar

    hits, matched = rank_similar(rows, text, encode, vectors=vectors) if (text or "").strip() else ([], 0)
    skip = stage == "frases"
    parts, note, meta = review(text, hits) if hits and not skip else ({part: [] for part in PARTS}, "", None)
    if not hits and (text or "").strip():
        had = any(isinstance(row, dict) and (row.get("text") or "").strip() for row in rows or [])
        note = "No pude comparar la explicación con las frases." if had else "No hay frases guardadas de estos papers."
    seen = []
    for row in hits:
        key = row.get("paper")
        if key not in seen:
            seen.append(key)
    return {
        "extracts": hits,
        "papers": len(seen),
        "line": "",
        "empty": not hits,
        "matched": matched,
        "parts": parts,
        "note": note,
        "meta": meta,
        "store": store_progress(root, ids if ids is not None else []),
    }
