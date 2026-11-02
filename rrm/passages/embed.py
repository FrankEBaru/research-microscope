"""Texto que se embebe y vectores normalizados.

El vector es el de SPECTER2 con el adapter de proximidad, el mismo que
embebe papers. El texto que se muestra sigue siendo la fila: el vector
solo ordena.
"""

import numpy as np

from rrm.search.encode import PROXIMITY, use_proximity


# Presupuesto del texto embebido. SPECTER2 corta en 512 tokens (con [CLS] y
# [SEP]). Medido con el tokenizer de allenai/specter2_base [V]: prosa con $..$
# ~0.25-0.35 tokens por carácter, LaTeX en bloque ~0.55-0.75. Se estima con
# cotas altas (PROSE_RATE, LATEX_RATE) para que encabezado + párrafo previo +
# ecuación quepan siempre antes del corte. Lo que va después de la ecuación
# (párrafo siguiente y citas) puede quedar cortado por el tokenizer: es a propósito.
WINDOW_TOKENS = 500
PROSE_RATE = 0.5
LATEX_RATE = 0.8
HEADER_CHARS = 160
LATEX_TOKENS = 300
BEFORE_WORDS = 80
AFTER_WORDS = 60
REF_WORDS = 30
SEP = " \u203a "


def _tokens(text, rate):
    return int(len(text or "") * rate) + 1


def _last_words(text, words, chars=None):
    parts = (text or "").split()
    out = " ".join(parts[-int(words):]) if words > 0 else ""
    if chars is not None and len(out) > chars:
        out = out[len(out) - int(chars):]
        cut = out.find(" ")
        out = out[cut + 1:] if 0 <= cut < len(out) - 1 else out
    return out


def _first_words(text, words):
    parts = (text or "").split()
    return " ".join(parts[: int(words)]) if words > 0 else ""


def header_text(row):
    """Título del paper y, si no es genérica, la sección. Sin título queda la sección."""
    title = (row.get("title") or "").strip()
    head = (row.get("head") or "").strip()
    parts = [part for part in (title, head) if part]
    return SEP.join(parts)[:HEADER_CHARS]


def _text_of(by_id, rid):
    if not rid or not by_id:
        return ""
    found = by_id.get(rid)
    return (found.get("text") or "").strip() if found else ""


def passage_text(row, by_id=None):
    """Texto embebido. `text` de la fila no cambia; esto solo ordena el vector.

    eq: encabezado, final del párrafo previo, LaTeX, inicio del siguiente y
    fragmentos de los párrafos que citan la ecuación. p y def: encabezado y
    luego el texto (más el LaTeX en def). El salto de línea pide proximidad.
    """
    header = header_text(row)
    text = (row.get("text") or "").strip()
    latex = (row.get("latex") or "").strip()
    if row.get("kind") == "eq":
        latex = latex[: int(LATEX_TOKENS / LATEX_RATE)]
        before = _text_of(by_id, row.get("ctx_before"))
        after = _text_of(by_id, row.get("ctx_after"))
        if not before and not after:
            before = text
        left = WINDOW_TOKENS - _tokens(header, PROSE_RATE) - _tokens(latex, LATEX_RATE) - 4
        before = _last_words(before, BEFORE_WORDS, chars=max(0, int(left / PROSE_RATE)))
        refs = [_first_words(_text_of(by_id, rid), REF_WORDS) for rid in row.get("ctx_refs") or []]
        parts = [header, before, latex, _first_words(after, AFTER_WORDS)] + refs
    else:
        parts = [header, text, latex]
    body = "\n".join(part for part in parts if part)
    if "\n" not in body:
        body = (body or "") + "\n"
    return body


def embed_policy():
    return {
        "order_eq": "title > head, before (last words), latex, after (first words), ctx_refs",
        "order_p_def": "title > head, text, latex",
        "window_tokens": WINDOW_TOKENS,
        "prose_rate": PROSE_RATE,
        "latex_rate": LATEX_RATE,
        "latex_tokens": LATEX_TOKENS,
        "before_words": BEFORE_WORDS,
        "after_words": AFTER_WORDS,
        "ref_words": REF_WORDS,
        "header_chars": HEADER_CHARS,
    }


def uses_proximity(row) -> bool:
    return use_proximity(passage_text(row))


def l2_normalize(vectors):
    arr = np.ascontiguousarray(vectors, dtype=np.float32)
    if arr.size == 0:
        return arr.reshape(0, arr.shape[1] if arr.ndim == 2 else 0)
    if arr.ndim != 2:
        raise ValueError("vectors must be a matrix")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return arr / norms


def embed_rows(rows, encode, batch=32):
    """`encode` recibe textos y devuelve float32 (n, dim). En Modal es proximidad."""
    rows = list(rows or [])
    by_id = {row.get("id"): row for row in rows if row.get("kind") == "p"}
    texts = [passage_text(row, by_id) for row in rows]
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    batch = max(1, int(batch))
    parts = []
    for start in range(0, len(texts), batch):
        part = np.asarray(encode(texts[start : start + batch]), dtype=np.float32)
        parts.append(part)
    return np.vstack(parts)


def proximity_name():
    return PROXIMITY
