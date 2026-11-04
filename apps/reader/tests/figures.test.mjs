import test from "node:test";
import assert from "node:assert/strict";
import { figRows } from "../src/lib/figures.js";

test("panels share a row when the author put them side by side", () => {
  const two = figRows([{ src: "a" }, { src: "b" }]);
  assert.equal(two.length, 1);
  assert.equal(two[0].length, 2);
  const grid = figRows([{ src: "a", w: 0.48 }, { src: "b", w: 0.48 }, { src: "c", w: 0.48 }, { src: "d", w: 0.48 }]);
  assert.deepEqual(grid.map((row) => row.map((p) => p.src)), [["a", "b"], ["c", "d"]]);
  const four = figRows([{ src: "a" }, { src: "b" }, { src: "c" }, { src: "d" }]);
  assert.equal(four.length, 2);
  const full = figRows([{ src: "a", w: 1 }, { src: "b", w: 0.48 }, { src: "c", w: 0.48 }]);
  assert.deepEqual(full.map((row) => row.length), [1, 2]);
});
