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
        return _specter(rows, edges, vectors)
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
