"""2D positions for the live map. No network, no Modal.

SPECTER2, when every returned paper has a stored vector: PCA of those
vectors, groups where cosine similarity is at least ``COSINE_GROUP``, and a
nearest-neighbor link when cosine is at least ``NEIGHBOR_MIN``.

Without those vectors the map does not invent a projection. If the papers
cite each other and at least two have a year, x is the year and y is a force
layout of the citation edges. With citations but no years, both axes are that
force layout. With no citation inside the set, the points sit on a circle in
rank order.

Coordinates are in the same 1600×1000 field as the curated platina.
"""

from __future__ import annotations

import math
import os
import re

WORLD_W = 1600.0
WORLD_H = 1000.0
COSINE_GROUP = 0.80
NEIGHBOR_MIN = 0.50
_STEPS = 220
_MARGIN = 96.0
_MIN_GAP = 28.0


def place_papers(papers, edges, vectors=None, missing_vectors=None):
    """Layout for the papers list, in that order.

    ``vectors`` is (n, d) for every row, or None. ``missing_vectors`` lists
    corpus ids that had no stored SPECTER2 vector; the map then uses citations
    and records those ids instead of projecting a partial matrix.
    """
    rows = _rows(papers)
    if vectors is not None and len(rows) > 0 and _vector_count(vectors) == len(rows) and not missing_vectors:
        # kNN keeps who is close. `_specter` (PCA) stays in this file and is not the live path.
        return _knn_map(rows, edges, vectors)
    layout = _citation(rows, edges)
    if missing_vectors:
        layout["missing_vectors"] = [int(cid) for cid in missing_vectors]
    return layout


def _vector_count(vectors) -> int:
    try:
        return len(vectors)
    except TypeError:
        return 0


def _rows(papers):
    out = []
    for row in papers or []:
        if not isinstance(row, dict):
            continue
        cid = row.get("corpusid")
        if isinstance(cid, bool) or not isinstance(cid, int):
            continue
        out.append(row)
    return out


def _year(row):
    year = row.get("year")
    if isinstance(year, bool):
        return None
    if isinstance(year, int):
        return year
    if isinstance(year, float) and year == int(year):
        return int(year)
    return None


def _links(rows, edges):
    index = {row["corpusid"]: i for i, row in enumerate(rows)}
    directed = []
    seen = set()
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        citing = edge.get("citing")
        cited = edge.get("cited")
        if citing not in index or cited not in index or citing == cited:
            continue
        key = (int(citing), int(cited))
        if key in seen:
            continue
        seen.add(key)
        directed.append(key)
    undirected = []
    used = set()
    for citing, cited in directed:
        pair = (min(citing, cited), max(citing, cited))
        if pair in used:
            continue
        used.add(pair)
        undirected.append((index[citing], index[cited]))
    return directed, undirected


def _empty(method, grouping):
    return {
        "method": method,
        "width": WORLD_W,
        "height": WORLD_H,
        "points": [],
        "links": [],
        "similarity": [],
        "groups": [],
        "grouping": grouping,
    }


def _point(row, rank, x, y, cluster, nudged=False):
    item = {
        "corpusid": int(row["corpusid"]),
        "x": round(float(x), 2),
        "y": round(float(y), 2),
        "cluster": int(cluster),
        "rank": int(rank),
    }
    if nudged:
        item["nudged"] = True
    return item


def _finish(method, rows, pos, clusters, directed, grouping, extra=None, years=None):
    nudged = _separate(pos, pin_x=(method == "year-citation"))
    points = [
        _point(row, i, pos[i][0], pos[i][1], clusters[i], nudged=i in nudged)
        for i, row in enumerate(rows)
    ]
    counts = {}
    for cluster in clusters:
        counts[cluster] = counts.get(cluster, 0) + 1
    groups = [{"id": cid, "n": counts[cid], "kind": grouping} for cid in sorted(counts)]
    out = {
        "method": method,
        "width": WORLD_W,
        "height": WORLD_H,
        "points": points,
        "links": [{"citing": a, "cited": b, "kind": "citation"} for a, b in directed],
        "similarity": [],
        "groups": groups,
        "grouping": grouping,
    }
    if years is not None:
        out["years"] = years
    if extra:
        out.update(extra)
    return out


def _citation(rows, edges):
    n = len(rows)
    if n == 0:
        return _empty("rank-circle", "none")
    directed, undirected = _links(rows, edges)
    years = [_year(row) for row in rows]
    known = [year for year in years if year is not None]
    if n == 1 or not undirected:
        pos = _circle(n)
        clusters = [0] * n
        return _finish("rank-circle", rows, pos, clusters, directed, "none")
    if len(known) >= 2:
        return _year_citation(rows, years, known, directed, undirected)
    pos = _circle(n)
    _force(pos, undirected, pin=None)
    _fit(pos)
    clusters = _components(n, undirected)
    grouping = "citation-component"
    return _finish("citation-graph", rows, pos, clusters, directed, grouping)


def _year_citation(rows, years, known, directed, undirected):
    n = len(rows)
    y0, y1 = min(known), max(known)
    span = max(1, y1 - y0)
    left, right = 180.0, WORLD_W - 280.0
    gutter = WORLD_W - 120.0

    def x_of(i):
        # A missing year is a labeled gutter, not a point past the last year.
        if years[i] is None:
            return gutter
        return left + (right - left) * ((years[i] - y0) / span)

    pos = _circle(n)
    for i in range(n):
        pinned = x_of(i)
        if pinned is not None:
            pos[i][0] = pinned
    _force(pos, undirected, pin=x_of)
    for i in range(n):
        pinned = x_of(i)
        if pinned is not None:
            pos[i][0] = pinned
    _spread_y(pos)
    missing = [int(rows[i]["corpusid"]) for i in range(n) if years[i] is None]
    # One citation component is common in a top-10. Color stays one group:
    # the year axis is the measured separation, not a made-up topic.
    clusters = [0] * n
    return _finish(
        "year-citation",
        rows,
        pos,
        clusters,
        directed,
        "year",
        extra={"gutter_x": round(gutter, 2)} if missing else None,
        years={"min": int(y0), "max": int(y1), "missing": missing},
    )


def _circle(n):
    pos = []
    if n <= 0:
        return pos
    if n == 1:
        return [[WORLD_W / 2, WORLD_H / 2]]
    radius = min(WORLD_W, WORLD_H) * 0.28
    for i in range(n):
        ang = -math.pi / 2 + (2 * math.pi * i) / n
        pos.append([WORLD_W / 2 + radius * math.cos(ang), WORLD_H / 2 + radius * math.sin(ang)])
    return pos


def _force(pos, undirected, pin):
    n = len(pos)
    if n <= 1:
        return
    k = math.sqrt((WORLD_W * WORLD_H) / n) * 0.42
    for step in range(_STEPS):
        temp = 48.0 * (1 - step / _STEPS) + 0.35
        disp = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist = math.hypot(dx, dy) or 0.01
                force = (k * k) / dist
                ux, uy = dx / dist, dy / dist
                disp[i][0] += ux * force
                disp[i][1] += uy * force
                disp[j][0] -= ux * force
                disp[j][1] -= uy * force
        for i, j in undirected:
            dx = pos[i][0] - pos[j][0]
            dy = pos[i][1] - pos[j][1]
            dist = math.hypot(dx, dy) or 0.01
            force = (dist * dist) / k
            ux, uy = dx / dist, dy / dist
            disp[i][0] -= ux * force
            disp[i][1] -= uy * force
            disp[j][0] += ux * force
            disp[j][1] += uy * force
        for i in range(n):
            if pin is not None:
                pinned = pin(i)
                if pinned is not None:
                    disp[i][0] += (pinned - pos[i][0]) * 6.0
            dist = math.hypot(disp[i][0], disp[i][1]) or 1.0
            scale = min(dist, temp) / dist
            pos[i][0] += disp[i][0] * scale
            pos[i][1] += disp[i][1] * scale
            pos[i][0] = min(WORLD_W - 70, max(70, pos[i][0]))
            pos[i][1] = min(WORLD_H - 70, max(70, pos[i][1]))
            if pin is not None:
                pinned = pin(i)
                if pinned is not None:
                    pos[i][0] = pinned


def _spread_y(pos):
    """Keep the force layout's vertical shape. Only a small scale-up if it collapsed."""
    if len(pos) <= 1:
        return
    ys = [p[1] for p in pos]
    lo, hi = min(ys), max(ys)
    span = hi - lo
    mid = (lo + hi) / 2
    if span < 1:
        for i, p in enumerate(pos):
            p[1] = WORLD_H / 2 + (i - (len(pos) - 1) / 2) * 36
        return
    scale = min(1.25, max(1.0, 280.0 / span))
    for p in pos:
        p[1] = min(WORLD_H - 140, max(140, WORLD_H / 2 + (p[1] - mid) * scale))


def _fit(pos):
    if len(pos) <= 1:
        return
    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    spanx = max(maxx - minx, 1.0)
    spany = max(maxy - miny, 1.0)
    left, right = _MARGIN, WORLD_W - _MARGIN
    top, bot = _MARGIN, WORLD_H - _MARGIN
    for p in pos:
        p[0] = left + (right - left) * ((p[0] - minx) / spanx)
        p[1] = top + (bot - top) * ((p[1] - miny) / spany)


def _separate(pos, pin_x):
    """Push stacked points apart. The flag says the gap is for reading, not distance."""
    nudged = set()
    n = len(pos)
    for _ in range(12):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[j][0] - pos[i][0]
                dy = pos[j][1] - pos[i][1]
                dist = math.hypot(dx, dy)
                if dist >= _MIN_GAP:
                    continue
                moved = True
                nudged.add(i)
                nudged.add(j)
                if dist < 0.01:
                    dx, dy, dist = 0.0, 1.0, 1.0
                push = (_MIN_GAP - dist) / 2 + 0.4
                ux, uy = dx / dist, dy / dist
                if pin_x:
                    uy = 1.0 if dy >= 0 else -1.0
                    ux = 0.0
                pos[i][0] -= ux * push
                pos[i][1] -= uy * push
                pos[j][0] += ux * push
                pos[j][1] += uy * push
        if not moved:
            break
    for p in pos:
        p[0] = min(WORLD_W - 48, max(48, p[0]))
        p[1] = min(WORLD_H - 48, max(48, p[1]))
    return nudged


def _components(n, undirected):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in undirected:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
    roots = {}
    clusters = []
    for i in range(n):
        root = find(i)
        if root not in roots:
            roots[root] = len(roots)
        clusters.append(roots[root])
    return clusters


def _specter(rows, edges, vectors):
    import numpy as np

    n = len(rows)
    directed, _undirected = _links(rows, edges)
    raw = np.asarray(vectors, dtype=np.float64)
    if raw.ndim != 2 or raw.shape[0] != n:
        return _citation(rows, edges)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-9, None)
    unit = raw / norms
    sim = unit @ unit.T
    clusters = _cosine_groups(sim)
    similarity = _neighbors(rows, sim)
    coords = _pca(unit)
    _orient(coords, n)
    pos = _scale_pca(coords)
    extra = {
        "similarity": similarity,
        "cosine_min": COSINE_GROUP,
        "neighbor_min": NEIGHBOR_MIN,
        "variance": _variance(unit),
    }
    return _finish("specter2-pca", rows, pos, clusters, directed, "cosine", extra=extra)


def _pca(unit):
    import numpy as np

    n = unit.shape[0]
    if n == 1:
        return np.zeros((1, 2), dtype=np.float64)
    centered = unit - unit.mean(axis=0, keepdims=True)
    _u, s, vt = np.linalg.svd(centered, full_matrices=False)
    coords = np.zeros((n, 2), dtype=np.float64)
    take = min(2, vt.shape[0])
    coords[:, :take] = centered @ vt[:take].T
    # ``s`` is unused for the coordinates (they are the projections) but kept
    # so a zero second component stays a line instead of a fake spread.
    if s.size < 2 or float(s[1]) < 1e-8:
        coords[:, 1] = 0.0
    return coords


def _variance(unit):
    import numpy as np

    if unit.shape[0] < 2:
        return [1.0, 0.0]
    centered = unit - unit.mean(axis=0, keepdims=True)
    _u, s, _vt = np.linalg.svd(centered, full_matrices=False)
    energy = s ** 2
    total = float(energy.sum())
    if total <= 0:
        return [0.0, 0.0]
    first = float(energy[0] / total) if energy.size else 0.0
    second = float(energy[1] / total) if energy.size > 1 else 0.0
    return [round(first, 4), round(second, 4)]


def _orient(coords, n):
    """SVD sign is arbitrary. Rank 0 points to +x; the next free point to +y."""
    if n == 0:
        return
    if coords[0, 0] < 0:
        coords[:, 0] *= -1
    j = 1 if n > 1 else 0
    if coords[j, 1] < 0:
        coords[:, 1] *= -1


def _scale_pca(coords):
    import numpy as np

    pos = coords.astype(np.float64).copy()
    if len(pos) == 1:
        return [[WORLD_W / 2, WORLD_H / 2]]
    minx, maxx = float(pos[:, 0].min()), float(pos[:, 0].max())
    miny, maxy = float(pos[:, 1].min()), float(pos[:, 1].max())
    spanx = max(maxx - minx, 1e-6)
    spany = max(maxy - miny, 1e-6)
    # Same scale on both axes so a round group stays round.
    scale = min((WORLD_W - 2 * _MARGIN) / spanx, (WORLD_H - 2 * _MARGIN) / spany)
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    out = []
    for i in range(len(pos)):
        out.append([
            WORLD_W / 2 + (float(pos[i, 0]) - cx) * scale,
            WORLD_H / 2 + (float(pos[i, 1]) - cy) * scale,
        ])
    return out


def _cosine_groups(sim):
    n = sim.shape[0]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if float(sim[i, j]) >= COSINE_GROUP:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    roots = {}
    clusters = []
    for i in range(n):
        root = find(i)
        if root not in roots:
            roots[root] = len(roots)
        clusters.append(roots[root])
    return clusters


def map_rows(payload):
    """Ranked papers first, then FAISS hits that are not already in that list."""
    rows = []
    seen = set()
    for key in ("papers", "similar"):
        for row in (payload or {}).get(key) or []:
            if not isinstance(row, dict):
                continue
            cid = row.get("corpusid")
            if isinstance(cid, bool) or not isinstance(cid, int) or cid in seen:
                continue
            seen.add(cid)
            rows.append(row)
    return rows


_STOP = frozenset(
    """
    a an the of and or to for in on with from by as at is are was were be been being
    this that these those into over under between among its their our we you
    using use used via based paper papers approach approaches method methods
    study studies result results task tasks toward towards new show shown propose
    proposed model models data dataset datasets algorithm algorithms which where
    when while than then also can may such not only more most other into within
    between without across per each both all any few many one two three
    retraction retracted phys conf ser proceedings preprint copyright doi figure
    table university department page pages vol volume issue springer elsevier
    """.split()
)


def _keep(word):
    return word not in _STOP and not word.isdigit() and len(word) > 2


def _terms(text):
    raw = re.findall(r"[a-z][a-z0-9]+(?:-[a-z0-9]+)*", str(text or "").lower())
    words = [word for word in raw if _keep(word)]
    # Bigrams only when the two words were next to each other. Dropping a
    # stopword must not glue "relationship" to "architecture".
    bigrams = [
        f"{a} {b}" for a, b in zip(raw, raw[1:])
        if _keep(a) and _keep(b) and a not in b and b not in a
    ]
    return words + bigrams


def _stem(term):
    parts = []
    for word in term.split():
        if len(word) > 4 and word.endswith("s"):
            word = word[:-1]
        parts.append(word)
    return " ".join(parts)


_SURFACE = re.compile(r"[a-z][a-z0-9]+(?:-[a-z0-9]+)*", re.I)


def _display_name(term, surface):
    """The matching term back in the titles' own spelling (NeRF, GNN), first letter up."""
    from rrm.textcase import cap_first, enabled, is_identifier

    if not enabled():
        return term
    words = []
    for word in term.split():
        seen = surface.get(word)
        form = seen.most_common(1)[0][0] if seen else word
        words.append(form if is_identifier(form) or (form.isupper() and len(form) > 1) else word)
    return cap_first(" ".join(words))


def _cluster_names(rows, clusters):
    """c-TF-IDF keywords. No model, no question phrasing."""
    from collections import Counter

    ids = sorted(set(clusters))
    counts = {cid: Counter() for cid in ids}
    docs = {cid: Counter() for cid in ids}
    titles = {cid: Counter() for cid in ids}
    surface = {}
    for row in rows:
        for token in _SURFACE.findall(str(row.get("title") or "")):
            surface.setdefault(token.lower(), Counter())[token] += 1
    for row, cid in zip(rows, clusters):
        title = _terms(row.get("title"))
        abstract = _terms(row.get("abstract"))
        counts[cid].update(title)
        counts[cid].update(title)
        counts[cid].update(title)
        counts[cid].update(abstract)
        docs[cid].update(set(title) | set(abstract))
        titles[cid].update(set(title))
    total = Counter()
    for ctr in counts.values():
        total.update(ctr)
    sizes = [sum(ctr.values()) for ctr in counts.values() if ctr]
    avg = (sum(sizes) / len(sizes)) if sizes else 1.0
    pool = []
    for cid in ids:
        for term, tf in counts[cid].items():
            if titles[cid][term] < 2:
                continue
            if " " not in term or not 2 <= len(term.split()) <= 4:
                continue
            everywhere = float(total[term] or tf)
            pool.append((tf * math.log1p(avg / everywhere), cid, term))
    pool.sort(key=lambda item: (-item[0], -len(item[2]), item[2]))
    names = {}
    used = set()
    used_words = set()
    for _score, cid, term in pool:
        if cid in names:
            continue
        stem = _stem(term)
        if stem in used or all(word in used_words for word in stem.split()):
            continue
        names[cid] = term[:48]
        used.add(stem)
        used_words.update(stem.split())
    for cid in ids:
        if cid in names:
            continue
        words = [
            term for term, _tf in counts[cid].most_common()
            if " " not in term and titles[cid][term] >= 3 and _stem(term) not in used_words
        ]
        names[cid] = (words[0] if words else "grupo")[:48]
        used_words.update(_stem(names[cid]).split())
    return {cid: _display_name(name, surface) for cid, name in names.items()}


def _neighbor_stats(unit, pos, k):
    import numpy as np

    n = int(unit.shape[0])
    k = int(min(max(k, 0), max(n - 1, 0)))
    if n < 2 or k < 1:
        return {"k": 0, "preserved": 1.0, "trustworthiness": 1.0}
    sim = unit @ unit.T
    np.fill_diagonal(sim, -np.inf)
    high = np.argsort(-sim, axis=1)[:, :k]
    xy = np.asarray(pos, dtype=np.float64)
    dist = np.sum((xy[:, None, :] - xy[None, :, :]) ** 2, axis=2)
    np.fill_diagonal(dist, np.inf)
    low = np.argsort(dist, axis=1)[:, :k]
    hit = 0
    for i in range(n):
        hit += len(set(high[i].tolist()) & set(low[i].tolist()))
    preserved = hit / float(n * k)
    order = np.argsort(-sim, axis=1)
    rank = np.empty((n, n), dtype=np.int32)
    rank[np.arange(n)[:, None], order] = np.arange(1, n + 1)
    penalty = 0.0
    for i in range(n):
        extra = set(low[i].tolist()) - set(high[i].tolist())
        for j in extra:
            penalty += float(rank[i, j] - k)
    denom = n * k * (2 * n - 3 * k - 1)
    trust = 1.0 if denom <= 0 else 1.0 - (2.0 / denom) * penalty
    return {
        "k": k,
        "preserved": round(max(0.0, min(1.0, preserved)), 4),
        "trustworthiness": round(max(0.0, min(1.0, trust)), 4),
    }


def _renumber(clusters):
    seen = {}
    out = []
    for cid in clusters:
        if cid not in seen:
            seen[cid] = len(seen)
        out.append(seen[cid])
    return out


def _agglomerate(sim):
    n = int(sim.shape[0])
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = sorted(
        ((float(sim[i, j]), i, j) for i in range(n) for j in range(i + 1, n)),
        reverse=True,
    )
    for cos, i, j in edges:
        if cos < 0.72:
            break
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
    return _renumber([find(i) for i in range(n)])


def _kmeans(unit, k):
    import numpy as np

    n = int(unit.shape[0])
    k = int(min(max(k, 1), n))
    chosen = [int(np.argmax(np.linalg.norm(unit - unit.mean(axis=0), axis=1)))]
    for _ in range(k - 1):
        nearest = np.max(unit @ unit[chosen].T, axis=1)
        chosen.append(int(np.argmin(nearest)))
    cents = unit[np.asarray(chosen)].copy()
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(18):
        labels = np.argmax(unit @ cents.T, axis=1)
        for j in range(k):
            block = unit[labels == j]
            if len(block) == 0:
                cents[j] = unit[(chosen[0] + j) % n]
                continue
            mean = block.mean(axis=0)
            cents[j] = mean / (float(np.linalg.norm(mean)) or 1e-9)
    return labels


def _silhouette(unit, labels):
    import numpy as np

    dist = np.clip(1.0 - (unit @ unit.T), 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    labels = np.asarray(labels)
    kinds = sorted(set(int(c) for c in labels.tolist()))
    if len(kinds) < 2:
        return -1.0
    total = 0.0
    n = len(labels)
    for i in range(n):
        mine = labels == labels[i]
        mine[i] = False
        if not bool(mine.any()):
            continue
        a = float(dist[i, mine].mean())
        b = min(float(dist[i, labels == c].mean()) for c in kinds if c != int(labels[i]))
        total += (b - a) / max(a, b, 1e-9)
    return total / float(n)


def _median_groups(unit, target):
    """Split the biggest group on its first axis until there are `target` groups.

    k-means on a tight FAISS ball isolates one outlier. A median cut keeps
    every group large enough to read.
    """
    import numpy as np

    groups = [list(range(int(unit.shape[0])))]
    while len(groups) < target:
        groups.sort(key=len)
        big = groups.pop()
        if len(big) < 10:
            groups.append(big)
            break
        block = unit[np.asarray(big)]
        centered = block - block.mean(axis=0)
        vec = centered[int(np.argmax(np.linalg.norm(centered, axis=1)))]
        for _ in range(8):
            vec = centered.T @ (centered @ vec)
            norm = float(np.linalg.norm(vec))
            if norm < 1e-9:
                break
            vec /= norm
        order = np.argsort(centered @ vec)
        mid = len(big) // 2
        groups.append([big[int(i)] for i in order[:mid]])
        groups.append([big[int(i)] for i in order[mid:]])
    labels = [0] * int(unit.shape[0])
    for cid, members in enumerate(groups):
        for i in members:
            labels[i] = cid
    return labels


def _kmeans_pp(x, k, seed, iters=25):
    """Spherical k-means, k-means++ seeds from a fixed RNG. Returns (labels, inertia).

    Vectorized: a cold container builds the title index in a thread, and every
    Python-level step here waits on that thread's GIL.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    n = int(x.shape[0])
    chosen = [int(rng.integers(n))]
    for _ in range(k - 1):
        gap = np.clip(1.0 - np.max(x @ x[chosen].T, axis=1), 0.0, None)
        total = float(gap.sum())
        chosen.append(int(rng.choice(n, p=gap / total)) if total > 0 else int(rng.integers(n)))
    cents = x[np.asarray(chosen)].copy()
    labels = np.full(n, -1, dtype=np.int64)
    for _ in range(iters):
        new = np.argmax(x @ cents.T, axis=1)
        if np.array_equal(new, labels):
            break
        labels = new
        sums = (labels[None, :] == np.arange(k)[:, None]).astype(x.dtype) @ x
        norms = np.linalg.norm(sums, axis=1, keepdims=True)
        cents = np.where(norms > 1e-9, sums / np.clip(norms, 1e-9, None), cents)
    return labels, float(np.sum(1.0 - np.max(x @ cents.T, axis=1)))


def _silhouette_fast(x, labels):
    """Same value as _silhouette, without a Python loop over the points."""
    import numpy as np

    labels = np.asarray(labels)
    kinds = np.unique(labels)
    if len(kinds) < 2:
        return -1.0
    dist = np.clip(1.0 - (x @ x.T), 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    onehot = (labels[:, None] == kinds[None, :]).astype(np.float64)
    sizes = onehot.sum(axis=0)
    sums = dist @ onehot
    own = np.searchsorted(kinds, labels)
    rows = np.arange(len(labels))
    mine = sizes[own] - 1.0
    a = sums[rows, own] / np.clip(mine, 1.0, None)
    other = sums / sizes[None, :]
    other[rows, own] = np.inf
    b = other.min(axis=1)
    score = (b - a) / np.maximum(np.maximum(a, b), 1e-9)
    return float(np.where(mine > 0, score, 0.0).sum() / len(labels))


GROUP_MIN = 8
GROUP_SIL_MIN = 0.03
FAR_CORE = 0.94


def _proximity_groups(unit):
    """2 to 4 groups by real proximity, k by silhouette; one group if none holds.

    The FAISS ball is tight: every vector shares the query direction, so the
    vectors are centered before k-means. No group under GROUP_MIN papers.
    """
    import numpy as np

    n = int(unit.shape[0])
    if n < 12:
        return _agglomerate(unit @ unit.T)
    floor = GROUP_MIN if n >= 5 * GROUP_MIN else max(3, n // 5)
    x = unit - unit.mean(axis=0)
    x = x / np.clip(np.linalg.norm(x, axis=1, keepdims=True), 1e-9, None)
    best, score = None, GROUP_SIL_MIN
    for k in range(2, min(4, n // floor) + 1):
        labels = min((_kmeans_pp(x, k, seed) for seed in range(4)), key=lambda t: t[1])[0]
        counts = np.bincount(labels, minlength=k)
        counts = counts[counts > 0]
        if len(counts) < 2 or int(counts.min()) < floor:
            continue
        got = _silhouette_fast(x, labels)
        if got > score:
            best, score = labels.tolist(), got
    return _renumber(best) if best is not None else [0] * n


def _far_groups(unit, clusters, top=10):
    """Groups with none of the top papers and a centroid far from theirs."""
    import numpy as np

    if len(set(clusters)) < 2:
        return set()
    core = unit[: min(top, len(clusters))].mean(axis=0)
    core = core / (float(np.linalg.norm(core)) or 1e-9)
    far = set()
    for cid in set(clusters):
        idx = [i for i, c in enumerate(clusters) if c == cid]
        if any(i < top for i in idx):
            continue
        mean = unit[np.asarray(idx)].mean(axis=0)
        if float(mean @ core) / (float(np.linalg.norm(mean)) or 1e-9) < FAR_CORE:
            far.add(cid)
    return far


def _group_mode():
    return "median" if os.environ.get("RRM_GROUPS", "").strip().lower() == "median" else "proximity"


def _groups_of(unit):
    """3 to 6 groups (RRM_GROUPS=median, the pre-RRM-49 path). k by silhouette when every group has enough papers."""
    n = int(unit.shape[0])
    if n < 12:
        return _agglomerate(unit @ unit.T)
    floor = 5 if n >= 25 else 3
    hi = min(6, max(3, n // floor))
    best, score = None, -2.0
    for k in range(3, hi + 1):
        labels = _kmeans(unit, k)
        counts = {}
        for cid in labels.tolist():
            counts[int(cid)] = counts.get(int(cid), 0) + 1
        if len(counts) < 3 or min(counts.values()) < floor:
            continue
        got = _silhouette(unit, labels)
        if got > score:
            best, score = labels.tolist(), got
    if best is None:
        best = _median_groups(unit, min(4, hi))
    return _renumber(best)


def _local_pack(m):
    """Even dots inside the circle. A collapsed PCA left them stacked."""
    gap = 30.0
    if m <= 1:
        return [[0.0, 0.0]], 40.0
    pos = []
    for i in range(m):
        rad = gap * 0.5 * math.sqrt(i)
        ang = i * 2.39996323
        pos.append([rad * math.cos(ang), rad * math.sin(ang)])
    for _ in range(10):
        moved = False
        for i in range(m):
            for j in range(i + 1, m):
                dx = pos[j][0] - pos[i][0]
                dy = pos[j][1] - pos[i][1]
                dist = math.hypot(dx, dy)
                if dist >= gap:
                    continue
                moved = True
                if dist < 0.01:
                    dx, dy, dist = 1.0, 0.0, 1.0
                push = (gap - dist) / 2
                pos[i][0] -= dx / dist * push
                pos[i][1] -= dy / dist * push
                pos[j][0] += dx / dist * push
                pos[j][1] += dy / dist * push
        if not moved:
            break
    span = max(math.hypot(p[0], p[1]) for p in pos)
    return pos, span + gap * 0.75




def _pack(radii, gap=88.0):
    """Rows, not a ring: the platina is wide, and a ring leaves the groups small."""
    g = len(radii)
    if g == 0:
        return []
    if g == 1:
        return [(0.0, 0.0)]
    cols = g
    centers = []
    rows = [radii[i : i + cols] for i in range(0, g, cols)]
    row_gap = gap + 36.0
    height = sum(2 * max(row) for row in rows) + row_gap * (len(rows) - 1)
    y = -height / 2
    for row in rows:
        y += max(row)
        width = sum(2 * radius for radius in row) + gap * (len(row) - 1)
        x = -width / 2
        for radius in row:
            x += radius
            centers.append((x, y))
            x += radius + gap
        y += max(row) + row_gap
    return centers


def _fit_groups(centers, radii):
    if not centers:
        return centers, radii
    minx = min(x - r for (x, _y), r in zip(centers, radii))
    maxx = max(x + r for (x, _y), r in zip(centers, radii))
    miny = min(y - r for (_x, y), r in zip(centers, radii))
    maxy = max(y + r for (_x, y), r in zip(centers, radii))
    spanx = max(maxx - minx, 1.0)
    spany = max(maxy - miny, 1.0)
    left, right = 120.0, WORLD_W - 120.0
    top, bot = 150.0, WORLD_H - 110.0
    scale = min((right - left) / spanx, (bot - top) / spany)
    # Use the width. A second shrink left the groups as a small knot in the middle.
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    ox = (left + right) / 2
    oy = (top + bot) / 2
    fitted = [((x - cx) * scale + ox, (y - cy) * scale + oy) for x, y in centers]
    return fitted, [r * scale for r in radii]


def _knn_map(rows, edges, vectors):
    import numpy as np

    n = len(rows)
    directed, _undirected = _links(rows, edges)
    raw = np.asarray(vectors, dtype=np.float64)
    if raw.ndim != 2 or raw.shape[0] != n:
        return _citation(rows, edges)
    norms = np.clip(np.linalg.norm(raw, axis=1, keepdims=True), 1e-9, None)
    unit = raw / norms
    sim = unit @ unit.T
    if _group_mode() == "median":
        clusters, far = _groups_of(unit), set()
    else:
        clusters = _proximity_groups(unit)
        far = _far_groups(unit, clusters)
    names = _cluster_names(rows, clusters)
    members = {}
    for i, cid in enumerate(clusters):
        members.setdefault(cid, []).append(i)
    axis = _pca(unit)[:, 0]
    order = sorted(members, key=lambda cid: (cid in far, float(sum(axis[i] for i in members[cid]) / len(members[cid]))))
    local = {}
    radii = []
    for cid in order:
        pos, radius = _local_pack(len(members[cid]))
        local[cid] = pos
        radii.append(radius)
    raw_radii = list(radii)
    centers, radii = _fit_groups(_pack(radii), radii)
    world = [[0.0, 0.0] for _ in range(n)]
    groups = []
    for cid, center, radius, raw in zip(order, centers, radii, raw_radii):
        sx, sy = center
        grown = radius / max(raw, 1.0)
        for slot, i in enumerate(members[cid]):
            world[i][0] = sx + local[cid][slot][0] * grown
            world[i][1] = sy + local[cid][slot][1] * grown
        groups.append({
            "id": int(cid),
            "n": len(members[cid]),
            "kind": "knn",
            "name": names.get(cid) or "grupo",
            "cx": round(sx, 2),
            "cy": round(sy, 2),
            "r": round(radius, 2),
            **({"far": True} if cid in far else {}),
        })
    for p in world:
        p[0] = min(WORLD_W - 36, max(36, p[0]))
        p[1] = min(WORLD_H - 36, max(36, p[1]))
    k = min(8, n - 1)
    stats = _neighbor_stats(unit, world, k)
    points = []
    for i, row in enumerate(rows):
        item = _point(row, i, world[i][0], world[i][1], clusters[i])
        if i < 10:
            item["focus"] = True
        points.append(item)
    return {
        "method": "specter2-knn",
        "width": WORLD_W,
        "height": WORLD_H,
        "points": points,
        "links": [{"citing": a, "cited": b, "kind": "citation"} for a, b in directed],
        "similarity": _neighbors(rows, sim),
        "groups": groups,
        "grouping": "knn",
        "neighbors": stats,
        "cosine_min": 0.72,
        "variance": _variance(unit),
    }


def _neighbors(rows, sim):
    n = sim.shape[0]
    pairs = []
    seen = set()
    for i in range(n):
        best, score = None, NEIGHBOR_MIN
        for j in range(n):
            if i == j:
                continue
            value = float(sim[i, j])
            if value > score:
                best, score = j, value
        if best is None:
            continue
        a = int(rows[i]["corpusid"])
        b = int(rows[best]["corpusid"])
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"a": key[0], "b": key[1], "cosine": round(score, 4)})
    return pairs
