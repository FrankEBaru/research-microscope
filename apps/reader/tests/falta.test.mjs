import test from "node:test";
import assert from "node:assert/strict";

import { faltaText } from "../src/lib/falta.js";

test("Falta no culpa al paper cuando esta corrida no usó OCR", () => {
  assert.equal(faltaText("pdf; ocr skipped: cap"), "this run did not use OCR");
  assert.equal(faltaText("Esta corrida no usó OCR."), "this run did not use OCR");
  assert.equal(faltaText("no arXiv e-print and no open-access PDF"), "no arXiv e-print and no open PDF");
  assert.equal(faltaText("el texto no está"), "el texto no está");
  assert.equal(faltaText(""), "the paper could not be drawn");
});