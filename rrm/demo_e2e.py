"""Settle and OCR-cap rules for the 12-prompt demo. No network.

These supersede the PR #9 stop line ("if two papers show stage ocr or source ocr").
That line counted papers OCR'd on an earlier run. Count a paper only when this
run called the GPU: meta.ocr_gpu_s > 0 and meta.ocr_invoked_at is at or after
the unix time recorded before the first prompt.

`missing` is not settled. A top-10 id with no status row is still in flight.
"""

SETTLED_STATUSES = frozenset({"done", "abstract_only", "failed"})


def is_settled(status) -> bool:
    return status in SETTLED_STATUSES


def top_settled(ids, rows) -> bool:
    found = {}
    for row in rows or []:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        try:
            found[int(row["id"])] = row.get("status")
        except (TypeError, ValueError):
            continue
    return all(is_settled(found.get(int(i))) for i in ids)


def _meta(row) -> dict:
    if not isinstance(row, dict):
        return {}
    meta = row.get("meta")
    if isinstance(meta, dict):
        return meta
    return row


def spent_gpu_this_run(row, run_started_at: float) -> bool:
    """True when this run's OCR used the GPU. Cached OCR from an earlier run is false."""
    meta = _meta(row)
    try:
        invoked = float(meta["ocr_invoked_at"])
        gpu = float(meta.get("ocr_gpu_s") or 0)
        started = float(run_started_at)
    except (KeyError, TypeError, ValueError):
        return False
    return gpu > 0 and invoked >= started


def ocr_cap_reached(rows, run_started_at: float, limit: int = 2) -> bool:
    n = sum(1 for row in rows or [] if spent_gpu_this_run(row, run_started_at))
    return n >= int(limit)
