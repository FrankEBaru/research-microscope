import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { parseNumber, analyze, bars } from "../src/lib/tablechart.js";

const T = (v) => ({ t: "text", v }); const M = (v) => ({ t: "math", v, display: false });
test("parseNumber: decimales, miles, porcentaje, científica y basura", () => {
  assert.equal(parseNumber("23.75"), 23.75); assert.equal(parseNumber("1,024"), 1024); assert.equal(parseNumber("85%"), 85);
  assert.equal(parseNumber("$2.3\\cdot10^{19}$"), 2.3e19); assert.equal(parseNumber("$1.0\\cdot 10^{20}$"), 1e20); assert.equal(parseNumber("$3.3\\times10^{-4}$"), 3.3e-4);
  for (const bad of ["", "n/a", "ByteNet", "24.6/38.1", "100K", "2-3"]) assert.equal(parseNumber(bad), null, bad);
});
test("analyze: cabecera multicolumna se expande por colspan y se ignora «2-3»", () => {
  const t = { head: [[[T("Model")], [T("BLEU")], [], [T("Cost")]]], hspan: [[1, 2, 1, 2]],
    body: [[[T("2-3")], [T("EN-DE")], [T("EN-FR")], [], [T("EN-DE")], [T("EN-FR")]],
           [[T("A")], [T("23.75")], [], [], [], []], [[T("B")], [T("24.6")], [T("39.92")], [], [M("2.3\\cdot10^{19}")], [M("1.4\\cdot10^{20}")]], [[T("C")], [T("26.4")], [T("41")], [], [M("7.7\\cdot10^{19}")], [M("1.2\\cdot10^{21}")]],
           [[T("D")], [T("27.3")], [T("38.1")], [], [M("3.3\\cdot10^{18}")], [M("2.3\\cdot10^{19}")]]],
    bspan: Array.from({ length: 5 }, () => [1, 1, 1, 1, 1, 1]) };
  const m = analyze(t);
  assert.equal(m.headers[1], "BLEU · EN-DE"); assert.equal(m.headers[2], "BLEU · EN-FR");
  assert.equal(m.headers[4], "Cost · EN-DE"); assert.equal(m.headers[5], "Cost · EN-FR");
  assert.deepEqual(m.rows.map((r) => r.label), ["A", "B", "C", "D"]);
  assert.deepEqual(m.numericCols, [1, 2, 4, 5]);
  assert.equal(m.rows[1].num[4], 2.3e19);
});
test("bars: orden, valores nulos fuera, y la escala log no cambia el orden", () => {
  const m = { rows: [{ label: "a", raw: ["a", "10"], num: [null, 10] }, { label: "b", raw: ["b", "1000"], num: [null, 1000] }, { label: "c", raw: ["c", ""], num: [null, null] }, { label: "d", raw: ["d", "100"], num: [null, 100] }] };
  const lin = bars(m, 1, { sort: "desc" }); assert.deepEqual(lin.map((x) => x.label), ["b", "d", "a"]); assert.equal(lin[0].frac, 1);
  const lg = bars(m, 1, { sort: "desc", log: true }); assert.deepEqual(lg.map((x) => x.label), ["b", "d", "a"]); assert.ok(lg[2].frac > 0 && lg[2].frac < lin[1].frac + 1);
  assert.ok(lg[1].frac > lin[1].frac, "en log, 100 pesa más que en lineal");
});
test("Attention, Tabla 2 real: las barras de BLEU EN-DE coinciden con los números del paper", { skip: !existsSync(new URL("../public/papers/1706.03762.json", import.meta.url)) }, () => {
  const d = JSON.parse(readFileSync(new URL("../public/papers/1706.03762.json", import.meta.url)));
  const m = analyze(d.blocks.filter((b) => b.kind === "table")[1]);
  const c = m.headers.findIndex((h) => /BLEU · EN-DE/.test(h)); assert.ok(c > 0, "columna BLEU EN-DE");
  const v = Object.fromEntries(bars(m, c).map((b) => [b.label, b.value]));
  assert.equal(v["ByteNet"], 23.75); assert.ok(Object.keys(v).length >= 6);
});
