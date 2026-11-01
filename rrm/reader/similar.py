"""Top-k de frases por coseno. No exige las mismas palabras ni el mismo idioma.

El encoder de la consulta ya está en el repo: SPECTER2 (`rrm.search.encode`).
Si ese paquete no está, se usa una bolsa local con el glosario de panorama.
"""

import hashlib
import os
import unicodedata

import numpy as np

from rrm.reader.phrases import _chunk_in, query_tokens, rank_phrases
from rrm.search.labels import cosine

_DIM = 48
_CAP = 12
_PER_PAPER = 3
_encoder = None


def _fold(text):
    raw = unicodedata.normalize("NFD", text or "").casefold()
    return "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")


def _gloss():
    from rrm.panorama import _GLOSS

    return _GLOSS


def local_encode(texts):
    gloss = _gloss()
    out = np.zeros((len(list(texts)), _DIM), dtype=np.float32)
    for index, text in enumerate(texts):
        for word in query_tokens(_fold(text))[0]:
            token = gloss.get(word, word)
            digest = hashlib.sha256(token.encode()).digest()
            bucket = int.from_bytes(digest[:2], "little") % _DIM
            sign = 1.0 if digest[2] & 1 else -1.0
            out[index, bucket] += sign
    return out


def specter_encode(texts):
    global _encoder
    if _encoder is None:
        from rrm.search.encode import QueryEncoder

        _encoder = QueryEncoder()
    return np.asarray(_encoder.encode(list(texts)), dtype=np.float32)


def encode_texts(texts):
    """SPECTER2 si carga. Si no, la bolsa local. `RRM_PHRASE_ENCODER=local` lo fuerza."""
    choice = os.environ.get("RRM_PHRASE_ENCODER", "auto").strip().lower()
    if choice == "local":
        return local_encode(texts)
    try:
        return specter_encode(texts)
    except Exception:
        return local_encode(texts)


def _phrase_text(row):
    latex = " ".join(row.get("latex") or [])
    return ((row.get("text") or "") + " " + latex).strip()


def rank_similar(rows, text, encode=None):
    """Las frases más cercanas a la explicación. Tope 3 por paper y 12."""
    words, chunks = query_tokens(text or "")
    usable = [row for row in rows or [] if isinstance(row, dict) and (row.get("text") or "").strip()]
    if not (text or "").strip() or not usable:
        return [], 0
    if chunks and not words:
        return rank_phrases(usable, text)
    encode = encode or local_encode
    try:
        vecs = np.asarray(encode([text] + [_phrase_text(row) for row in usable]), dtype=np.float32)
    except Exception:
        return [], 0
    if vecs.ndim != 2 or vecs.shape[0] != len(usable) + 1:
        return [], 0
    scored = []
    for row, vec in zip(usable, vecs[1:]):
        score = cosine(vecs[0], vec)
        if score is None:
            continue
        bonus = 1 if chunks and any(_chunk_in(chunk, row) for chunk in chunks) else 0
        scored.append((bonus, score, row))
    if scored:
        best = max(item[1] for item in scored)
        # Una frase lejos de la mejor no entra: si no, «te faltó» cita cualquier cosa.
        scored = [item for item in scored if item[0] or item[1] >= best - 0.05]
    scored.sort(key=lambda item: (-item[0], -item[1]))
    picked, per = [], {}
    for _bonus, _score, row in scored:
        pid = row.get("paper")
        if per.get(pid, 0) >= _PER_PAPER:
            continue
        per[pid] = per.get(pid, 0) + 1
        picked.append(row)
        if len(picked) >= _CAP:
            break
    return picked, len(scored)
