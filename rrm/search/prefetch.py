"""Queue the top papers before the reader container is warm.

`/status` is read as soon as `/burst` returns. Writing `meta.json` and
committing the volume from the burst handler made a warm `/burst` wait
seconds on disk. The ids are noted in a Modal dict before the response
returns; `/status` reports those ids as `queued` until the volume row exists.
The volume write and `prefetch` spawn run after the response.
"""

from pathlib import Path

from rrm.reader.pipeline import load_meta, mark_queued, save_meta, worker_alive

_BURST_TOP = "burst_top"
_burst_top = None


def top_ids(corpusids, limit=10) -> list[int]:
    ids = []
    for raw in list(corpusids or [])[: int(limit)]:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def _top_store():
    global _burst_top
    if _burst_top is None:
        import modal
        _burst_top = modal.Dict.from_name("rrm-reader-queue", create_if_missing=True)
    return _burst_top


def note_burst_top(corpusids, store=None) -> list[int]:
    """Remember top ids where `/status` can see them without a volume commit."""
    gate = _top_store() if store is None else store
    try:
        current = list(gate[_BURST_TOP])
    except Exception:
        current = []
    merged = []
    seen = set()
    for raw in list(current) + list(corpusids or []):
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        merged.append(cid)
    merged = merged[-40:]
    gate[_BURST_TOP] = merged
    return merged


def missing_status(corpusid, pending) -> str:
    """No meta.json yet: noted top-10 ids are queued, every other id is missing."""
    try:
        cid = int(corpusid)
    except (TypeError, ValueError):
        return "missing"
    return "queued" if cid in (pending or ()) else "missing"


def load_burst_top(store=None) -> set[int]:
    try:
        gate = _top_store() if store is None else store
        raw = gate[_BURST_TOP]
    except Exception:
        return set()
    out = set()
    for item in raw or []:
        try:
            out.add(int(item))
        except (TypeError, ValueError):
            continue
    return out


def detach_queue(corpusids, papers_root, *, spawn, commit, note, start) -> list[int]:
    """Note top ids, then hand `queue_top` to `start` without waiting for it.

    `note` runs before this returns. `start` must not run the write on the
    caller's stack: that commit is what slowed warm `/burst`.
    """
    ids = top_ids(corpusids)
    if not ids:
        return []
    note(ids)

    def work():
        queue_top(ids, papers_root, spawn=spawn, commit=commit)

    start(work)
    return ids


def queue_top(corpusids, papers_root, *, spawn, commit=None) -> list[int]:
    """Write `queued` for every top id, commit, then spawn. Spawn errors stay queued.

    A row this call created is marked stale (`started` 0) when spawn raises, so
    opening the paper can start a worker. A worker that was already alive is left alone.
    """
    ids = top_ids(corpusids)
    root = Path(papers_root)
    fresh = []
    for cid in ids:
        folder = root / str(cid)
        before = load_meta(folder)
        status = mark_queued(folder, cid)
        alive = bool(before) and before.get("status") in ("queued", "parsing") and worker_alive(before)
        if status == "queued" and not alive:
            fresh.append(cid)
    if ids and commit is not None:
        commit()
    if not ids:
        return []
    try:
        spawn(list(ids))
    except Exception:
        for cid in fresh:
            folder = root / str(cid)
            meta = load_meta(folder)
            if meta and meta.get("status") == "queued":
                meta["started"] = 0
                save_meta(folder, meta)
        if fresh and commit is not None:
            commit()
    return ids
