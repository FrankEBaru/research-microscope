import test from "node:test";
import assert from "node:assert/strict";
import { briefRef } from "../src/lib/cite.js";

test("a citation balloon is the first author and the title, side by side", () => {
  const dated = "Vaswani, Ashish, Shazeer, Noam, and Parmar, Niki (2017). Attention is all you need. Advances in Neural Information Processing Systems.";
  const hit = briefRef(dated);
  assert.equal(hit.who, "(Vaswani et al.)");
  assert.equal(hit.title, "Attention is all you need");
  assert.equal(hit.title.includes("Parmar"), false);

  const prose = "Ashish Vaswani, Noam Shazeer, Niki Parmar, and Illia Polosukhin. Attention is all you need. In Advances in Neural Information Processing Systems, 2017.";
  const brief = briefRef(prose);
  assert.equal(brief.who, "(Vaswani et al.)");
  assert.equal(brief.title, "Attention is all you need");
  assert.equal(brief.title.includes("Shazeer"), false);
  assert.equal(prose.length > brief.who.length + brief.title.length, true);

  assert.equal(briefRef("Jane Doe. A short title. Venue 2020.").who, "(Doe)");
  assert.equal(briefRef("").who, "");
});

test("RRM-103: ACL-style reference (Authors. Year. Title.) names the first author", () => {
  const a = briefRef("Andrew M Dai and Quoc V Le. 2015. Semi-supervised sequence learning. In Advances in neural information processing systems, pages 3079--3087.");
  assert.equal(a.who, "(Dai et al.)");
  assert.equal(a.title, "Semi-supervised sequence learning");
  const b = briefRef("Alan Akbik, Duncan Blythe, and Roland Vollgraf. 2018. Contextual string embeddings for sequence labeling. In Proceedings of COLING.");
  assert.equal(b.who, "(Akbik et al.)");
  assert.equal(b.title, "Contextual string embeddings for sequence labeling");
});
