"""SPECTER2 vectors the FAISS index does not have. Cache on disk. No new index."""

from pathlib import Path

import numpy as np


def paper_text(row):
    """Title and abstract, the proximity-adapter input. Empty if both are missing."""
    title = str((row or {}).get("title") or "").strip()
    abstract = str((row or {}).get("abstract") or "").strip()
    if title and abstract:
        return title + "\n" + abstract
    return title or abstract


def cache_path(cache_dir, corpusid) -> Path:
    return Path(cache_dir) / f"{int(corpusid)}.npy"


def read_cache(cache_dir, corpusid):
    if not cache_dir:
        return None
    path = cache_path(cache_dir, corpusid)
    if not path.is_file():
        return None
    try:
        vec = np.load(path)
    except (OSError, ValueError):
        return None
    if getattr(vec, "ndim", 0) != 1 or int(vec.shape[0]) < 2:
        return None
    return np.ascontiguousarray(vec, dtype=np.float32)


def write_cache(cache_dir, corpusid, vec):
    if not cache_dir:
        return
    path = cache_path(cache_dir, corpusid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as handle:
        np.save(handle, np.ascontiguousarray(vec, dtype=np.float32))
    tmp.replace(path)


def slots_from(rows, stored, cache_dir=None):
    """Align stored vectors with rows. Fill holes from the cache. Missing ids still need an encode."""
    slots = []
    missing = []
    stored = list(stored or [])
    for i, row in enumerate(rows):
        vec = stored[i] if i < len(stored) else None
        if vec is None and cache_dir is not None:
            vec = read_cache(cache_dir, row["corpusid"])
        if vec is None:
            slots.append(None)
            missing.append(int(row["corpusid"]))
        else:
            slots.append(np.ascontiguousarray(vec, dtype=np.float32).reshape(-1))
    return slots, missing


def fill_encoded(rows, slots, encode, cache_dir=None):
    """Encode rows that still have no vector. Returns (matrix or None, ids still missing)."""
    slots = list(slots)
    want = []
    texts = []
    for i, row in enumerate(rows):
        if slots[i] is not None:
            continue
        text = paper_text(row)
        if not text:
            continue
        want.append(i)
        texts.append(text)
    if texts and encode is not None:
        made = np.asarray(encode(texts), dtype=np.float32)
        if made.ndim == 1:
            made = made.reshape(1, -1)
        for row_i, vec in zip(want, made):
            slots[row_i] = np.ascontiguousarray(vec, dtype=np.float32).reshape(-1)
            write_cache(cache_dir, rows[row_i]["corpusid"], slots[row_i])
    if any(vec is None for vec in slots):
        still = [int(rows[i]["corpusid"]) for i, vec in enumerate(slots) if vec is None]
        return None, still
    return np.stack(slots), []
