"""Lectura local de passages/ (rows.parquet + faiss.index). Sin Modal y sin red.

La escribe la etapa e3 de la app rrm-passages, en el volumen rrm-data, bajo
/data/passages. RRM_PASSAGES_DIR apunta a una copia local (las pruebas).
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


def search_embedding(vector, k=3, root=None):
    """Top-k por coseno contra el índice FAISS. Sin vector no hay filas."""
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
    width = min(max(int(k), 0), int(index.ntotal))
    if width == 0:
        return []
    dists, ids = index.search(np.ascontiguousarray(q), width)
    found = []
    for score, idx in zip(dists[0], ids[0]):
        pos = int(idx)
        if pos < 0 or pos >= len(rows):
            continue
        row = dict(rows[pos])
        row["cosine"] = float(score)
        found.append(row)
    return found
