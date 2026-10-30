import test from "node:test";
import assert from "node:assert/strict";
import { bibtex, bibtexKey } from "../src/lib/bibtex.js";

const attn = { arxivId: "1706.03762", title: "Attention Is All You Need", authors: ["Ashish Vaswani", "Noam Shazeer"], date: "2017/06/12" };

test("clave: apellido + año + primera palabra significativa", () => {
  assert.equal(bibtexKey(attn), "vaswani2017attention");
  assert.equal(bibtexKey({ ...attn, title: "The Pile: An 800GB Dataset", authors: ["Leo Gao"] , date: "2020/12/31" }), "gao2020pile");
});
test("campos del arXiv y escape de caracteres especiales", () => {
  const b = bibtex({ ...attn, title: "R&D at 50% of $", authors: ["Zoë O'Neil", "A. B"] });
  assert.match(b, /^@misc\{/); assert.match(b, /eprint = \{1706\.03762\}/); assert.match(b, /archivePrefix = \{arXiv\}/);
  assert.match(b, /R\\&D at 50\\% of \\\$/); assert.match(b, /author = \{Zoë O'Neil and A\. B\}/);
});
test("sin fecha no inventa el año", () => {
  assert.doesNotMatch(bibtex({ ...attn, date: "" }), /year =/);
});
