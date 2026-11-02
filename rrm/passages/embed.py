"""Texto que se embebe y vectores normalizados.

El vector es el de SPECTER2 con el adapter de proximidad, el mismo que
embebe papers. El texto que se muestra sigue siendo la fila: el vector
solo ordena.
"""

import numpy as np

from rrm.search.encode import PROXIMITY, use_proximity


def passage_text(row):
    """Oraciones en texto plano más el LaTeX. El salto de línea pide proximidad."""
    text = (row.get("text") or "").strip()
    latex = (row.get("latex") or "").strip()
    if text and latex:
        body = text + "\n" + latex
    else:
        body = text or latex
    if "\n" not in body:
        body = (body or "") + "\n"
    return body


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
    texts = [passage_text(row) for row in rows or []]
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
