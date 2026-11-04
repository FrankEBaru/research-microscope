import test from "node:test";
import assert from "node:assert/strict";

import { presentInlines } from "../src/lib/prose.js";
import { prepareTop } from "../src/lib/backend.js";
import { absenceText } from "../src/lib/falta.js";
import { notePhase, openPhase, openRoute, phaseRows, clockText } from "../src/lib/opening.js";
import { sortedRows } from "../src/lib/tablesort.js";

const maths = (s) => presentInlines([{ t: "text", v: s }]).filter((n) => n.t === "math").map((n) => n.v);
const texts = (s) => presentInlines([{ t: "text", v: s }]).filter((n) => n.t === "text").map((n) => n.v).join("");

test("loose TeX in an AI note: the formula is one math run and an unclosed \\mathrm{ is closed", () => {
  // Attention §3.3, as the note arrived (RRM-95 backlog 7).
  assert.deepEqual(maths("\\mathrm{FFN(x)=\\max(0, xW_1 + b_1) W_2 + b_2"), ["\\mathrm{FFN}(x)=\\max(0, xW_1 + b_1) W_2 + b_2"]);
  assert.deepEqual(maths("\\mathrm{FFN}(x)=\\max(0, xW_1 + b_1) W_2 + b_2"), ["\\mathrm{FFN}(x)=\\max(0, xW_1 + b_1) W_2 + b_2"]);
  const mid = "The FFN is \\mathrm{FFN(x)=\\max(0, xW_1 + b_1) W_2 + b_2 applied per position.";
  assert.equal(texts(mid), "The FFN is  applied per position.");
  assert.equal(texts(mid).includes("\\"), false);
  // Prose after a formula stays prose.
  assert.deepEqual(maths("we use \\mathrm{softmax}(QK^T) to weight, then sum."), ["\\mathrm{softmax}(QK^T)"]);
  assert.match(texts("we use \\mathrm{softmax}(QK^T) to weight, then sum."), /to weight, then sum\./);
});

test("prepareTop: 3 by default, env overrides within 1..10", () => {
  assert.equal(prepareTop(undefined), 3);
  assert.equal(prepareTop(""), 3);
  assert.equal(prepareTop("5"), 5);
  assert.equal(prepareTop("0"), 1);
  assert.equal(prepareTop("40"), 10);
  assert.equal(prepareTop("x"), 3);
});

test("absenceText says it plainly when there is no open version", () => {
  assert.equal(absenceText("no arXiv e-print and no open-access PDF", "Nature"), "Nature has no open version. Here is the abstract.");
  assert.equal(absenceText("no arXiv e-print and no open-access PDF", ""), "The publisher has no open version. Here is the abstract.");
  assert.equal(absenceText("ocr failed", "", true), "OCR failed. Here is the abstract.");
});

test("openPhase follows the backend stages", () => {
  assert.equal(openPhase({ status: "queued" }), "find");
  assert.equal(openPhase({ status: "parsing", stage: "resolve" }), "find");
  assert.equal(openPhase({ status: "parsing", stage: "stub" }), "download");
  assert.equal(openPhase({ status: "parsing", stage: "stub" }, { downloads: [{ source: "arxiv_eprint", ok: true }] }), "sections");
  assert.equal(openPhase({ status: "parsing", stage: "ocr" }), "ocr");
  assert.equal(openPhase({ status: "parsing", stage: "stub", ocr_invoked_at: 1 }), "ocr");
  assert.equal(openPhase({ status: "parsing", stage: "sections" }), "text");
  assert.equal(openPhase({ status: "abstract_only", stage: "done" }), "abstract");
  assert.equal(openPhase({ status: "failed" }), "failed");
  assert.equal(openRoute({ arxiv: "1601.06733" }), "arxiv");
  assert.equal(openRoute({ oa_pdf: "https://x/y.pdf" }), "pdf");
  assert.equal(openRoute({ stage: "stub" }, { title: "Human-level control" }), "none");
});

test("phaseRows: one row per phase with its own time; OCR only when it ran", () => {
  let log = notePhase([], "find", 0);
  log = notePhase(log, "find", 500);
  log = notePhase(log, "download", 2000);
  const rows = phaseRows(log, 12000, "arxiv");
  assert.deepEqual(rows.map((r) => [r.id, r.state]), [["find", "done"], ["download", "run"], ["sections", "wait"]]);
  assert.equal(rows[0].sec, 2);
  assert.equal(rows[1].sec, 10);
  assert.equal(rows[1].label, "Downloading from arXiv");
  const ocr = phaseRows(notePhase(log, "ocr", 20000), 50000, "pdf");
  assert.deepEqual(ocr.map((r) => r.id), ["find", "download", "sections", "ocr"]);
  assert.equal(ocr.find((r) => r.id === "ocr").sec, 30);
  assert.equal(ocr.find((r) => r.id === "sections").state, "done");
  assert.equal(clockText(9.6), "9 s");
  assert.equal(clockText(131), "2:11");
});

test("sortedRows: numeric columns sort as numbers, empty cells last, text naturally", () => {
  const model = {
    bodyRows: [0, 1, 2, 3],
    numericCols: [1],
    rows: [
      { raw: ["Transformer (big)", "28.4"], num: [null, 28.4] },
      { raw: ["ByteNet", "23.75"], num: [null, 23.75] },
      { raw: ["GNMT + RL", ""], num: [null, null] },
      { raw: ["ConvS2S", "25.16"], num: [null, 25.16] },
    ],
  };
  assert.deepEqual(sortedRows(model, null), [0, 1, 2, 3]);
  assert.deepEqual(sortedRows(model, { col: 1, dir: "asc" }), [1, 3, 0, 2]);
  assert.deepEqual(sortedRows(model, { col: 1, dir: "desc" }), [0, 3, 1, 2]);
  assert.deepEqual(sortedRows(model, { col: 0, dir: "asc" }), [1, 3, 2, 0]);
});
