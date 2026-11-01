import test from "node:test";
import assert from "node:assert/strict";

import { faltaText } from "../src/lib/falta.js";

test("Falta no culpa al paper cuando esta corrida no usó OCR", () => {
  assert.equal(faltaText("pdf; ocr skipped: cap"), "esta corrida no usó OCR");
  assert.equal(faltaText("Esta corrida no usó OCR."), "esta corrida no usó OCR");
  assert.equal(faltaText("no arXiv e-print and no open-access PDF"), "no hay e-print de arXiv ni un PDF abierto");
  assert.equal(faltaText("el texto no está"), "el texto no está");
  assert.equal(faltaText(""), "no se pudo dibujar el paper");
});