"""Question cache on the data volume. No Modal import.

One JSON file per normalized question: the burst payload and the last paper
status rows. A repeat question reads that file instead of FAISS.
"""

import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = "rrm-cache"
_STATUS_KEYS = ("id", "status", "stage", "reason", "source")


def normalize_question(text) -> str:
    """Lower case, collapsed whitespace. Shared with the browser cache."""
    return " ".join(str(text or "").casefold().split())


def question_digest(text) -> str:
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()


def entry_path(root, text) -> Path:
    return Path(root) / "burst" / f"{question_digest(text)}.json"


def load_entry(root, text):
    key = normalize_question(text)
    if not key:
        return None
    path = entry_path(root, text)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("q") != key:
        return None
    return data


def save_entry(root, text, *, burst=None, papers=None):
    """Merge and write. Returns the stored dict, or None when the question is empty."""
    key = normalize_question(text)
    if not key:
        return None
    current = load_entry(root, text) or {"q": key, "burst": None, "papers": {}}
    if burst is not None:
        current["burst"] = burst
    if papers is not None:
        merged = dict(current.get("papers") or {})
        merged.update(papers)
        current["papers"] = merged
    current["q"] = key
    path = entry_path(root, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return current


def cached_burst(entry, n: int):
    """Burst payload when the stored list is long enough. None otherwise."""
    if not isinstance(entry, dict):
        return None
    burst = entry.get("burst")
    if not isinstance(burst, dict):
        return None
    papers = burst.get("papers")
    if not isinstance(papers, list):
        return None
    stored = burst.get("n")
    try:
        stored_n = int(stored) if stored is not None else len(papers)
    except (TypeError, ValueError):
        stored_n = len(papers)
    n = max(0, int(n))
    if stored_n < n:
        return None
    out = dict(burst)
    out["papers"] = papers[:n]
    out["cached"] = True
    return out


def slim_status(row) -> dict | None:
    if not isinstance(row, dict):
        return None
    try:
        cid = int(row.get("id"))
    except (TypeError, ValueError):
        return None
    status = row.get("status")
    if status in (None, "", "missing"):
        return None
    out = {"id": cid, "status": status}
    for key in _STATUS_KEYS:
        if key in ("id", "status"):
            continue
        if key in row and row.get(key) is not None:
            out[key] = row.get(key)
    return out


def apply_status_cache(rows, saved):
    """A missing id keeps the status stored for that question. Fresh meta wins."""
    saved = saved or {}
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            out.append(row)
            continue
        prev = saved.get(str(row.get("id")))
        if row.get("status") == "missing" and isinstance(prev, dict) and prev.get("status") not in (None, "missing"):
            merged = dict(prev)
            merged["id"] = row.get("id")
            merged["cached"] = True
            out.append(merged)
        else:
            out.append(row)
    return out


def status_map(rows) -> dict:
    found = {}
    for row in rows or []:
        slim = slim_status(row)
        if slim is not None:
            found[str(slim["id"])] = slim
    return found
