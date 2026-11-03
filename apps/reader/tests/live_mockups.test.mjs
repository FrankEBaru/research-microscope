import test from "node:test";
import assert from "node:assert/strict";

import { TOPICS, bannedIn, shapeErrors } from "../src/live/contract.js";
import { FEWSHOTS, WIDGETS } from "../src/live/catalog.js";
import { digest, inkCount, makeRaster } from "../src/live/raster.js";
import { REJECTS } from "../src/live/rejects.js";
import { createSession } from "../src/live/run.js";

function play(widget) {
  let ctx = null;
  const session = createSession(widget, (w, h) => {
    ctx = makeRaster(w, h);
    return ctx;
  });
  session.frame(0);
  const before = digest(ctx);
  const ink = inkCount(ctx);
  const spec = session.specs[0];
  session.set(spec.id, spec.min);
  session.frame(0);
  const atMin = digest(ctx);
  session.set(spec.id, spec.max);
  session.frame(0);
  const atMax = digest(ctx);
  return { ink, changed: before !== atMin || atMin !== atMax || before !== atMax };
}

test("raster sees a filled rect and a circle", () => {
  const ctx = makeRaster(40, 30);
  assert.equal(inkCount(ctx), 0);
  ctx.fillStyle = "#0b6782";
  ctx.beginPath();
  ctx.arc(12, 12, 5, 0, Math.PI * 2);
  ctx.fill();
  assert.ok(inkCount(ctx) > 10);
  const mid = digest(ctx);
  ctx.fillRect(20, 18, 8, 6);
  assert.notEqual(digest(ctx), mid);
});

test("every contract widget draws and answers its first control", () => {
  const ids = new Set();
  const topics = new Set();
  assert.ok(WIDGETS.length >= 100, "catalog " + WIDGETS.length);
  for (const item of WIDGETS) {
    assert.equal(ids.has(item.id), false, item.id);
    ids.add(item.id);
    topics.add(item.topic);
    assert.deepEqual(shapeErrors(item), [], item.id + " " + shapeErrors(item).join(","));
    assert.deepEqual(bannedIn(item.draw), []);
    const got = play(item);
    assert.ok(got.ink > 30, item.id + " ink " + got.ink);
    assert.equal(got.changed, true, item.id);
  }
  for (const name of Object.keys(TOPICS)) assert.equal(topics.has(name), true, name);
});

test("few-shots are one primary draw per topic, gold ids first", () => {
  assert.deepEqual(FEWSHOTS.map((item) => item.id).slice(0, 4), [
    "positional-encoding",
    "softmax-temperature",
    "attention-scale",
    "stddev",
  ]);
  assert.equal(new Set(FEWSHOTS.map((item) => item.topic)).size, Object.keys(TOPICS).length);
  for (const shot of FEWSHOTS) {
    assert.equal(WIDGETS.some((item) => item.id === shot.id && item.draw === shot.draw), true);
  }
});

test("reject fixtures trip the contract and are not in the catalog", () => {
  const ids = new Set(WIDGETS.map((item) => item.id));
  for (const item of REJECTS) {
    assert.equal(ids.has(item.id), false);
    const shape = shapeErrors(item.widget);
    const banned = bannedIn(item.widget.draw || "");
    const got = shape.concat(banned);
    for (const name of item.names) assert.equal(got.includes(name), true, item.id + " missing " + name + " in " + got.join(","));
    assert.throws(() => createSession(item.widget, () => makeRaster(80, 80)));
  }
});
