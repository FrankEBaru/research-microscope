import test from "node:test";
import assert from "node:assert/strict";

import { compareOf, matrixOf, sqrtDenominator } from "../src/lib/artifacts.js";

const ATTN = String.raw`\mathrm{Attention}(Q, K, V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V`;
const PE = String.raw`PE_{(pos,2i)} = sin(pos / 10000^{2i/d_{\text{model}}}) \\ PE_{(pos,2i+1)} = cos(pos / 10000^{2i/d_{\text{model}}})`;

test("la matriz de PE usa d = 64 ilustrativo y la fila 0 cambia más", () => {
  const drawn = matrixOf(PE);
  assert.ok(drawn);
  assert.equal(drawn.legend, "d = 64, ilustrativo");
  assert.match(drawn.freq, /Cada fila es una dimensión/);
  assert.match(drawn.freq, /i = 0\) cambia más rápido/);
  assert.equal(drawn.rows.length, 16);
  assert.equal(drawn.rows[0].cells.length, 32);
  const speed = (row) => {
    let sum = 0;
    for (let i = 0; i < 31; i++) sum += Math.abs(row.cells[i + 1] - row.cells[i]);
    return sum;
  };
  assert.ok(speed(drawn.rows[0]) > speed(drawn.rows[drawn.rows.length - 1]));
  assert.equal(matrixOf(String.raw`\sin(x)+\cos(x)`), null);
});

test("softmax sin la raíz pica más, y un tex que no calza no dibuja", () => {
  assert.equal(sqrtDenominator(ATTN), String.raw`\sqrt{d_k}`);
  const drawn = compareOf(ATTN);
  assert.ok(drawn);
  assert.equal(drawn.legend, "d_k = 64, ilustrativo");
  assert.equal(drawn.withLabel, "dividiendo entre √d_k");
  assert.equal(drawn.withoutLabel, "sin dividir");
  assert.match(drawn.look, /casi todo el peso cae en una sola clave/);
  assert.equal(drawn.with.length, 8);
  assert.ok(Math.max(...drawn.without) > Math.max(...drawn.with));
  assert.equal(compareOf(String.raw`\frac{Q}{\sqrt{n}}`), null);
  assert.equal(compareOf(String.raw`\frac{a}{\sqrt{b}`), null);
});
