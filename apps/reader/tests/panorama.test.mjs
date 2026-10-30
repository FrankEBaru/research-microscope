import test from "node:test";
import assert from "node:assert/strict";
import { wilson, convergence } from "../src/lib/convergence.js";
import { validateSelections, proposeClaims, museMode } from "../src/lib/muse.js";

test("Wilson: conocidos y ancho con n pequeño", () => {
  const w = wilson(3, 6); assert.ok(Math.abs(w.p - 0.5) < 1e-9); assert.ok(Math.abs(w.lo - 0.188) < 0.01 && Math.abs(w.hi - 0.812) < 0.01);
  assert.deepEqual(wilson(0, 0), { p: 0, lo: 0, hi: 1 });
  const big = wilson(300, 600); assert.ok(big.hi - big.lo < 0.09, "con n grande el intervalo se estrecha");
  assert.ok(Math.abs(wilson(6, 6).hi - 1) < 1e-9 && Math.abs(wilson(0, 6).lo) < 1e-9, "los extremos llegan a 0 y 1");
});
test("convergencia cuenta papers distintos, no frases", () => {
  const c = convergence({ evidence: [{ paper: "a" }, { paper: "a" }, { paper: "b" }] }, 6); assert.equal(c.k, 2); assert.equal(c.n, 6);
});
const T = (v) => ({ t: "text", v });
const papers = { x: { blocks: [{ id: "b0", kind: "p", abs: true, inlines: [T("Scaling helps a lot. We train big models.")] }, { id: "b1", kind: "p", inlines: [T("We train big models on text. Scaling helps a lot.")] }, { id: "b2", kind: "p", inlines: [T("Unique sentence here")] }, { id: "b3", kind: "p", inlines: [T("dup phrase in two places")] }, { id: "b4", kind: "p", inlines: [T("another dup phrase in two places")] }] } };
test("compuerta: acepta frases exactas y rechaza inventadas o ambiguas", () => {
  const r = validateSelections(papers, [{ paper: "x", quote: "Unique sentence here" }, { paper: "x", quote: "Scaling helps a lot." }, { paper: "x", quote: "We train big models" }, { paper: "x", quote: "dup phrase in two places" }, { paper: "x", quote: "Texto que el modelo inventó" }, { paper: "y", quote: "x" }]);
  assert.deepEqual(r.ok.map((o) => o.blockId), ["b2", "b0", "b0"], "la frase del abstract gana si reaparece");
  assert.deepEqual(r.rejected.map((o) => o.reason), ["aparece 2 veces", "la frase no existe en el paper", "paper desconocido"], "ambigua sin abstract, inventada y paper desconocido se rechazan");
});
test("modo simulado y sin llamadas de red", () => {
  assert.equal(museMode(), "simulado"); assert.equal(proposeClaims({ panorama: { q: { a: 1 } } }, "q").a, 1); assert.equal(proposeClaims({}, "q"), null);
  assert.doesNotMatch(validateSelections.toString() + proposeClaims.toString(), /fetch\(|XMLHttpRequest|WebSocket/);
});
