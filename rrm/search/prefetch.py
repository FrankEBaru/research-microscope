"""Queue the top papers before the reader container is warm.

`/status` is read as soon as `/burst` returns. The reader `prefetch` container
is often still cold then, so the status row has to be written here, on the
shared volume, before `spawn`.
"""

from pathlib import Path

from rrm.reader.pipeline import load_meta, mark_queued, save_meta, worker_alive


def top_ids(corpusids, limit=10) -> list[int]:
    ids = []
    for raw in list(corpusids or [])[: int(limit)]:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
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
