"""Vecinos en la base de pasajes v2 (rows.parquet + faiss.index de e3).

SPECTER2 (adhoc_query para consultas cortas, proximity para texto largo o con
salto de línea; mismo criterio que `rrm.search.encode`). El índice es
IndexFlatIP sobre vectores normalizados: el puntaje es coseno.

- `exclude`: corpusids fuera (el propio paper, para «otros papers»).
- `only`: corpusids permitidos (C3: sólo papers citados).
- Filas basura (`junk_mask.npy` de e3) fuera siempre.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

import numpy as np

_LOCK = threading.Lock()
_STATE = {}


def _root():
    from rrm.reader.passage_db import passages_dir

    return passages_dir()


def _load():
    with _LOCK:
        if "rows" in _STATE:
            return _STATE
        import faiss
        import pyarrow.parquet as pq

        root = _root()
        cols = ["id", "corpusid", "arxiv_id", "kind", "section", "text", "latex", "license", "url", "title", "head"]
        table = pq.read_table(root / "rows.parquet", columns=cols)
        _STATE["rows"] = table
        _STATE["cid"] = np.asarray(table.column("corpusid").to_numpy(zero_copy_only=False), dtype=np.int64)
        _STATE["index"] = faiss.read_index(str(root / "faiss.index"))
        junk = root / "junk_mask.npy"
        _STATE["junk"] = np.load(junk) if junk.is_file() else np.zeros(len(table), dtype=bool)
        if _STATE["junk"].dtype != bool:
            _STATE["junk"] = _STATE["junk"].astype(bool)
        return _STATE


_ENC = {}


def encode(texts):
    """float32 (n, 768), normalizados L2."""
    from rrm.reader.similar import specter_encode

    vecs = np.asarray(specter_encode(list(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def row(i):
    st = _load()
    rec = {k: st["rows"].column(k)[i].as_py() for k in ("id", "corpusid", "arxiv_id", "kind", "section", "text", "latex", "license", "url", "title", "head")}
    return rec


_ROW_BY_ID = {}


def row_by_id(pid):
    st = _load()
    if not _ROW_BY_ID:
        ids = st["rows"].column("id").to_pylist()
        _ROW_BY_ID.update({str(x): i for i, x in enumerate(ids)})
    i = _ROW_BY_ID.get(str(pid))
    return None if i is None else row(i)


def _cache_path(key):
    raw = os.environ.get("RRM_ANALYSIS_CACHE", "").strip()
    if not raw:
        return None
    return Path(raw) / "retrieve" / f"{key}.json"


def search(queries, k=10, exclude=(), only=None, kinds=None, min_chars=60, overfetch=8):
    """Top-k por consulta. Devuelve [[{pid, corpusid, cosine, kind, title, text}], ...]."""
    st = _load()
    queries = [str(q or "").strip() for q in queries]
    key = hashlib.sha256(json.dumps([queries, k, sorted(exclude), sorted(only) if only is not None else None, kinds, min_chars], ensure_ascii=False).encode()).hexdigest()[:24]
    cp = _cache_path(key)
    if cp and cp.is_file():
        return json.loads(cp.read_text(encoding="utf-8"))
    vecs = encode(queries)
    excl = np.asarray(sorted(int(c) for c in exclude), dtype=np.int64)
    allow = None if only is None else set(int(c) for c in only)
    index = st["index"]
    out = []
    if allow is not None:
        # Búsqueda restringida: producto punto exacto sobre las filas de esos papers.
        mask = np.isin(st["cid"], np.asarray(sorted(allow), dtype=np.int64)) & ~st["junk"]
        idxs = np.nonzero(mask)[0]
        if len(idxs):
            sub = np.vstack([index.reconstruct(int(i)) for i in idxs]).astype(np.float32)
            sub /= np.maximum(np.linalg.norm(sub, axis=1, keepdims=True), 1e-9)
    for qi, q in enumerate(queries):
        hits = []
        if allow is not None:
            if len(idxs):
                scores = sub @ vecs[qi]
                order = np.argsort(-scores)
                cand = [(float(scores[j]), int(idxs[j])) for j in order[: k * overfetch]]
            else:
                cand = []
        else:
            d, ii = index.search(vecs[qi:qi + 1], k * overfetch)
            cand = [(float(s), int(i)) for s, i in zip(d[0], ii[0]) if i >= 0]
        for score, i in cand:
            if st["junk"][i]:
                continue
            if len(excl) and st["cid"][i] in excl:
                continue
            r = row(i)
            if kinds and r["kind"] not in kinds:
                continue
            if len((r["text"] or "") + (r["latex"] or "")) < min_chars:
                continue
            hits.append({"pid": str(r["id"]), "corpusid": int(r["corpusid"]), "cosine": round(score, 4), "kind": r["kind"],
                         "title": r["title"] or "", "section": r["section"] or "", "text": r["text"] or "", "latex": r["latex"] or "",
                         "url": r["url"] or "", "license": r["license"] or ""})
            if len(hits) >= k:
                break
        out.append(hits)
    if cp:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out
