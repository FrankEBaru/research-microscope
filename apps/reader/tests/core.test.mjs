import test from "node:test";
import assert from "node:assert/strict";

import { coreMode, featuresMode } from "../src/lib/features.js";
import { createDevLog } from "../src/lib/devlog.js";
import { normalizeQuestion, phaseOf, recallQuestion, rememberQuestion, QUESTION_CACHE_LIMIT } from "../src/lib/qcache.js";

function memory() {
  const box = new Map();
  return {
    getItem: (k) => (box.has(k) ? box.get(k) : null),
    setItem: (k, v) => { box.set(k, String(v)); },
  };
}

test("el default del navegador es core y all lo restaura", () => {
  assert.equal(featuresMode(undefined), "core");
  assert.equal(featuresMode(""), "core");
  assert.equal(featuresMode("all"), "all");
  assert.equal(coreMode("core"), true);
  assert.equal(coreMode("all"), false);
});

test("la pregunta normalizada coincide con el servidor", () => {
  assert.equal(normalizeQuestion("  Cómo   Hacen "), "cómo hacen");
  assert.equal(normalizeQuestion("Attention Is All You Need"), "attention is all you need");
  assert.equal(normalizeQuestion("  ¿Cuánto   cómputo? "), "¿cuánto cómputo?");
});

test("la caché guarda 10 y una pregunta ya vista no vuelve a calentar", () => {
  const store = memory();
  for (let i = 0; i < 12; i++) rememberQuestion(store, `pregunta ${i}`, { result: { n: i } });
  assert.equal(recallQuestion(store, "pregunta 0"), null);
  assert.equal(recallQuestion(store, "pregunta 1"), null);
  assert.equal(recallQuestion(store, "pregunta 2").payload.result.n, 2);
  const last = recallQuestion(store, "  Pregunta   11 ");
  assert.equal(last.payload.result.n, 11);
  const raw = JSON.parse(store.getItem("rrm.questions.v1"));
  assert.equal(raw.length, QUESTION_CACHE_LIMIT);
  const throwing = {
    getItem: () => "[]",
    setItem: () => { throw new Error("quota"); },
  };
  let spilled = "";
  rememberQuestion(throwing, "otra", { result: { ok: true } }, (json) => { spilled = json; });
  assert.match(spilled, /otra/);
});

test("fases del paper y el registro de desarrollo", () => {
  assert.equal(phaseOf(undefined).label, "encontrado");
  assert.equal(phaseOf("missing").id, "encontrado");
  assert.equal(phaseOf("queued").label, "preparando");
  assert.equal(phaseOf("parsing").label, "preparando");
  assert.equal(phaseOf("done").label, "listo");
  assert.equal(phaseOf("abstract_only").label, "listo");
  assert.equal(phaseOf("failed").label, "falló");
  let clock = 10;
  const log = createDevLog(() => clock);
  const id = log.begin("ráfaga", "attention");
  clock = 40;
  assert.match(log.line(log.steps[0]), /ráfaga — 30 ms — waiting — attention/);
  log.finish(id, "ok", "caché del navegador");
  assert.match(log.line(log.steps[0]), /ráfaga — 30 ms — ok — caché del navegador/);
  const bad = log.begin("figura", "plot.png");
  clock = 55;
  log.finish(bad, "error", "no cargó");
  assert.match(log.line(log.steps[1]), /figura — 15 ms — error — no cargó/);
});
