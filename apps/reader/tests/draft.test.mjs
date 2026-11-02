import test from "node:test";
import assert from "node:assert/strict";
import { draftKey, legacyKey, loadDraft, migrateLegacy, saveDraft } from "../src/lib/draft.js";

function memory() {
  const map = new Map();
  return {
    get length() { return map.size; },
    key(i) { return [...map.keys()][i] ?? null; },
    getItem(k) { return map.has(k) ? map.get(k) : null; },
    setItem(k, v) { map.set(k, String(v)); },
    removeItem(k) { map.delete(k); },
  };
}

test("clave por paper y sección", () => {
  assert.equal(draftKey("7", "intro"), "rrm.draft.v1:7:intro");
  assert.equal(draftKey("7", ""), "rrm.draft.v1:7:_");
  assert.equal(draftKey("7", null), "rrm.draft.v1:7:_");
  assert.equal(legacyKey("7"), "rrm-ask:7");
  assert.equal(legacyKey(""), "");
});

test("guardar y leer; JSON roto o storage que truena no tiran", () => {
  const box = memory();
  const snap = { text: "hola", result: { parts: {} }, err: "", store: { ready: 1, total: 2 }, at: 5 };
  assert.equal(saveDraft(box, draftKey("7", "s"), snap), true);
  assert.deepEqual(loadDraft(box, draftKey("7", "s")), snap);
  assert.equal(loadDraft(box, "no-existe"), null);
  box.setItem("malo", "{");
  assert.equal(loadDraft(box, "malo"), null);
  const broken = {
    getItem() { throw new Error("no"); },
    setItem() { throw new Error("no"); },
  };
  assert.equal(loadDraft(broken, "k"), null);
  assert.equal(saveDraft(broken, "k", snap), false);
  assert.equal(saveDraft(null, "k", snap), false);
});

test("migra rrm-ask y no pisa la clave nueva", () => {
  const box = memory();
  saveDraft(box, legacyKey("7"), { text: "viejo", result: { n: 1 }, err: "F-ASK", store: null });
  const moved = migrateLegacy(box, "7", "metodo");
  assert.equal(moved.text, "viejo");
  assert.equal(moved.err, "F-ASK");
  assert.equal(moved.result.n, 1);
  assert.equal(typeof moved.at, "number");
  assert.equal(loadDraft(box, legacyKey("7")), null);
  assert.equal(loadDraft(box, draftKey("7", "metodo")).text, "viejo");
  saveDraft(box, legacyKey("7"), { text: "no pisa", at: 1 });
  saveDraft(box, draftKey("7", "metodo"), { text: "nuevo", at: 2 });
  assert.equal(migrateLegacy(box, "7", "metodo").text, "nuevo");
  assert.equal(loadDraft(box, legacyKey("7")).text, "no pisa");
});
