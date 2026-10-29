"""Who may take the next arXiv slot.

The order list is only the jobs blocked on a download right now. `hot` is the
paper the user opened: it moves ahead of prefetch, including on its next
request, and it does not block anyone while it is not waiting.
"""


def _normalize(order, hot):
    hot = [int(x) for x in hot]
    rank = {}
    for i, cid in enumerate(hot):
        rank.setdefault(cid, i)
    waiting = []
    seen = set()
    for cid in order:
        cid = int(cid)
        if cid in seen:
            continue
        seen.add(cid)
        waiting.append(cid)
    hot_ids = [cid for cid in waiting if cid in rank]
    hot_ids.sort(key=lambda cid: rank[cid])
    rest = [cid for cid in waiting if cid not in rank]
    return hot_ids + rest, hot


def note(order, hot, cid, *, front: bool):
    """front=True is an open (`paper?id=`). front=False joins the prefetch tail."""
    cid = int(cid)
    order = [int(x) for x in order]
    hot = [int(x) for x in hot]
    if front:
        hot = [cid] + [x for x in hot if x != cid]
    elif cid not in order:
        order = order + [cid]
    return _normalize(order, hot)


def release(order, hot, cid):
    """One download finished. Stay hot so the next request of this paper is still first."""
    cid = int(cid)
    order = [int(x) for x in order if int(x) != cid]
    return _normalize(order, hot)


def forget(order, hot, cid):
    """The job is over. Drop it from both lists."""
    cid = int(cid)
    order = [int(x) for x in order if int(x) != cid]
    hot = [int(x) for x in hot if int(x) != cid]
    return _normalize(order, hot)
