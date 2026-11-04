import test from "node:test";
import assert from "node:assert/strict";

import { pickExplore, recordVisit, visitWhy } from "../src/lib/explore.js";

function mem() {
  const box = new Map();
  return {
    getItem: (key) => (box.has(key) ? box.get(key) : null),
    setItem: (key, value) => box.set(key, value),
  };
}

test("ida A B C, volver a B y saltar a D conserva a C", () => {
  const store = mem();
  const step = (id, from, at) => recordVisit(store, "Attention", { id, title: id, from, porQue: "cita", at });
  step("A", "", 1);
  step("B", "A", 2);
  step("C", "B", 3);
  const back = step("D", "B", 4);
  assert.deepEqual(back.nodes.map((node) => node.id), ["A", "B", "C", "D"]);
  assert.deepEqual(back.edges.map((edge) => `${edge.from}->${edge.to}`), ["A->B", "B->C", "B->D"]);
  const again = recordVisit(store, "Attention", { id: "D", title: "D", from: "B", porQue: "nota", at: 9 });
  const bd = again.edges.filter((edge) => edge.from === "B" && edge.to === "D");
  assert.equal(bd.length, 1);
  assert.equal(bd[0].at, 9);
  assert.equal(bd[0].porQue, "nota");
});

test("el mismo paper no agrega nodo ni arista, y el tope tira lo viejo", () => {
  const store = mem();
  recordVisit(store, "", { id: "A", title: "uno", from: "", at: 1 });
  const same = recordVisit(store, "", { id: "A", title: "dos", from: "A", porQue: "x", at: 2 });
  assert.equal(same.nodes.length, 1);
  assert.equal(same.edges.length, 0);
  assert.equal(same.q, "_solo");
  let last = same;
  for (let i = 1; i <= 200; i++) {
    last = recordVisit(store, "", { id: `n${i}`, title: `t${i}`, from: i === 1 ? "A" : `n${i - 1}`, at: i + 1 });
  }
  assert.ok(last.nodes.length <= 200);
  assert.ok(!last.nodes.some((node) => node.id === "A"));
  assert.ok(last.nodes.some((node) => node.id === "n200"));
});

test("sin pregunta, el deep link recupera el grafo que contiene el paper", () => {
  const all = {
    "how does self-attention replace recurrence": {
      q: "how does self-attention replace recurrence",
      nodes: [{ id: "13756489", title: "Attention", at: 2 }, { id: "bleu", title: "BLEU", at: 3 }],
      edges: [{ from: "13756489", to: "bleu", porQue: "cita", at: 3 }],
    },
  };
  const picked = pickExplore(all, "", "13756489");
  assert.equal(picked.nodes.length, 2);
  assert.equal(picked.edges[0].porQue, "cita");
  assert.equal(pickExplore(all, "otra", "").nodes.length, 0);
  assert.equal(pickExplore(all, "otra", "13756489").nodes.length, 0);
});

test("la primera visita dice de dónde salió y el salto del minimapa se lee", () => {
  const store = mem();
  const map = recordVisit(store, "how does self-attention replace recurrence", { id: "13756489", title: "Attention Is All You Need y un título largo que no cabe en la lista del minimapa", from: "", porQue: "desde el mapa", at: 1 });
  assert.equal(visitWhy(map.nodes[0], map.edges, map.q), "from the map");
  const jump = recordVisit(store, "how does self-attention replace recurrence", { id: "bleu", title: "BLEU", from: "13756489", porQue: "nodo del minimapa", at: 2 });
  assert.equal(visitWhy(jump.nodes[1], jump.edges, jump.q), "jump from the minimap");
  const solo = recordVisit(store, "", { id: "13756489", title: "Attention", from: "", at: 3 });
  assert.equal(visitWhy(solo.nodes[0], solo.edges, solo.q), "direct link");
});

test("si localStorage tira, el overflow recibe el json", () => {
  const store = {
    getItem: () => null,
    setItem: () => { throw new Error("quota"); },
  };
  let saved = "";
  recordVisit(store, "q", { id: "A", title: "t", from: "", at: 1 }, (json) => { saved = json; });
  assert.match(saved, /rrm|A/);
  assert.equal(JSON.parse(saved).q.nodes[0].id, "A");
});
