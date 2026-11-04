// Atlas B.1: x is the paper's year, lanes are layout groups.
// Pure: no network, no DOM. Positions are display-only.

export const ATLAS_W = 900;
export const ATLAS_H = 500;
const GAP = 4;
const X0 = 168;
const SEP = 15;
const SEP_ITERS = 40;

export function hashId(id) {
  const s = String(id);
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Stable offset in [0, 0.9). Display only: it is not a year. */
export function yearOffset(id) {
  return hashId(id) % 0.9;
}

export function fullText(paper, state) {
  if (state?.gated) return false;
  if (paper?.full || state?.text) return true;
  if (state?.status === "done") return true;
  if (state?.source === "latex" || state?.source === "ocr") return true;
  return state?.stages?.sections === "done";
}

function paperId(paper) {
  if (typeof paper?.corpusid === "number" || (typeof paper?.corpusid === "string" && paper.corpusid !== "")) {
    return String(paper.corpusid);
  }
  return "";
}

function yearOf(paper) {
  const year = paper?.year;
  if (typeof year === "number" && Number.isInteger(year)) return year;
  return null;
}

function authorList(paper) {
  return (Array.isArray(paper?.authors) ? paper.authors : [])
    .map((author) => (typeof author === "string" ? author : author?.name))
    .filter(Boolean);
}

function stateFor(states, id) {
  if (!states) return undefined;
  if (states[id]) return states[id];
  const n = Number(id);
  if (Number.isFinite(n) && states[n]) return states[n];
  return undefined;
}

function cmpId(a, b) {
  const na = Number(a);
  const nb = Number(b);
  if (Number.isFinite(na) && Number.isFinite(nb) && String(na) === String(a) && String(nb) === String(b)) return na - nb;
  return String(a).localeCompare(String(b));
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) / 2)];
}

/** Parent is the earliest incoming edge that does not close a cycle. */
export function trailPairs(explore) {
  const edges = [...(explore?.edges || [])].sort((a, b) => (a.at || 0) - (b.at || 0));
  const parent = new Map();
  const cycles = (from, to) => {
    const seen = new Set();
    let cur = from;
    while (cur && !seen.has(cur)) {
      if (cur === to) return true;
      seen.add(cur);
      cur = parent.get(cur);
    }
    return false;
  };
  for (const edge of edges) {
    const to = String(edge?.to ?? "");
    const from = String(edge?.from ?? "");
    if (!to || !from || to === from || parent.has(to)) continue;
    if (cycles(from, to)) continue;
    parent.set(to, from);
  }
  return [...parent.entries()].map(([to, from]) => ({ from, to }));
}

export function lastVisit(explore) {
  let best = null;
  for (const node of explore?.nodes || []) {
    const id = String(node?.id ?? "");
    if (!id) continue;
    const at = Number.isFinite(node?.at) ? node.at : 0;
    if (!best || at >= best.at) best = { id, at };
  }
  return best ? best.id : "";
}

function visitedIds(explore) {
  const out = [];
  const seen = new Set();
  for (const node of explore?.nodes || []) {
    const id = String(node?.id ?? "");
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

function laneHeights(rows) {
  const gaps = Math.max(0, rows.length - 1) * GAP;
  const usable = ATLAS_H - gaps;
  const total = rows.reduce((sum, row) => sum + Math.max(1, row.n), 0) || 1;
  let top = 0;
  return rows.map((row) => {
    const h = Math.max(1, row.n) / total * usable;
    const box = { top, h };
    top += h + GAP;
    return box;
  });
}

// RRM-95: a year is a column whose width grows with sqrt(papers that year), so a
// recent, crowded field does not pile up at the right edge. A few very old
// outliers (under ~6 %) fold into one "earlier" column at the left instead of
// stretching the axis back decades. Ticks still name real years.
function placeX(points) {
  const dated = points.filter((p) => p.year != null);
  const undated = points.filter((p) => p.year == null);
  const x1 = undated.length ? 800 : 884;
  const noYearX = undated.length ? 852 : null;
  const ticks = [];
  if (!dated.length) {
    const x = noYearX ?? 450;
    for (const p of points) p.x = x;
    return { min: null, max: null, ticks, noYearX: x, earlierX: null, cut: null };
  }
  const sorted = dated.map((p) => p.year).sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  let cut = min;
  if (sorted.length >= 12) {
    const q = sorted[Math.floor(sorted.length * 0.06)];
    // Fold only when it saves real room: at least 4 years.
    if (q - min >= 4) cut = Math.max(q, max - 24);
  }
  const early = dated.filter((p) => p.year < cut);
  const earlierW = early.length ? 46 : 0;
  const xs = X0 + earlierW;
  const count = new Map();
  for (const p of dated) if (p.year >= cut) count.set(p.year, (count.get(p.year) || 0) + 1);
  const cols = [];
  let total = 0;
  for (let year = cut; year <= max; year++) {
    const w = 0.7 + Math.sqrt(count.get(year) || 0);
    cols.push({ year, w });
    total += w;
  }
  const span = x1 - xs;
  let at = xs;
  const col = new Map();
  for (const c of cols) {
    const w = (c.w / total) * span;
    col.set(c.year, { x: at, w });
    at += w;
  }
  for (const p of dated) {
    if (p.year < cut) {
      p.x = X0 + earlierW / 2 + ((hashId(p.id) % 1000) / 999 - 0.5) * 18;
      continue;
    }
    const c = col.get(p.year);
    const f = (hashId(p.id) % 1000) / 999;
    p.x = c.x + c.w * (0.18 + 0.64 * f);
  }
  for (const p of undated) p.x = noYearX;
  let lastX = early.length ? X0 + earlierW / 2 + 8 : -1e9;
  for (const c of cols) {
    const { x, w } = col.get(c.year);
    const cx = x + w / 2;
    const major = c.year === cut || c.year === max || c.year % 5 === 0;
    if (cx - lastX < 34 && !major) continue;
    if (cx - lastX < 30) continue;
    ticks.push({ year: c.year, x: cx, edge: x });
    lastX = cx;
  }
  return { min, max, ticks, noYearX, earlierX: early.length ? X0 + earlierW / 2 : null, cut: early.length ? cut : null };
}

function separate(items, top, h) {
  if (!items.length) return;
  const pad = Math.min(9, Math.max(1, h / 2 - 1));
  const lo = top + pad;
  const hi = Math.max(lo, top + h - pad);
  for (const p of items) {
    const v = (hashId(p.id) % 1000) / 999;
    p.y = top + v * h;
  }
  for (let it = 0; it < SEP_ITERS; it++) {
    for (let a = 0; a < items.length; a++) {
      for (let b = a + 1; b < items.length; b++) {
        const A = items[a];
        const B = items[b];
        const dx = A.x - B.x;
        const dy = A.y - B.y;
        const d = Math.hypot(dx, dy);
        const need = Math.max(SEP, (A.r || 0) + (B.r || 0) + 3);
        if (d < need) {
          const push = (need - d) / 2 || 0.5;
          // Mostly vertical (y means nothing); a little sideways stays inside the year column.
          const ux = d > 0.01 ? dx / d : 0;
          const s = dy >= 0 ? 1 : -1;
          A.y += s * push * 0.9;
          B.y -= s * push * 0.9;
          A.x += ux * push * 0.35;
          B.x -= ux * push * 0.35;
        }
      }
    }
  }
  for (const p of items) p.y = Math.max(lo, Math.min(hi, p.y));
  // One more pass after clamping, so the lane edge does not pile dots back together.
  for (let it = 0; it < 12; it++) {
    for (let a = 0; a < items.length; a++) {
      for (let b = a + 1; b < items.length; b++) {
        const A = items[a];
        const B = items[b];
        const d = Math.hypot(A.x - B.x, A.y - B.y);
        const need = Math.max(SEP, (A.r || 0) + (B.r || 0) + 3);
        if (d >= need) continue;
        const push = (need - d) / 2 || 0.5;
        const s = A.x >= B.x ? 1 : -1;
        A.x += s * push;
        B.x -= s * push;
      }
    }
  }
}

function circleModel(explore) {
  const nodes = explore?.nodes || [];
  const n = nodes.length;
  const points = nodes.map((node, i) => {
    const ang = -Math.PI / 2 + (i / Math.max(n, 1)) * Math.PI * 2;
    const id = String(node.id);
    const spread = n <= 1 ? 0 : 150;
    return basePoint({
      id,
      x: 450 + Math.cos(ang) * spread,
      y: 250 + Math.sin(ang) * (n <= 1 ? 0 : 120),
      year: null,
      lane: "",
      laneName: "",
      color: "var(--grp-1)",
      far: false,
      full: false,
      retracted: false,
      survey: false,
      rank: i,
      title: String(node.title || ""),
      authors: [],
      venue: "",
      abstract: "",
    });
  });
  const ids = new Set(points.map((p) => p.id));
  return {
    lanes: [],
    points,
    years: { min: null, max: null, ticks: [], noYearX: null },
    links: [],
    trail: trailPairs(explore).filter((pair) => ids.has(pair.from) && ids.has(pair.to)),
    visited: visitedIds(explore),
    lone: true,
  };
}

function basePoint(row) {
  return {
    cites: [],
    citedBy: [],
    authorLine: authorList({ authors: row.authors }).join(", "),
    ...row,
  };
}

function attachLinks(points, edges) {
  const ids = new Set(points.map((p) => p.id));
  const cites = new Map(points.map((p) => [p.id, []]));
  const citedBy = new Map(points.map((p) => [p.id, []]));
  const links = [];
  const seen = new Set();
  for (const edge of edges || []) {
    const citing = String(edge?.citing ?? "");
    const cited = String(edge?.cited ?? "");
    if (!ids.has(citing) || !ids.has(cited) || citing === cited) continue;
    const key = `${citing}>${cited}`;
    if (seen.has(key)) continue;
    seen.add(key);
    links.push({ from: citing, to: cited });
    cites.get(citing).push(cited);
    citedBy.get(cited).push(citing);
  }
  for (const p of points) {
    p.cites = cites.get(p.id) || [];
    p.citedBy = citedBy.get(p.id) || [];
  }
  return links;
}

export function atlasModel({ papers, edges, layout, states, explore } = {}) {
  const list = Array.isArray(papers) ? papers : [];
  const pointList = Array.isArray(layout?.points) ? layout.points : [];
  if (!list.length) return circleModel(explore);

  const byPaper = new Map();
  list.forEach((paper, index) => {
    const id = paperId(paper);
    if (!id || byPaper.has(id)) return;
    byPaper.set(id, { paper, index });
  });

  let ids;
  const clusterOf = new Map();
  if (pointList.length) {
    ids = [];
    const seen = new Set();
    for (const point of pointList) {
      const id = String(point?.corpusid ?? "");
      if (!id || seen.has(id)) continue;
      seen.add(id);
      ids.push(id);
      clusterOf.set(id, String(point.cluster ?? "0"));
    }
  } else {
    ids = [...byPaper.keys()];
    for (const id of ids) clusterOf.set(id, "all");
  }

  const groupList = Array.isArray(layout?.groups) && layout.groups.length
    ? layout.groups
    : [...new Set(clusterOf.values())].map((id) => ({ id, n: 0 }));

  const members = new Map();
  for (const group of groupList) members.set(String(group.id), []);
  for (const id of ids) {
    const cluster = clusterOf.get(id);
    if (!members.has(cluster)) members.set(cluster, []);
    members.get(cluster).push(id);
  }

  const laneRows = [];
  const seenLane = new Set();
  const pushLane = (id, source) => {
    const key = String(id);
    if (seenLane.has(key)) return;
    seenLane.add(key);
    const mem = members.get(key) || [];
    const years = mem.map((pid) => yearOf(byPaper.get(pid)?.paper)).filter((year) => year != null);
    const n = Number.isFinite(source?.n) ? source.n : mem.length;
    laneRows.push({
      id: key,
      n: n || mem.length,
      name: String(source?.name || ""),
      far: Boolean(source?.far),
      median: median(years),
      members: mem,
    });
  };
  for (const group of groupList) pushLane(group.id, group);
  for (const id of members.keys()) pushLane(id, { id, n: (members.get(id) || []).length });

  laneRows.sort((a, b) => {
    if (a.median == null && b.median == null) return cmpId(a.id, b.id);
    if (a.median == null) return 1;
    if (b.median == null) return -1;
    if (a.median !== b.median) return a.median - b.median;
    return cmpId(a.id, b.id);
  });

  const sole = laneRows.length === 1;
  const boxes = laneHeights(laneRows);
  const lanes = laneRows.map((row, i) => ({
    id: row.id,
    name: sole ? "" : row.name,
    n: row.n,
    far: row.far,
    color: `var(--grp-${(i % 6) + 1})`,
    top: boxes[i].top,
    h: boxes[i].h,
  }));
  const laneById = new Map(lanes.map((lane, i) => [lane.id, { lane, members: laneRows[i].members }]));

  const points = [];
  for (const id of ids) {
    const hit = byPaper.get(id);
    const paper = hit?.paper;
    const cluster = clusterOf.get(id);
    const lane = laneById.get(cluster)?.lane;
    const year = yearOf(paper);
    const authors = authorList(paper);
    points.push(basePoint({
      id,
      x: 0,
      y: 0,
      year,
      lane: lane?.id || "",
      laneName: lane?.name || "",
      color: lane?.color || "var(--grp-1)",
      far: Boolean(lane?.far),
      full: fullText(paper, stateFor(states, id)),
      retracted: Boolean(paper?.retracted),
      survey: Boolean(paper?.survey),
      rank: hit ? hit.index : 10000,
      title: String(paper?.title || ""),
      authors,
      venue: String(paper?.venue || ""),
      abstract: String(paper?.abstract || ""),
      citations: Number(paper?.citationcount ?? paper?.citations) || 0,
    }));
  }

  // RRM-95: size says weight. The first five of the ranking are badges; the
  // rest grow gently with log(citations), so a landmark reads from afar.
  const ord = new Map(readingOrder(points).map((row) => [row.id, row.n]));
  for (const p of points) {
    const n = ord.get(p.id) || 0;
    p.order = n;
    p.r = n && n <= 5 ? 9 : Math.min(7.2, 3.4 + 0.95 * Math.log10(1 + p.citations));
  }

  const years = placeX(points);
  for (const { lane, members: mem } of laneById.values()) {
    separate(points.filter((p) => mem.includes(p.id)), lane.top, lane.h);
  }

  const links = attachLinks(points, edges);
  const onMap = new Set(points.map((p) => p.id));
  return {
    lanes,
    points,
    years,
    links,
    trail: trailPairs(explore).filter((pair) => onMap.has(pair.from) && onMap.has(pair.to)),
    visited: visitedIds(explore),
    lone: false,
  };
}

/** 1 is the paper the search already ranked first. */
export function readingOrder(points) {
  return [...(points || [])]
    .filter((point) => point && point.id)
    .sort((a, b) => (a.rank - b.rank) || cmpId(a.id, b.id))
    .map((point, index) => ({ id: point.id, n: index + 1, rank: point.rank }));
}

export function suggestOf(model) {
  if (model?.visited?.length) return "";
  let best = null;
  for (const point of model?.points || []) {
    if (!best || point.rank < best.rank) best = point;
  }
  return best ? best.id : "";
}

export function related(model, id, cap = 14) {
  const points = model?.points || [];
  const by = new Map(points.map((p) => [p.id, p]));
  const p = by.get(String(id));
  if (!p) return [];
  const all = [];
  const seen = new Set();
  for (const other of [...p.cites, ...p.citedBy]) {
    if (!by.has(other) || seen.has(other)) continue;
    seen.add(other);
    all.push(other);
  }
  if (all.length <= cap) return all;
  const visited = new Set(model?.visited || []);
  return all
    .map((other) => {
      const q = by.get(other);
      const k = (visited.has(other) ? 0 : 1e4) + (q.full ? 0 : 1e3) + Math.hypot(q.x - p.x, q.y - p.y);
      return { other, k };
    })
    .sort((a, b) => a.k - b.k || String(a.other).localeCompare(String(b.other)))
    .slice(0, cap)
    .map((row) => row.other);
}

export function nearest(points, x, y, r = 18) {
  const list = Array.isArray(points) ? points : points?.points || [];
  let best = null;
  let bd = r;
  for (const p of list) {
    const d = Math.hypot(p.x - x, p.y - y);
    if (d < bd) { bd = d; best = p.id; }
  }
  return best;
}
