import test from "node:test";
import assert from "node:assert/strict";

import { citingIndex, citingPassages } from "../src/lib/figrefs.js";

const xref = { "fig:block": "Figure 1", "fig:block_deeper": "Figure 2", "tab:variations": "Table 3" };

test("fig:block no empareja fig:block_deeper", () => {
  const blocks = [
    { id: "f1", kind: "fig", label: "fig:block" },
    { id: "p-deep", kind: "p", inlines: [{ t: "text", v: "Deeper " }, { t: "ref", label: "fig:block_deeper", target: "f2" }] },
    { id: "f2", kind: "fig", label: "fig:block_deeper" },
    { id: "p-hit", kind: "p", inlines: [{ t: "text", v: "Shallow " }, { t: "ref", label: "fig:block", target: "f1" }] },
    { id: "p-mislabeled", kind: "p", inlines: [{ t: "ref", label: "fig:block", target: "f2" }] },
  ];
  const hit = citingPassages(blocks, "f1", "fig:block", 2, xref);
  assert.deepEqual(hit.top.map((r) => r.block), ["p-hit"]);
  assert.equal(hit.rest.length, 0);
  assert.equal(hit.top[0].text, "Shallow Figure 1");
  const named = citingPassages([
    { id: "f1", kind: "fig", label: "fig:block" },
    { id: "p-named", kind: "p", inlines: [{ t: "text", v: "shown in Figure~" }, { t: "ref", label: "fig:block", target: "f1" }] },
  ], "f1", "fig:block", 2, xref);
  assert.equal(named.top[0].text, "shown in Figure 1");
  const deep = citingPassages(blocks, "f2", "fig:block_deeper", 2, xref);
  assert.deepEqual(deep.top.map((r) => r.block).sort(), ["p-deep", "p-mislabeled"]);
});

test("sin target acepta el label exacto y nada que lo contenga", () => {
  const blocks = [
    { id: "p1", kind: "p", sents: [[{ t: "text", v: "See " }, { t: "ref", label: "fig:block" }]] },
    { id: "p2", kind: "p", sents: [[{ t: "ref", label: "fig:block_deeper" }]] },
    { id: "p3", kind: "p", sents: [[{ t: "ref", label: "fig:block", target: "other" }]] },
  ];
  const hit = citingPassages(blocks, "f1", "fig:block", 2, xref);
  assert.deepEqual(hit.top.map((r) => r.block), ["p1"]);
  assert.equal(hit.top[0].text, "See Figure 1");
  assert.deepEqual(citingPassages(blocks, "f1", "", 2, xref), { top: [], rest: [] });
});

test("una tabla sin label se cita por target", () => {
  const blocks = [
    { id: "p1", kind: "p", sents: [[{ t: "text", v: "Results in " }, { t: "ref", label: "tab:variations", target: "b83" }, { t: "text", v: "." }]] },
    { id: "b83", kind: "table" },
  ];
  const hit = citingPassages(blocks, "b83", "", 2, xref);
  assert.equal(hit.top.length, 1);
  assert.equal(hit.top[0].text, "Results in Table 3.");
  assert.equal(hit.top[0].sent, 0);
  assert.deepEqual(citingIndex(blocks, xref)["b83"].top, hit.top);
});

test("cero citas", () => {
  const blocks = [
    { id: "p", kind: "p", inlines: [{ t: "text", v: "Nothing here." }] },
    { id: "f", kind: "fig", label: "fig:block" },
  ];
  assert.deepEqual(citingPassages(blocks, "f", "fig:block"), { top: [], rest: [] });
  assert.deepEqual(citingIndex(blocks, xref), {});
});

test("seis citas quedan 2 y 4, por menciones y cercanía", () => {
  const ref = { t: "ref", label: "fig:block", target: "fig" };
  const para = (id, n, word) => ({
    id,
    kind: "p",
    sents: [
      [{ t: "text", v: `${word} ` }, ref],
      ...Array.from({ length: Math.max(0, n - 1) }, () => [ref]),
    ],
  });
  const blocks = [
    para("a", 1, "a"),
    para("b", 5, "b"),
    para("c", 1, "c"),
    { id: "fig", kind: "fig", label: "fig:block" },
    para("d", 1, "d"),
    para("e", 1, "e"),
    para("f", 1, "f"),
  ];
  const hit = citingPassages(blocks, "fig", "fig:block", 2, xref);
  assert.deepEqual(hit.top.map((r) => r.block), ["b", "c"]);
  assert.deepEqual(hit.rest.map((r) => r.block), ["d", "e", "a", "f"]);
  assert.equal(hit.top[0].text, "b Figure 1");
  assert.equal(citingIndex(blocks, xref).fig.rest.length, 4);
});

test("Figure, Table, Eq y Section no repiten la palabra del \\ref", () => {
  const blocks = [
    { id: "p-fig", kind: "p", sents: [[{ t: "text", v: "Figure " }, { t: "ref", label: "fig:block", target: "f1" }, { t: "text", v: " shows the block." }]] },
    { id: "f1", kind: "fig", label: "fig:block" },
    { id: "p-tab", kind: "p", sents: [[{ t: "text", v: "Table " }, { t: "ref", label: "tab:variations", target: "t1" }, { t: "text", v: " lists them." }]] },
    { id: "t1", kind: "table", label: "tab:variations" },
    { id: "p-sec", kind: "p", sents: [[{ t: "text", v: "Section " }, { t: "ref", label: "sec:pe", target: "s1" }]] },
    { id: "s1", kind: "h", label: "sec:pe" },
    { id: "p-eq", kind: "p", sents: [[{ t: "text", v: "Equation " }, { t: "ref", label: "eq:pe", number: 8 }, { t: "text", v: " and Eq. " }, { t: "ref", label: "eq:pe2", target: "e2" }]] },
  ];
  const names = { ...xref, "sec:pe": "Section 5", "eq:pe": "Equation 8", "eq:pe2": "Eq. 9" };
  assert.equal(citingPassages(blocks, "f1", "fig:block", 2, names).top[0].text, "Figure 1 shows the block.");
  assert.equal(citingPassages(blocks, "t1", "tab:variations", 2, names).top[0].text, "Table 3 lists them.");
  // Section is not a figure or table, so citingPassages ignores it. The quote text is what plainSent builds for a hit.
  const sec = citingPassages(
    [{ id: "p", kind: "p", sents: [[{ t: "text", v: "Section " }, { t: "ref", label: "fig:block", target: "f1" }]] }, { id: "f1", kind: "fig", label: "fig:block" }],
    "f1", "fig:block", 2, { "fig:block": "Section 5" },
  );
  assert.equal(sec.top[0].text, "Section 5");
  const eq = citingPassages(blocks, "f1", "fig:block", 2, names);
  assert.equal(eq.top[0].text, "Figure 1 shows the block.");
  const eqQuote = citingPassages(
    [{ id: "p", kind: "p", sents: [[{ t: "text", v: "Equation " }, { t: "ref", label: "fig:block", target: "f1" }, { t: "text", v: " and Eq. " }, { t: "ref", label: "fig:block", target: "f1" }]] }, { id: "f1", kind: "fig", label: "fig:block" }],
    "f1", "fig:block", 2, { "fig:block": "Equation 8" },
  );
  assert.equal(eqQuote.top[0].text, "Equation 8 and Eq. 8");
});

test("un ref dentro de em o span cuenta, y el recorte usa puntos suspensivos", () => {
  const long = "x".repeat(240);
  const blocks = [
    {
      id: "p",
      kind: "p",
      sents: [
        [{ t: "text", v: "Skip this sentence." }],
        [{ t: "span", c: [{ t: "em", c: [{ t: "text", v: `${long} ` }, { t: "ref", label: "fig:block", target: "f1" }] }] }],
      ],
    },
    { id: "f1", kind: "fig", label: "fig:block" },
  ];
  const hit = citingPassages(blocks, "f1", "fig:block", 2, xref);
  assert.equal(hit.top[0].sent, 1);
  assert.equal(hit.top[0].text.length, 200);
  assert.ok(hit.top[0].text.endsWith("…"));
  assert.equal(citingIndex(blocks, xref).f1.top[0].sent, 1);
});
