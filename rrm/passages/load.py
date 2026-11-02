"""Carga del índice en el contenedor de búsqueda. No-op si el flag está apagado."""

import json
from pathlib import Path

import numpy as np

from rrm.passages import passages_enabled
from rrm.passages.query import gap_text, query_rows
from rrm.passages.store import read_faiss_vectors, read_rows


class PassageIndex:
    def __init__(self, rows, vectors, manifest):
        self.rows = list(rows or [])
        self.vectors = vectors
        self.manifest = manifest or {}

    def query(self, gap, vector=None, rerank=None, k=10):
        gap = dict(gap or {})
        if vector is not None:
            gap["vector"] = vector
        return query_rows(self.rows, self.vectors, gap, k=k, rerank=rerank)


def load_passages(path) -> PassageIndex:
    path = Path(path)
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = read_rows(path / "rows.parquet")
    _index, vectors = read_faiss_vectors(path / "faiss.index")
    if len(rows) != int(vectors.shape[0]):
        raise RuntimeError("rows.parquet and faiss index differ in length")
    return PassageIndex(rows, vectors, manifest)


def attach(holder, root):
    """Lo llama BurstSearch.load. Con el flag apagado no toca el holder."""
    if not passages_enabled():
        return holder
    holder.passages = None
    try:
        holder.passages = load_passages(Path(root) / "passages")
        loaded = list(getattr(holder, "loaded", []) or [])
        if "passages" not in loaded:
            loaded.append("passages")
        holder.loaded = loaded
    except Exception as err:
        holder.passages = None
        holder.passages_error = f"{type(err).__name__}: {err}"[:200]
    return holder


def answer(index, gap, encode=None, error=None):
    """La misma respuesta para la ruta HTTP y para el método de Modal."""
    if index is None:
        body = {"enabled": False, "rows": []}
        if error:
            body["error"] = error
        return body
    gap = dict(gap or {})
    if gap.get("vector") is None and encode is not None:
        text = gap_text(gap)
        if text:
            vec = np.asarray(encode([text]), dtype=np.float32)
            gap["vector"] = vec[0]
    return {"enabled": True, "rows": index.query(gap)}
