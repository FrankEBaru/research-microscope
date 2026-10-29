// Pruebas por propiedad derivadas de Attention Is All You Need §3.2.1 (nota 1):
// "q·k has mean 0 and variance d_k" bajo componentes independientes, media 0, varianza 1.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { simulate, meanVar, scaled, theoreticalVar, meanMaxWeight } from "../src/lib/instrument.js";

const close = (a, b, rel) => Math.abs(a - b) <= rel * Math.abs(b);

test("P1: Var(q·k) ≈ d_k (σ²=1)", () => {
  for (const dk of [16, 64, 256]) {
    const { variance } = meanVar(simulate({ dk, n: 20000, seed: 11 }));
    assert.ok(close(variance, dk, 0.05), `dk=${dk} var=${variance}`);
  }
});

test("P2: la media de q·k ≈ 0", () => {
  const { mean } = meanVar(simulate({ dk: 64, n: 20000, seed: 5 }));
  assert.ok(Math.abs(mean) < 0.2, `mean=${mean}`);
});

test("P3: Var(q·k/√d_k) ≈ 1 (σ²=1)", () => {
  for (const dk of [16, 64, 256]) {
    const d = simulate({ dk, n: 20000, seed: 3 });
    const { variance } = meanVar(scaled(d, dk));
    assert.ok(close(variance, 1, 0.05), `dk=${dk} var=${variance}`);
  }
});

test("P4: con σ²=2 la varianza escalada es σ⁴=4, no 1 (el supuesto de varianza 1 importa)", () => {
  const d = simulate({ dk: 64, sigma2: 2, n: 20000, seed: 9 });
  const { variance } = meanVar(scaled(d, 64));
  assert.ok(close(variance, theoreticalVar(1, 2), 0.06), `var=${variance}`);
  assert.ok(Math.abs(variance - 1) > 1.5);
});

test("P5: sin escala el softmax es más puntiagudo que con escala (d_k=256)", () => {
  const d = simulate({ dk: 256, n: 6000, seed: 2 });
  assert.ok(meanMaxWeight(d) > meanMaxWeight(scaled(d, 256)) + 0.1);
});

test("P6: coincide con la reimplementación independiente en numpy (≤7% en varianzas)", () => {
  const ref = JSON.parse(readFileSync(new URL("./numpy_reference.json", import.meta.url)));
  for (const r of ref) {
    const d = simulate({ dk: r.dk, sigma2: r.sigma2, n: 20000, seed: 21 });
    const { variance } = meanVar(d);
    const sv = meanVar(scaled(d, r.dk)).variance;
    assert.ok(close(variance, r.var, 0.07), `var dk=${r.dk} σ²=${r.sigma2}: js=${variance} np=${r.var}`);
    assert.ok(close(sv, r.scaledVar, 0.07), `scaledVar dk=${r.dk} σ²=${r.sigma2}: js=${sv} np=${r.scaledVar}`);
  }
});
