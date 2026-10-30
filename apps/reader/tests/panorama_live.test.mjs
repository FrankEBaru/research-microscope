import test from "node:test";
import assert from "node:assert/strict";
import { readState, coverage, buildPanorama } from "../src/lib/panorama.js";
import { convergence } from "../src/lib/convergence.js";

const T = (v) => ({ t: "text", v });
const doc = (...ss) => ({ blocks: ss.map((s, i) => ({ id: `b${i}`, kind: "p", inlines: [T(s)] })) });
const docs = { 1: doc("Scaling helps a lot."), 2: doc("Only an abstract here."), 3: doc("Never read") };
const states = { 1: { status: "done" }, 2: { status: "abstract_only" }, 3: { status: "failed" }, 4: { status: "queued" } };

test("estados: done/abstract_only/failed y el resto pendiente", () => {
  assert.deepEqual(["done", "abstract_only", "failed", "queued", "missing", undefined].map(readState), ["full", "abstract", "failed", "pending", "pending", "pending"]);
});
test("cobertura: n son los leídos; fallidos y pendientes no entran al denominador", () => {
  const c = coverage(["1", "2", "3", "4", "5"], states);
  assert.deepEqual(c, { full: 1, abstract: 1, failed: 1, pending: 2, total: 5, n: 2 });
  assert.equal(convergence({ evidence: [{ paper: "1" }] }, c.n).n, 2);
});
test("buildPanorama: valida contra el paper y descarta papers no leídos", () => {
  const r = buildPanorama([{ id: "c1", statement: "S", selections: [
    { paper: "1", quote: "Scaling helps a lot." }, { paper: "2", quote: "Texto inventado" }, { paper: "3", quote: "Never read" }, { paper: "4", quote: "x" }] }], docs, states);
  assert.deepEqual(r.claims[0].evidence, [{ paper: "1", quote: "Scaling helps a lot.", anchor: { blockId: "b0" } }]);
  assert.equal(r.rejected.length, 3);
  assert.equal(r.rejected.filter((x) => x.paper === "2")[0].reason, "la frase no existe en el paper");
  assert.ok(r.rejected.filter((x) => x.paper === "3" || x.paper === "4").every((x) => x.reason.startsWith("paper no leído")));
});
test("sin llamadas de red", () => {
  assert.doesNotMatch(buildPanorama.toString() + coverage.toString(), /fetch\(|XMLHttpRequest/);
});
