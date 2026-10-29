import test from "node:test";
import assert from "node:assert/strict";
import { modelGrowth, tokenGrowth, computeGrowth } from "../src/lib/scaling.js";

test("×10 de cómputo: Kaplan (0.73) y Chinchilla (0.50)", () => {
  assert.ok(Math.abs(modelGrowth(10, 0.73) - 5.37) < 0.01);
  assert.ok(Math.abs(modelGrowth(10, 0.5) - 3.162) < 0.001);
  assert.ok(Math.abs(tokenGrowth(10, 0.73) - 1.862) < 0.001);
  assert.ok(Math.abs(tokenGrowth(10, 0.5) - 3.162) < 0.001);
});
test("N·D crece como el cómputo (FLOPs ≈ 6ND)", () => {
  for (const a of [0.5, 0.73]) for (const x of [1, 10, 123]) assert.ok(Math.abs(computeGrowth(x, a) - x) < 1e-9);
});
test("Chinchilla escala tamaño y datos por igual", () => {
  for (const x of [2, 10, 1000]) assert.ok(Math.abs(modelGrowth(x, 0.5) - tokenGrowth(x, 0.5)) < 1e-9);
});
