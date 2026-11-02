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

export function readExplore(storage, question) {
  const q = normalizeQuestion(question) || "_solo";
  const row = readAll(storage)[q];
  if (!row || typeof row !== "object") return empty(q);
  return {
    q,
    nodes: Array.isArray(row.nodes) ? row.nodes : [],
    edges: Array.isArray(row.edges) ? row.edges : [],
  };
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
    node = { id, title, at };
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
