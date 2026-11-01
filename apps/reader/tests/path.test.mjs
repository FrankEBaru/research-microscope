import test from "node:test";
import assert from "node:assert/strict";

import { mergeLabels, popVisit, pushVisit, resolveCite } from "../src/lib/path.js";
import { pinPoint } from "../src/lib/layout.js";

test("no duplica el paper abierto y el padre es la visita anterior", () => {
  let stack = [];
  stack = pushVisit(stack, "1", "nodo del mapa");
  stack = pushVisit(stack, "1", "nodo del minimapa");
  assert.equal(stack.length, 1);
  assert.equal(stack[0].padre, null);
  stack = pushVisit(stack, "2", "cita en el paper");
  assert.equal(stack.length, 2);
  assert.equal(stack[1].padre, "1");
  assert.equal(stack[1].porQue, "cita en el paper");
  const back = popVisit(stack);
  assert.equal(back.length, 1);
  assert.equal(back[0].id, "1");
  assert.deepEqual(popVisit(back), []);
});

test("el survey se agrega una vez y el retractado se marca sin inventarlo", () => {
  const papers = [{ corpusid: 1, title: "A" }, { corpusid: 2, title: "B" }];
  const body = {
    ok: true,
    by_id: { "2": { abstract: "abs", retracted: true, retraction: "retractado", survey: false } },
    survey_paper: { corpusid: 9, title: "Survey real", survey: true },
  };
  const merged = mergeLabels(papers, body);
  assert.equal(merged[1].retracted, true);
  assert.equal(merged[1].abstract, "abs");
  assert.equal(merged[2].corpusid, 9);
  assert.equal(merged[2].survey, true);
  const again = mergeLabels(merged, body);
  assert.equal(again.filter((row) => row.corpusid === 9).length, 1);
  const offline = mergeLabels(papers, { ok: false, note: "Sin red: solo el título, sin survey." });
  assert.equal(offline.length, 2);
  assert.equal(offline[0].survey, undefined);
});

test("los autores de /labels reemplazan el título mudo", () => {
  const papers = [{ corpusid: 1, title: "What Can", year: 2022 }];
  const merged = mergeLabels(papers, { ok: true, by_id: { "1": { authors: ["Yann LeCun"], abstract: "" } } });
  assert.deepEqual(merged[0].authors, ["Yann LeCun"]);
  const kept = mergeLabels(papers, { ok: true, by_id: { "1": { authors: [] } } });
  assert.equal(kept[0].authors, undefined);
});

test("el punto del survey no mueve a los demás", () => {
  const layout = { points: [{ corpusid: 1, x: 10, y: 20, rank: 0, cluster: 1 }] };
  const next = pinPoint(layout, { corpusid: 9 });
  assert.equal(next.points[0].x, 10);
  assert.equal(next.points[1].corpusid, 9);
  assert.equal(pinPoint(next, { corpusid: 9 }).points.length, 2);
});

test("la cita BibTeX abre solo si el mapa trae s2", () => {
  assert.equal(resolveCite("s2:12", {}), "12");
  assert.equal(resolveCite("Cho2014a", { Cho2014a: "s2:99" }), "99");
  assert.equal(resolveCite("Cho2014a", {}), "");
});
