// Grafo de lo explorado, por pregunta. Volver atrás no lo recorta.

import { normalizeQuestion } from "./qcache.js";

export const EXPLORE_KEY = "rrm.explore.v1";
const MAX_NODES = 200;
const MAX_EDGES = 400;

function empty(q) {
  return { q, nodes: [], edges: [] };
}

function readAll(storage) {
  if (!storage) return {};
  try {
    const raw = storage.getItem(EXPLORE_KEY);
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === "object" && !Array.isArray(data) ? data : {};
  } catch {
    return {};
  }
}

function pack(row, q) {
  return {
    q,
    nodes: Array.isArray(row?.nodes) ? row.nodes : [],
    edges: Array.isArray(row?.edges) ? row.edges : [],
  };
}

export function readExplore(storage, question) {
  const q = normalizeQuestion(question) || "_solo";
  return pack(readAll(storage)[q], q);
}

/** Si esta pregunta no tiene visitas, usa el grafo guardado que contiene el paper. */
export function pickExplore(all, question, paperId) {
  const q = normalizeQuestion(question) || "_solo";
  const bag = all && typeof all === "object" && !Array.isArray(all) ? all : {};
  const own = pack(bag[q], q);
  if (own.nodes.length) return own;
  // Otra pregunta no hereda el camino de la anterior. Solo un enlace sin pregunta busca el paper.
  if (q !== "_solo") return own;
  const id = String(paperId || "");
  if (!id) return own;
  let best = null;
  let bestAt = -1;
  let bestKey = q;
  for (const [key, row] of Object.entries(bag)) {
    if (!row || !Array.isArray(row.nodes) || !row.nodes.length) continue;
    if (!row.nodes.some((node) => String(node.id) === id)) continue;
    const at = Math.max(0, ...row.nodes.map((node) => node.at || 0), ...(row.edges || []).map((edge) => edge.at || 0));
    if (!best || at >= bestAt) { best = row; bestAt = at; bestKey = key; }
  }
  return best ? pack(best, bestKey) : own;
}

export function readExploreFor(storage, question, paperId) {
  return pickExplore(readAll(storage), question, paperId);
}

const WHY = {
  "nodo del mapa": "from the map",
  "desde el mapa": "from the map",
  "from the map": "from the map",
  "nodo del minimapa": "jump from the minimap",
  "salto desde el minimapa": "jump from the minimap",
  "jump from the minimap": "jump from the minimap",
  "link directo": "direct link",
  "direct link": "direct link",
};

export function whyLabel(raw) {
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  return WHY[text] || text;
}
export function visitWhy(node, edges, q) {
  const id = String((node && node.id) || "");
  const best = (edges || []).filter((edge) => String(edge.to) === id).sort((a, b) => (a.at || 0) - (b.at || 0)).pop();
  if (best) return whyLabel(best.porQue);
  return whyLabel(node && node.llegada) || (q && q !== "_solo" ? "from the map" : "direct link");
}

function trim(entry, current) {
  const edges = entry.edges.slice().sort((a, b) => (a.at || 0) - (b.at || 0));
  while (edges.length > MAX_EDGES) edges.shift();
  let nodes = entry.nodes.slice();
  const dropIsolates = () => {
    const used = new Set();
    edges.forEach((edge) => {
      used.add(String(edge.from));
      used.add(String(edge.to));
    });
    nodes = nodes.filter((node) => String(node.id) === current || used.has(String(node.id)));
  };
  dropIsolates();
  while (nodes.length > MAX_NODES && edges.length) {
    edges.shift();
    dropIsolates();
  }
  while (nodes.length > MAX_NODES) {
    const victim = nodes.find((node) => String(node.id) !== current);
    if (!victim) break;
    nodes = nodes.filter((node) => node !== victim);
    const id = String(victim.id);
    for (let i = edges.length - 1; i >= 0; i--) {
      if (String(edges[i].from) === id || String(edges[i].to) === id) edges.splice(i, 1);
    }
  }
  entry.nodes = nodes;
  entry.edges = edges;
}

export function recordVisit(storage, question, visit, overflow) {
  const q = normalizeQuestion(question) || "_solo";
  const id = String((visit && visit.id) || "");
  const entry = readExplore(storage, question);
  entry.q = q;
  if (!id) return entry;
  const from = String((visit && visit.from) || "");
  const last = entry.nodes.length ? String(entry.nodes[entry.nodes.length - 1].id) : "";
  if (id === from || (id === last && !from)) return entry;
  const at = Number.isFinite(visit && visit.at) ? visit.at : Date.now();
  const title = String((visit && visit.title) || "").replace(/\s+/g, " ").trim();
  let node = entry.nodes.find((item) => String(item.id) === id);
  if (!node) {
    node = { id, title, at, llegada: String((visit && visit.porQue) || "") };
    entry.nodes.push(node);
  } else if (title) {
    node.title = title;
  }
  if (from) {
    const edge = entry.edges.find((item) => String(item.from) === from && String(item.to) === id);
    if (edge) {
      edge.at = at;
      edge.porQue = String((visit && visit.porQue) || "");
    } else {
      entry.edges.push({ from, to: id, porQue: String((visit && visit.porQue) || ""), at });
    }
  }
  trim(entry, id);
  const all = readAll(storage);
  all[q] = entry;
  const json = JSON.stringify(all);
  try {
    if (storage) storage.setItem(EXPLORE_KEY, json);
  } catch {
    if (typeof overflow === "function") overflow(json);
  }
  return entry;
}
