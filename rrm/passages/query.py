"""Consulta de pasajes.

Si el hueco trae símbolo, se quedan las filas cuyo LaTeX o cuyo texto lo
contienen tal como viene escrito, ya sin espacios de más. Entre esas filas
se ordena por el coseno. Sin símbolo, el coseno corre sobre todas las filas
(`eq`, `p` y `def`). No hay umbral: cada fila trae su coseno.

El modelo, si entra, solo reordena el top 10 ya recuperado. El texto que
sale es el de la fila guardada. Si el filtro de símbolo no deja filas, la
salida es vacía.
"""

import re

TOP = 10


def squash(text):
    return re.sub(r"\s+", "", text or "")


def contains_symbol(row, symbol):
    needle = squash(symbol)
    if not needle:
        return False
    hay = squash((row.get("latex") or "") + (row.get("text") or ""))
    return needle in hay


def gap_text(gap):
    gap = gap or {}
    local = str(gap.get("local") or "").strip()
    extra = str(gap.get("symbol") or gap.get("claim") or "").strip()
    parts = [part for part in (local, extra) if part]
    return "\n".join(parts)


def _public(row, cosine):
    return {
        "id": row.get("id"),
        "corpusid": row.get("corpusid"),
        "arxiv_id": row.get("arxiv_id") or "",
        "kind": row.get("kind"),
        "section": row.get("section") or "",
        "text": row.get("text") or "",
        "latex": row.get("latex") or "",
        "license": row.get("license") or "",
        "url": row.get("url") or "",
        "cosine": None if cosine is None else float(cosine),
    }


def _rerank_top(rows, rerank):
    """Reordena solo las primeras 10. Un texto nuevo del modelo se descarta."""
    top = rows[:TOP]
    rest = rows[TOP:]
    if rerank is None or not top:
        return rows
    proposed = rerank([dict(row) for row in top]) or []
    by_id = {row["id"]: row for row in top}
    ordered = []
    seen = set()
    for item in proposed:
        rid = item.get("id") if isinstance(item, dict) else item
        if rid in by_id and rid not in seen:
            ordered.append(by_id[rid])
            seen.add(rid)
    for row in top:
        if row["id"] not in seen:
            ordered.append(row)
    return ordered + rest


def query_rows(rows, vectors, gap, *, k=TOP, rerank=None):
    """Filas guardadas, ordenadas. `vectors` alineado con `rows`, ya normalizado.

    Sin vectores y con símbolo: las filas que lo contienen, coseno vacío.
    Sin vectores y sin símbolo: vacío, porque no hay con qué ordenar.
    """
    import numpy as np

    gap = gap or {}
    symbol = str(gap.get("symbol") or "").strip()
    rows = [row for row in rows or [] if isinstance(row, dict)]
    if symbol:
        chosen = [(i, row) for i, row in enumerate(rows) if contains_symbol(row, symbol)]
        if not chosen:
            return []
    else:
        if vectors is None:
            return []
        chosen = list(enumerate(rows))
    if not chosen:
        return []

    scored = []
    q = gap.get("vector")
    mat = None if vectors is None else np.asarray(vectors, dtype=np.float32)
    if q is not None and mat is not None:
        q = np.asarray(q, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(q))
        if norm > 0:
            q = q / norm
    else:
        q = None
    for index, row in chosen:
        cosine = None
        if q is not None:
            vec = mat[index]
            if vec.shape == q.shape:
                cosine = float(np.dot(vec, q))
        scored.append((cosine, str(row.get("id") or ""), row))
    scored.sort(key=lambda item: (-(item[0] if item[0] is not None else -2.0), item[1]))
    width = max(int(k), TOP)
    public = [_public(row, cosine) for cosine, _rid, row in scored[:width]]
    public = _rerank_top(public, rerank)
    return public[: max(0, int(k))]
