import test from "node:test";
import assert from "node:assert/strict";
import { arxivAbs, isGated, rightsLine } from "../src/lib/rights.js";

const open = {
  label: "CC BY 4.0", url: "http://creativecommons.org/licenses/by/4.0/",
  cls: "open", sa: false, gated: false, arxiv: "2302.13971", version: "v1",
};
const sa = { ...open, label: "CC BY-SA 4.0", cls: "open", sa: true, arxiv: "0000.00002", version: "" };
const closed = {
  label: "arXiv license", url: "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
  cls: "closed", sa: false, gated: true, arxiv: "1706.03762", version: "v7",
};

test("rightsLine names the license, the version, and the annotation", () => {
  assert.deepEqual(rightsLine(open), [
    "CC BY 4.0",
    "arXiv:2302.13971v1",
    "Annotated by Research Reading Microscope (modified)",
  ]);
  assert.ok(rightsLine(sa).includes("Our annotations: CC BY-SA 4.0"));
  assert.equal(rightsLine(sa)[1], "arXiv:0000.00002");
  assert.deepEqual(rightsLine(closed), [
    "arXiv license",
    "arXiv:1706.03762v7",
    "Abstract and our explanations only",
  ]);
  assert.deepEqual(rightsLine(null), []);
});

test("isGated follows the backend flag", () => {
  assert.equal(isGated({ rights: closed }, null), true);
  assert.equal(isGated({ rights: open }, { gated: false }), false);
  assert.equal(isGated({}, { gated: true }), true);
  assert.equal(isGated({}, {}), false);
  assert.equal(arxivAbs(closed), "https://arxiv.org/abs/1706.03762v7");
  assert.equal(arxivAbs({}), "");
});
