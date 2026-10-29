import test from "node:test";
import assert from "node:assert/strict";
import { themesOf, simulatePaper, assemble, runSimulated } from "../src/lib/musesim.js";
import { buildPanorama } from "../src/lib/panorama.js";

const T = (v) => ({ t: "text", v });
const doc = (...ss) => ({ blocks: ss.map((s, i) => ({ id: `b${i}`, kind: "p", abs: i === 0, inlines: [T(s)] })) });
const docs = {
  a: doc("Attention mechanisms let a model weigh every position of the input sequence.", "Scaling laws show that loss falls as a power law with compute and data size."),
  b: doc("We study the translation quality of large language models on benchmarks.", "A second sentence that is long enough but mentions nothing relevant at all here."),
};
const states = { a: { status: "done" }, b: { status: "abstract_only" } };

test("temas: términos de contenido, glosario es→en y tope de 4", () => {
  const t = themesOf("¿Cómo funciona la atención y las leyes de escalado en modelos de lenguaje?");
  assert.equal(t.length, 4); assert.deepEqual(t.map((x) => x.term), ["atención", "leyes", "escalado", "modelos"]);
  assert.ok(themesOf("atención").some((x) => x.stems.includes("attent")));
  assert.deepEqual(themesOf("¿Y la de?"), []);
});
test("simulatePaper devuelve oraciones que existen y pasan la compuerta", () => {
  const themes = themesOf("attention scaling");
  const per = { a: simulatePaper({ themes, id: "a", doc: docs.a }), b: simulatePaper({ themes, id: "b", doc: docs.b }) };
  assert.equal(per.a.length, 2); assert.equal(per.b.length, 0);
  const r = buildPanorama(assemble(themes, per), docs, states);
  assert.equal(r.rejected.length, 0); assert.equal(r.claims[0].evidence.length, 1);
});
test("con fallas a propósito la compuerta rechaza las tres", () => {
  const themes = themesOf("attention scaling");
  const per = { a: simulatePaper({ themes, id: "a", doc: docs.a }) };
  const r = buildPanorama(assemble(themes, per, true, "a"), docs, states);
  assert.equal(r.rejected.length, 3);
  assert.deepEqual(r.claims[0].evidence.map((e) => e.paper), ["a"], "las buenas siguen ahí");
});
test("runSimulated avisa paper por paper", async () => {
  const got = []; await runSimulated({ question: "attention", ids: ["a", "b"], getDoc: async (i) => docs[i], onPaper: (id, d, s) => got.push([id, s.length]), latencyMs: 0 });
  assert.deepEqual(got.sort(), [["a", 1], ["b", 0]]);
});
