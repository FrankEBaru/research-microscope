import test from "node:test";
import assert from "node:assert/strict";

import { UNDEFINED, equationHover, symbolHover, tableHover } from "../src/lib/hover.js";
import { hasConclusion, scanIds } from "../src/lib/scan.js";

const blocks = [
  { id: "h", kind: "h", level: 1, inlines: [{ t: "text", v: "Intro" }] },
  { id: "p1", kind: "p", sents: [
    [{ t: "text", v: "Early " }, { t: "math", v: "\\alpha" }, { t: "text", v: " is defined here." }],
    [{ t: "text", v: "Later we reuse the symbol." }],
  ] },
  { id: "p2", kind: "p", sents: [[{ t: "text", v: "No definition in this sentence." }]] },
  { id: "eq", kind: "eq", tex: "E=mc^2" },
  { id: "p3", kind: "p", sents: [[{ t: "text", v: "Table 1 shows the split." }]] },
  { id: "tab", kind: "table", label: "tab:main", caption: [{ t: "text", v: "Results on the benchmark." }] },
  { id: "hc", kind: "h", level: 1, inlines: [{ t: "text", v: "Conclusion" }] },
  { id: "pc", kind: "p", abs: false, sents: [[{ t: "text", v: "We conclude." }]] },
  { id: "abs", kind: "p", abs: true, inlines: [{ t: "text", v: "Abstract sentence." }] },
];

test("el símbolo usa la frase anterior que lo contiene, o dice que el paper no lo define", () => {
  const early = symbolHover(blocks, "\\alpha", { block: "p1", index: 0 });
  assert.match(early.text, /defined here/);
  const later = symbolHover(blocks, "\\alpha", { block: "p2", index: 0 });
  assert.match(later.text, /defined here/);
  const missing = symbolHover(blocks, "\\gamma", { block: "p2", index: 0 });
  assert.equal(missing.text, UNDEFINED);
});

test("la ecuación muestra las frases de donde sale y la tabla el pie, sin un número nuevo", () => {
  const eq = equationHover(blocks, "eq");
  assert.deepEqual(eq.texts, ["No definition in this sentence."]);
  const table = tableHover(blocks, "tab");
  assert.equal(table.caption, "Results on the benchmark.");
  assert.equal(table.sentence, "Table 1 shows the split.");
  assert.equal("value" in table, false);
  const bare = tableHover([{ id: "t", kind: "table", caption: [{ t: "text", v: "Solo el pie." }] }], "t");
  assert.equal(bare.caption, "Solo el pie.");
  assert.equal(bare.sentence, "");
});

test("el scan deja abstract, figuras, tablas y la conclusión", () => {
  const ids = scanIds(blocks);
  assert.equal(ids.has("abs"), true);
  assert.equal(ids.has("tab"), true);
  assert.equal(ids.has("hc"), true);
  assert.equal(ids.has("pc"), true);
  assert.equal(ids.has("p1"), false);
  assert.equal(hasConclusion(blocks), true);
  assert.equal(hasConclusion([{ kind: "h", inlines: [{ t: "text", v: "Intro" }] }]), false);
  assert.equal(hasConclusion([{ kind: "h", inlines: [{ t: "text", v: "5 Discussion" }] }]), true);
  assert.equal(hasConclusion([{ kind: "h", inlines: [{ t: "text", v: "Concluding remarks" }] }]), true);
  assert.equal(hasConclusion([{ kind: "h", inlines: [{ t: "text", v: "Summary" }] }]), true);
});
