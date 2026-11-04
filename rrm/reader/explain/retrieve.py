"""Recuperación para Explain: oraciones del paper abierto y pasajes de otros papers.

Las oraciones se encodean una vez por paper con SPECTER2 (`units.npy` junto al
paper). Los pasajes salen del índice v2 (`passages/faiss.index`, coseno) y se
quedan solo los de otros papers y sin basura (`junk_mask.npy`).
"""

import hashlib
import json
import os
import threading
from pathlib import Path

import numpy as np

_LOCK = threading.Lock()
_MEMO = {}


def _encode(texts, encode=None):
    if encode is None:
        from rrm.reader.similar import specter_encode as encode
    vecs = np.asarray(encode(list(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def _unit_text(unit):
    return unit["text"]


def unit_vectors(units, folder=None, encode=None):
    """Vectores normalizados de las oraciones. Caché en disco por hash del texto."""
    digest = hashlib.sha256("\n".join(u["id"] + "\t" + u["text"] for u in units).encode()).hexdigest()[:16]
    with _LOCK:
        hit = _MEMO.get(digest)
    if hit is not None:
        return hit
    path = Path(folder) / f"explain-units-{digest}.npy" if folder else None
    vecs = None
    if path is not None and path.is_file():
        try:
            vecs = np.load(path, allow_pickle=False)
            if vecs.shape[0] != len(units):
                vecs = None
        except (OSError, ValueError):
            vecs = None
    if vecs is None:
        vecs = _encode([_unit_text(u) for u in units], encode) if units else np.zeros((0, 768), np.float32)
        if path is not None:
            try:
                tmp = path.with_name(f".{path.stem}.{os.getpid()}.npy")
                np.save(tmp, vecs)
                os.replace(tmp, path)
            except OSError:
                pass
    with _LOCK:
        _MEMO[digest] = vecs
    return vecs


def rank_units(query_vecs, units, vecs, k=4, prefer=None, bonus=0.03):
    """Top-k oraciones por consulta. `prefer` (ids de la sección) suma un pequeño bono."""
    if len(units) == 0 or query_vecs is None or len(query_vecs) == 0:
        return [[] for _ in range(len(query_vecs) if query_vecs is not None else 0)]
    sims = np.asarray(query_vecs) @ np.asarray(vecs).T
    if prefer:
        mask = np.array([1.0 if u["id"] in prefer else 0.0 for u in units], dtype=np.float32)
        sims = sims + bonus * mask
    out = []
    for row in sims:
        order = np.argsort(-row)[:k]
        out.append([(units[i], float(row[i])) for i in order])
    return out


class PassageBase:
    """Índice v2 de pasajes. Se carga una vez por proceso."""

    def __init__(self, root):
        import faiss
        import pyarrow.parquet as pq

        root = Path(root)
        table = pq.read_table(root / "rows.parquet", columns=["id", "corpusid", "kind", "section", "text", "latex", "title", "license", "url"])
        self.rows = table.to_pylist()
        self.index = faiss.read_index(str(root / "faiss.index"))
        junk = root / "junk_mask.npy"
        self.junk = np.load(junk) if junk.is_file() else np.zeros(len(self.rows), dtype=bool)

    def search(self, vecs, k=12, exclude=None):
        """[(fila, coseno)] únicos, mejores primero. Sin el paper abierto ni basura."""
        q = np.ascontiguousarray(np.asarray(vecs, dtype=np.float32))
        dists, ids = self.index.search(q, k * 3)
        best = {}
        for drow, irow in zip(dists, ids):
            taken = 0
            for score, idx in zip(drow, irow):
                idx = int(idx)
                if idx < 0 or idx >= len(self.rows) or (idx < len(self.junk) and self.junk[idx]):
                    continue
                row = self.rows[idx]
                if exclude is not None and str(row.get("corpusid")) == str(exclude):
                    continue
                text = str(row.get("text") or "")
                if len(text) < 60:
                    continue
                if idx not in best or score > best[idx][1]:
                    best[idx] = (row, float(score))
                taken += 1
                if taken >= k:
                    break
        return sorted(best.values(), key=lambda item: -item[1])


_BASES = {}


def passage_base(root=None):
    from rrm.reader.passage_db import passages_dir

    root = str(root or passages_dir())
    with _LOCK:
        base = _BASES.get(root)
    if base is None:
        base = PassageBase(root)
        with _LOCK:
            _BASES[root] = base
    return base


def passage_text(row, limit=420):
    """Texto citable de un pasaje: prosa con su LaTeX en línea, recortado."""
    text = " ".join(str(row.get("text") or "").split())
    if len(text) > limit:
        cut = text[:limit]
        stop = max(cut.rfind(". "), cut.rfind("; "))
        text = (cut[: stop + 1] if stop > limit // 2 else cut.rsplit(" ", 1)[0]) + " …"
    return text


def dump(obj):
    return json.dumps(obj, ensure_ascii=False)
