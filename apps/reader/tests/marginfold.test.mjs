import test from "node:test";
import assert from "node:assert/strict";
import { foldPlan } from "../src/lib/marginfold.js";

test("RRM-103b: a sparse margin is left alone", () => {
  const rows = [{ id: "g-b1-0", raw: 0, h: 300 }, { id: "g-b5-0", raw: 900, h: 400 }];
  const plan = foldPlan(rows);
  assert.deepEqual(plan.folded, []);
  assert.equal(plan.tops["g-b5-0"], 900);
});

test("RRM-103b: a dense stretch folds the tall notes pushing others, until every note is within the limit", () => {
  // Attention §3.2-like: tall notes 140 px apart.
  const rows = [
    { id: "g-b25-0", raw: 0, h: 800 }, { id: "g-b26-0", raw: 140, h: 720 }, { id: "fn-1", raw: 500, h: 200 },
    { id: "g-b28-0", raw: 520, h: 300 }, { id: "g-b28-1", raw: 520, h: 240 }, { id: "lv-dk", raw: 700, h: 215 }, { id: "g-b31-0", raw: 1000, h: 670 },
  ];
  const before = foldPlan(rows, { canFold: () => false });
  assert.ok(before.drift > 1500);
  const plan = foldPlan(rows, { canFold: (id) => id.startsWith("g-") });
  assert.ok(plan.drift < 300, `drift ${plan.drift}`); // best effort: footnotes and widget hooks never fold
  assert.ok(!plan.folded.includes("fn-1") && !plan.folded.includes("lv-dk"));
  // Never overlapping: each top is at least the previous bottom + gap.
  const order = [...rows].sort((a, b) => a.raw - b.raw);
  for (let i = 1; i < order.length; i++) {
    const p = order[i - 1], h = plan.folded.includes(p.id) ? 64 : p.h;
    assert.ok(plan.tops[order[i].id] >= plan.tops[p.id] + h + 12);
  }
});

test("RRM-103b: an opened note is never folded again", () => {
  const rows = [{ id: "g-a-0", raw: 0, h: 900 }, { id: "g-b-0", raw: 100, h: 300 }];
  const plan = foldPlan(rows, { canFold: (id) => id !== "g-a-0" });
  assert.ok(!plan.folded.includes("g-a-0"));
});

test("RRM-103b: a note that cannot be helped does not stop the folds below it", () => {
  const rows = [
    { id: "lv-dk", raw: 0, h: 600 }, { id: "fn-1", raw: 100, h: 200 },
    { id: "g-b48-0", raw: 3000, h: 420 }, { id: "g-b48-1", raw: 3000, h: 330 }, { id: "g-b48-2", raw: 3000, h: 250 },
  ];
  const plan = foldPlan(rows, { canFold: (id) => id.startsWith("g-") });
  assert.ok(plan.folded.includes("g-b48-0"));
  assert.ok(plan.tops["g-b48-2"] - 3000 <= 250);
});
