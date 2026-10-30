import test from "node:test";
import assert from "node:assert/strict";
import { createTracker } from "../src/lib/companion.js";

const clock = () => { let t = 0; return { now: () => t, tick: (ms) => (t += ms) }; };

test("ofrece al llegar al umbral y solo una vez", () => {
  const c = clock(); const tr = createTracker({ threshold: 3, now: c.now });
  assert.equal(tr.track("sym:dk"), null); assert.equal(tr.track("sym:dk"), null);
  assert.equal(tr.track("sym:dk"), "sym:dk");
  for (let i = 0; i < 5; i++) assert.equal(tr.track("sym:dk"), null, "no repite lo ya ofrecido");
});

test("las señales viejas expiran (ventana)", () => {
  const c = clock(); const tr = createTracker({ threshold: 3, windowMs: 10_000, now: c.now });
  tr.track("a"); c.tick(6_000); tr.track("a"); c.tick(6_000);
  assert.equal(tr.track("a"), null, "la primera ya salió de la ventana");
});

test("enfriamiento: no ofrece dos cosas seguidas", () => {
  const c = clock(); const tr = createTracker({ threshold: 2, cooldownMs: 45_000, now: c.now });
  tr.track("a"); assert.equal(tr.track("a"), "a");
  tr.track("b"); assert.equal(tr.track("b"), null, "dentro del enfriamiento");
  c.tick(46_000);
  assert.equal(tr.track("b"), "b", "pasado el enfriamiento, las señales acumuladas ya bastan");
});

test("reset olvida conteos y ofertas", () => {
  const c = clock(); const tr = createTracker({ threshold: 2, now: c.now });
  tr.track("a"); assert.equal(tr.track("a"), "a"); tr.reset(); c.tick(60_000);
  tr.track("a"); assert.equal(tr.track("a"), "a", "tras reset se puede volver a ofrecer");
});

test("no persiste nada fuera de memoria", () => {
  const src = createTracker.toString();
  assert.doesNotMatch(src, /localStorage|sessionStorage|fetch\(|indexedDB|document\.cookie/);
});

test("offer (permanencia): una vez por clave y respeta el enfriamiento compartido", () => {
  const c = clock(); const tr = createTracker({ threshold: 3, cooldownMs: 45_000, now: c.now });
  assert.equal(tr.offer("dwell:b5"), "dwell:b5"); assert.equal(tr.offer("dwell:b5"), null, "no repite");
  assert.equal(tr.offer("dwell:b9"), null, "dentro del enfriamiento");
  c.tick(46_000); assert.equal(tr.offer("dwell:b9"), "dwell:b9");
  tr.track("sym:x"); tr.track("sym:x"); assert.equal(tr.track("sym:x"), null, "el enfriamiento también frena a las repeticiones");
});
