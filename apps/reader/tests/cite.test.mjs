import test from "node:test";
import assert from "node:assert/strict";
import { briefRef } from "../src/lib/cite.js";

test("a citation balloon is the first author and the title", () => {
  const long = "Ashish Vaswani, Noam Shazeer, Niki Parmar, and Illia Polosukhin. Attention is all you need. In Advances in Neural Information Processing Systems, 2017.";
  const brief = briefRef(long);
  assert.equal(brief.who, "");
  const dated = "Vaswani, Ashish, Shazeer, Noam, and Parmar, Niki (2017). Attention is all you need. Advances in Neural Information Processing Systems.";
  const hit = briefRef(dated);
  assert.equal(hit.who, "Vaswani et al.");
  assert.match(hit.title, /^Attention is all you need/);
  assert.equal(hit.title.includes("Parmar"), false);
  assert.equal(briefRef("").who, "");
});
