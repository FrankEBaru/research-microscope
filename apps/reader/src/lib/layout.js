import { paperKey } from "./backend.js";
import { phaseOf } from "./qcache.js";

// Positions for the live map. The server is the source of the coordinates.
// This file repeats the citation / year / rank layout for a cached payload
// that was stored before `layout` existed. It does not invent SPECTER2 points.

export const WORLD_W = 1600;
export const WORLD_H = 1000;

function authorNames(paper) {
  return (Array.isArray(paper?.authors) ? paper.authors : [])
    .map((author) => (typeof author === "string" ? author : author?.name))
    .filter(Boolean);
}

/** Apellido y año cuando hay autor. Si no, el título corto, entero si cabe. */
export function nodeLabel(paper) {
  const year = paper?.year ? String(paper.year) : "";
  const first = authorNames(paper)[0];
  if (first) {
    const last = String(first).split(/[\s,]+/).filter(Boolean).pop();
    return `${last || first}${year ? ` ${year}` : ""}`;
  }
  const title = String(paper?.title || "").replace(/\s+/g, " ").trim();
  if (!title) return year ? `paper ${year}` : "paper";
  const room = year ? 32 : 40;
  let text = title;
  if (title.length > room) {
    const cut = title.slice(0, room).replace(/\s+\S*$/, "").trim();
    text = `${cut.length >= 8 ? cut : title.slice(0, room).trim()}…`;
  }
  return year ? `${text} ${year}` : text;
}

/** «Autor Año · sección». Nunca el id de corpus. */
export function citeName(paper, section) {
  const who = paper ? nodeLabel(paper) : "";
  const sec = String(section || "").replace(/\s+/g, " ").trim();
  if (who && sec) return `${who} · ${sec}`;
  return who || sec || "paper";
}

// Misma regla que rrm/search/querylang.py FAR_GAP. Los tops de RRM-42 van de 0.72 a 0.82.
export const FAR_GAP = 0.15;

/** Ids de grupo cuya mediana cae FAR_GAP por debajo del mejor paper de esta pregunta. */
export function farGroupIds(papers, points) {
  const score = new Map();
  for (const paper of papers || []) {
    if (typeof paper?.query_cosine === "number") score.set(paper.corpusid, paper.query_cosine);
  }
  const buckets = new Map();
  for (const point of points || []) {
    const value = score.get(point.corpusid);
    if (typeof value !== "number") continue;
    const key = String(point.cluster);
    const list = buckets.get(key) || [];
    list.push(value);
    buckets.set(key, list);
  }
  if (buckets.size < 2) return new Set();
  let top = null;
  for (const list of buckets.values()) top = Math.max(top ?? -Infinity, ...list);
  const far = new Set();
  for (const [id, list] of buckets) {
    const ordered = [...list].sort((a, b) => a - b);
    const mid = ordered[Math.floor((ordered.length - 1) / 2)];
    if (top - mid >= FAR_GAP) far.add(id);
  }
  return far;
}

export function groupPacks(papers, layout) {
  const by = new Map((papers || []).map((paper) => [paper.corpusid, paper]));
  const groups = new Map();
  for (const point of layout?.points || []) {
    const paper = by.get(point.corpusid);
    if (!paper) continue;
    const id = String(point.cluster);
    const bucket = groups.get(id) || { id, titles: [], abstracts: [] };
    if (paper.title) bucket.titles.push(String(paper.title));
    if (paper.abstract) bucket.abstracts.push(String(paper.abstract).slice(0, 800));
    groups.set(id, bucket);
  }
  return [...groups.values()];
}

export function applyGroupNames(result, names) {
  if (!result?.layout?.groups || !names?.length) return result;
  const by = new Map(names.map((row) => [String(row.id), row.name]));
  let changed = false;
  const groups = result.layout.groups.map((group) => {
    const name = by.get(String(group.id));
    if (!name || name === group.name) return group;
    changed = true;
    return { ...group, name };
  });
  if (!changed) return result;
  return { ...result, layout: { ...result.layout, groups } };
}
const STEPS = 220;
const MARGIN = 96;
const MIN_GAP = 28;

export function mapPapers(result) {
  const ranked = Array.isArray(result?.papers) ? result.papers : [];
  const seen = new Set(ranked.map((paper) => paper?.corpusid));
  const extra = (Array.isArray(result?.similar) ? result.similar : []).filter(
    (paper) => paper && Number.isInteger(paper.corpusid) && !seen.has(paper.corpusid),
  );
  return ranked.concat(extra);
}

export function layoutOf(payload) {
  const papers = Array.isArray(payload?.papers) ? payload.papers : [];
  const layout = payload?.layout;
  if (layout && covers(layout, papers)) return layout;
  return placePapers(papers, payload?.edges || []);
}

function covers(layout, papers) {
  const ids = new Set((layout.points || []).map((p) => p.corpusid));
  return papers.length > 0 && papers.every((p) => ids.has(p.corpusid));
}

export function placePapers(papers, edges) {
  const rows = (papers || []).filter((row) => row && Number.isInteger(row.corpusid));
  return citation(rows, edges || []);
}

function yearOf(row) {
  const year = row.year;
  if (typeof year === "number" && Number.isInteger(year)) return year;
  return null;
}

function linksOf(rows, edges) {
  const index = new Map(rows.map((row, i) => [row.corpusid, i]));
  const directed = [];
  const seen = new Set();
  for (const edge of edges || []) {
    const citing = edge?.citing;
    const cited = edge?.cited;
    if (!index.has(citing) || !index.has(cited) || citing === cited) continue;
    const key = `${citing}>${cited}`;
    if (seen.has(key)) continue;
    seen.add(key);
    directed.push([citing, cited]);
  }
  const undirected = [];
  const used = new Set();
  for (const [citing, cited] of directed) {
    const pair = `${Math.min(citing, cited)}:${Math.max(citing, cited)}`;
    if (used.has(pair)) continue;
    used.add(pair);
    undirected.push([index.get(citing), index.get(cited)]);
  }
  return { directed, undirected };
}

function circle(n) {
  if (n <= 0) return [];
  if (n === 1) return [[WORLD_W / 2, WORLD_H / 2]];
  const radius = Math.min(WORLD_W, WORLD_H) * 0.28;
  const pos = [];
  for (let i = 0; i < n; i++) {
    const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;
    pos.push([WORLD_W / 2 + radius * Math.cos(ang), WORLD_H / 2 + radius * Math.sin(ang)]);
  }
  return pos;
}

function force(pos, undirected, pin) {
  const n = pos.length;
  if (n <= 1) return;
  const k = Math.sqrt((WORLD_W * WORLD_H) / n) * 0.42;
  for (let step = 0; step < STEPS; step++) {
    const temp = 48 * (1 - step / STEPS) + 0.35;
    const disp = pos.map(() => [0, 0]);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = pos[i][0] - pos[j][0];
        const dy = pos[i][1] - pos[j][1];
        const dist = Math.hypot(dx, dy) || 0.01;
        const push = (k * k) / dist;
        const ux = dx / dist;
        const uy = dy / dist;
        disp[i][0] += ux * push;
        disp[i][1] += uy * push;
        disp[j][0] -= ux * push;
        disp[j][1] -= uy * push;
      }
    }
    for (const [i, j] of undirected) {
      const dx = pos[i][0] - pos[j][0];
      const dy = pos[i][1] - pos[j][1];
      const dist = Math.hypot(dx, dy) || 0.01;
      const pull = (dist * dist) / k;
      const ux = dx / dist;
      const uy = dy / dist;
      disp[i][0] -= ux * pull;
      disp[i][1] -= uy * pull;
      disp[j][0] += ux * pull;
      disp[j][1] += uy * pull;
    }
    for (let i = 0; i < n; i++) {
      if (pin) {
        const pinned = pin(i);
        if (pinned != null) disp[i][0] += (pinned - pos[i][0]) * 6;
      }
      const dist = Math.hypot(disp[i][0], disp[i][1]) || 1;
      const scale = Math.min(dist, temp) / dist;
      pos[i][0] += disp[i][0] * scale;
      pos[i][1] += disp[i][1] * scale;
      pos[i][0] = Math.min(WORLD_W - 70, Math.max(70, pos[i][0]));
      pos[i][1] = Math.min(WORLD_H - 70, Math.max(70, pos[i][1]));
      if (pin) {
        const pinned = pin(i);
        if (pinned != null) pos[i][0] = pinned;
      }
    }
  }
}

function spreadY(pos) {
  if (pos.length <= 1) return;
  const ys = pos.map((p) => p[1]);
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const span = hi - lo;
  const mid = (lo + hi) / 2;
  if (span < 1) {
    pos.forEach((p, i) => { p[1] = WORLD_H / 2 + (i - (pos.length - 1) / 2) * 36; });
    return;
  }
  const scale = Math.min(1.25, Math.max(1, 280 / span));
  for (const p of pos) p[1] = Math.min(WORLD_H - 140, Math.max(140, WORLD_H / 2 + (p[1] - mid) * scale));
}

function fit(pos) {
  if (pos.length <= 1) return;
  const xs = pos.map((p) => p[0]);
  const ys = pos.map((p) => p[1]);
  const minx = Math.min(...xs);
  const maxx = Math.max(...xs);
  const miny = Math.min(...ys);
  const maxy = Math.max(...ys);
  const spanx = Math.max(maxx - minx, 1);
  const spany = Math.max(maxy - miny, 1);
  const left = MARGIN;
  const right = WORLD_W - MARGIN;
  const top = MARGIN;
  const bot = WORLD_H - MARGIN;
  for (const p of pos) {
    p[0] = left + (right - left) * ((p[0] - minx) / spanx);
    p[1] = top + (bot - top) * ((p[1] - miny) / spany);
  }
}

function separate(pos, pinX) {
  const nudged = new Set();
  const n = pos.length;
  for (let pass = 0; pass < 12; pass++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = pos[j][0] - pos[i][0];
        let dy = pos[j][1] - pos[i][1];
        let dist = Math.hypot(dx, dy);
        if (dist >= MIN_GAP) continue;
        moved = true;
        nudged.add(i);
        nudged.add(j);
        if (dist < 0.01) { dx = 0; dy = 1; dist = 1; }
        const push = (MIN_GAP - dist) / 2 + 0.4;
        let ux = dx / dist;
        let uy = dy / dist;
        if (pinX) { uy = dy >= 0 ? 1 : -1; ux = 0; }
        pos[i][0] -= ux * push;
        pos[i][1] -= uy * push;
        pos[j][0] += ux * push;
        pos[j][1] += uy * push;
      }
    }
    if (!moved) break;
  }
  for (const p of pos) {
    p[0] = Math.min(WORLD_W - 48, Math.max(48, p[0]));
    p[1] = Math.min(WORLD_H - 48, Math.max(48, p[1]));
  }
  return nudged;
}

function components(n, undirected) {
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (x) => {
    while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; }
    return x;
  };
  for (const [i, j] of undirected) {
    const ri = find(i);
    const rj = find(j);
    if (ri !== rj) parent[rj] = ri;
  }
  const roots = new Map();
  const clusters = [];
  for (let i = 0; i < n; i++) {
    const root = find(i);
    if (!roots.has(root)) roots.set(root, roots.size);
    clusters.push(roots.get(root));
  }
  return clusters;
}

function finish(method, rows, pos, clusters, directed, grouping, extra, years) {
  const nudged = separate(pos, method === "year-citation");
  const points = rows.map((row, i) => {
    const item = {
      corpusid: row.corpusid,
      x: Math.round(pos[i][0] * 100) / 100,
      y: Math.round(pos[i][1] * 100) / 100,
      cluster: clusters[i],
      rank: i,
    };
    if (nudged.has(i)) item.nudged = true;
    return item;
  });
  const counts = new Map();
  for (const cluster of clusters) counts.set(cluster, (counts.get(cluster) || 0) + 1);
  const groups = [...counts.keys()].sort((a, b) => a - b).map((id) => ({ id, n: counts.get(id), kind: grouping }));
  const out = {
    method,
    width: WORLD_W,
    height: WORLD_H,
    points,
    links: directed.map(([citing, cited]) => ({ citing, cited, kind: "citation" })),
    similarity: [],
    groups,
    grouping,
  };
  if (years) out.years = years;
  if (extra) Object.assign(out, extra);
  return out;
}

function citation(rows, edges) {
  const n = rows.length;
  if (n === 0) {
    return { method: "rank-circle", width: WORLD_W, height: WORLD_H, points: [], links: [], similarity: [], groups: [], grouping: "none" };
  }
  const { directed, undirected } = linksOf(rows, edges);
  const years = rows.map(yearOf);
  const known = years.filter((year) => year != null);
  if (n === 1 || undirected.length === 0) {
    return finish("rank-circle", rows, circle(n), rows.map(() => 0), directed, "none");
  }
  if (known.length >= 2) return yearCitation(rows, years, known, directed, undirected);
  const pos = circle(n);
  force(pos, undirected, null);
  fit(pos);
  return finish("citation-graph", rows, pos, components(n, undirected), directed, "citation-component");
}

function yearCitation(rows, years, known, directed, undirected) {
  const n = rows.length;
  const y0 = Math.min(...known);
  const y1 = Math.max(...known);
  const span = Math.max(1, y1 - y0);
  const left = 180;
  const right = WORLD_W - 280;
  const gutter = WORLD_W - 120;
  const xOf = (i) => (years[i] == null ? gutter : left + (right - left) * ((years[i] - y0) / span));
  const pos = circle(n);
  for (let i = 0; i < n; i++) pos[i][0] = xOf(i);
  force(pos, undirected, xOf);
  for (let i = 0; i < n; i++) pos[i][0] = xOf(i);
  spreadY(pos);
  const missing = rows.filter((_, i) => years[i] == null).map((row) => row.corpusid);
  return finish(
    "year-citation",
    rows,
    pos,
    rows.map(() => 0),
    directed,
    "year",
    missing.length ? { gutter_x: Math.round(gutter * 100) / 100 } : null,
    { min: y0, max: y1, missing },
  );
}

const CLUSTER_COLORS = ["#27476b", "#3d5a47", "#8a5a2b", "#5c4d7a", "#3e6b66", "#6d5a4a"];

export function statusLine(papers, states) {
  const counts = { encontrado: 0, preparando: 0, listo: 0, fallo: 0 };
  for (const paper of papers || []) counts[phaseOf(states?.[paperKey(paper)]?.status).id] += 1;
  const bit = (n, one, many) => (n ? (n === 1 ? `1 ${one}` : `${n} ${many}`) : "");
  return [
    bit(counts.preparando, "preparando", "preparando"),
    bit(counts.encontrado, "encontrado", "encontrados"),
    bit(counts.listo, "listo", "listos"),
    bit(counts.fallo, "falló", "fallaron"),
  ].filter(Boolean).join(" · ");
}

export function clusterColor(id) {
  const n = Number(id) || 0;
  return CLUSTER_COLORS[((n % CLUSTER_COLORS.length) + CLUSTER_COLORS.length) % CLUSTER_COLORS.length];
}

export function pointRadius(rank, n) {
  const t = n <= 1 ? 0 : rank / (n - 1);
  return 13 - t * 6;
}

export function mapCaption(layout) {
  const method = layout?.method;
  const nudged = (layout?.points || []).some((p) => p.nudged);
  const nudge = nudged ? " Algunos puntos se separaron para no quedar encima; esa separación no es una distancia." : "";
  if (method === "specter2-knn") {
    const kept = layout?.neighbors?.preserved;
    const pct = typeof kept === "number" ? ` Se conservan ${Math.round(kept * 100)}% de los vecinos.` : "";
    return {
      position: "posición: vecinos de SPECTER2",
      positionKind: "calculo",
      positionTitle: `Cada paper queda junto a los que SPECTER2 ve cerca. El círculo es un grupo; el nombre son palabras del título y el abstract, sin un modelo.${pct}`,
      grouping: "color del círculo: grupo",
      edges: "línea tenue al pasar el mouse: cita (Semantic Scholar)",
      similar: "",
      note: "Los 10 primeros son más grandes. El resto de lo que FAISS revisó se queda en su grupo, más tenue.",
    };
  }
  if (method === "specter2-pca") {
    const share = (layout.variance || []).reduce((a, b) => a + (Number(b) || 0), 0);
    const pct = share > 0 ? ` (${Math.round(share * 100)}% de la varianza)` : "";
    const groups = layout.groups || [];
    const grouping = groups.length > 1
      ? `color: grupos con coseno ≥ ${layout.cosine_min}`
      : `un solo grupo (coseno ≥ ${layout.cosine_min ?? 0.8})`;
    return {
      position: `PCA de SPECTER2${pct}`,
      positionKind: "calculo",
      positionTitle: "Proyección lineal de los vectores SPECTER2 de estos papers. Las dos ejes usan la misma escala.",
      grouping,
      edges: "línea sólida: cita (Semantic Scholar)",
      similar: (layout.similarity || []).length ? "línea punteada: vecino más cercano por SPECTER2" : "",
      note: nudge.trim(),
    };
  }
  if (method === "year-citation") {
    const missing = layout?.years?.missing?.length || 0;
    return {
      position: "horizontal: año del índice",
      positionKind: "calculo",
      positionTitle: "El eje horizontal es el año. El vertical acerca papers que se citan. No es una proyección SPECTER2.",
      grouping: "un solo color: el año ya separa",
      edges: "línea sólida: cita (Semantic Scholar)",
      similar: "",
      note: `${missing ? `${missing} sin año, en la columna de la derecha. ` : ""}${nudge}`.trim(),
    };
  }
  if (method === "citation-graph") {
    return {
      position: "posición por las citas de esta ráfaga",
      positionKind: "calculo",
      positionTitle: "Layout de fuerzas sobre las citas entre estos papers. No es SPECTER2.",
      grouping: "color: componente de citas",
      edges: "línea sólida: cita (Semantic Scholar)",
      similar: "",
      note: nudge.trim(),
    };
  }
  return {
    position: "círculo según el ranking",
    positionKind: "calculo",
    positionTitle: "No hay citas entre estos papers ni vectores SPECTER2 en la respuesta. El orden del círculo es el puesto, no una similitud.",
    grouping: "",
    edges: "",
    similar: "",
    note: "",
  };
}

export function pinPoint(layout, paper) {
  if (!layout || !paper || !Number.isInteger(paper.corpusid)) return layout;
  const points = Array.isArray(layout.points) ? layout.points : [];
  if (points.some((point) => point.corpusid === paper.corpusid)) return layout;
  return { ...layout, points: [...points, { corpusid: paper.corpusid, x: 1488, y: 96, rank: points.length, cluster: 0 }] };
}
