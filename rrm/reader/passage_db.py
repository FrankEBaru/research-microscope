"""Lectura local de passages/ (rows.parquet + faiss.index). Sin Modal y sin red.

La escribe la etapa e3 de la app rrm-passages, en el volumen rrm-data, bajo
/data/passages. RRM_PASSAGES_DIR apunta a una copia local (las pruebas).

Con el filtro prendido (default; `RRM_PASSAGES_FILTER_JUNK=0` lo apaga) el
top-k no devuelve filas de portada. Si al lado del parquet está
`junk_mask.npy` (un bool por fila, el mismo orden), se usa esa máscara.
Si no está, o el largo no coincide, se clasifica el texto de los candidatos.
"""

import threading
from pathlib import Path

import os

_COLUMNS = (
    "id", "corpusid", "arxiv_id", "kind", "section", "text", "latex", "license", "url",
)
_CACHE = {}
_LOCK = threading.Lock()


def passages_dir():
    env = os.environ.get("RRM_PASSAGES_DIR", "").strip()
    if env:
        return Path(env)
    data = os.environ.get("RRM_DATA", "/data").strip() or "/data"
    return Path(data) / "passages"


def _load_rows(root):
    parquet = Path(root) / "rows.parquet"
    if not parquet.is_file():
        raise FileNotFoundError(parquet)
    st = parquet.stat()
    key = (str(parquet.resolve()), st.st_mtime_ns, st.st_size)
    with _LOCK:
        hit = _CACHE.get("rows", {}).get(key)
    if hit is not None:
        return hit
    import pyarrow.parquet as pq

    names = set(pq.read_schema(parquet).names)
    cols = [name for name in _COLUMNS if name in names]
    rows = pq.read_table(parquet, columns=cols or None).to_pylist()
    with _LOCK:
        _CACHE.setdefault("rows", {})[key] = rows
    return rows


def _load_index(root, n_rows):
    """IndexFlatIP de e3. None si falta o si no coincide con las filas."""
    path = Path(root) / "faiss.index"
    if not path.is_file():
        return None
    st = path.stat()
    key = (str(path.resolve()), st.st_mtime_ns, st.st_size, int(n_rows))
    with _LOCK:
        hit = _CACHE.get("index", {}).get(key)
    if hit is not None:
        return hit
    import faiss

    index = faiss.read_index(str(path))
    if int(index.ntotal) != int(n_rows) or int(index.ntotal) == 0:
        return None
    with _LOCK:
        _CACHE.setdefault("index", {})[key] = index
    return index


def _load_mask(root, n_rows):
    """junk_mask.npy alineada con las filas. None si falta o no coincide."""
    path = Path(root) / "junk_mask.npy"
    if not path.is_file():
        return None
    st = path.stat()
    key = (str(path.resolve()), st.st_mtime_ns, st.st_size, int(n_rows))
    with _LOCK:
        hit = _CACHE.get("mask", {}).get(key)
    if hit is not None:
        return hit
    import numpy as np

    try:
        arr = np.load(path)
    except (OSError, ValueError):
        return None
    arr = np.asarray(arr)
    if arr.ndim != 1 or int(arr.shape[0]) != int(n_rows):
        return None
    with _LOCK:
        _CACHE.setdefault("mask", {})[key] = arr
    return arr


def _widths(want, ntotal):
    """k no alcanza si las primeras filas son portada. Se ensancha pocas veces."""
    width = min(int(ntotal), max(int(want) * 8, int(want) + 32))
    out = [width]
    while width < int(ntotal) and len(out) < 4:
        width = min(int(ntotal), max(width * 8, width + int(want)))
        out.append(width)
    return out


def _row_junk(pos, row, mask):
    if mask is not None:
        return bool(mask[pos])
    from rrm.reader.passage_junk import is_junk_passage

    return is_junk_passage(row.get("text"), row.get("latex"), row.get("kind"))


def search_embedding(vector, k=3, root=None, filter_junk=None):
    """Top-k por coseno contra el índice FAISS. Sin vector no hay filas.

    `filter_junk` None sigue la bandera. Para llenar k se piden más vecinos
    y se saltan las filas de portada. El índice y el parquet no se modifican.
    """
    import numpy as np

    if vector is None:
        return []
    root = Path(root) if root is not None else passages_dir()
    rows = [row for row in _load_rows(root) if isinstance(row, dict)]
    index = _load_index(root, len(rows))
    if index is None:
        return []
    q = np.ascontiguousarray(np.asarray(vector, dtype=np.float32).reshape(1, -1))
    if q.shape[1] != int(index.d):
        return []
    import faiss

    faiss.normalize_L2(q)
    want = max(int(k), 0)
    ntotal = int(index.ntotal)
    if want == 0 or ntotal == 0:
        return []
    if filter_junk is None:
        from rrm.reader.passage_junk import junk_filter_enabled

        filter_junk = junk_filter_enabled()
    mask = _load_mask(root, len(rows)) if filter_junk else None
    found = []
    seen = set()
    widths = _widths(want, ntotal) if filter_junk else [min(want, ntotal)]
    for width in widths:
        if len(found) >= want:
            break
        dists, ids = index.search(np.ascontiguousarray(q), int(width))
        for score, idx in zip(dists[0], ids[0]):
            pos = int(idx)
            if pos < 0 or pos >= len(rows) or pos in seen:
                continue
            seen.add(pos)
            row = rows[pos]
            if filter_junk and _row_junk(pos, row, mask):
                continue
            item = dict(row)
            item["cosine"] = float(score)
            found.append(item)
            if len(found) >= want:
                break
    return found
