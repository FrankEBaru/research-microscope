delete process.env.NEXT_PUBLIC_BURST_URL;
delete process.env.NEXT_PUBLIC_READER_URL;
delete process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN;

import test from "node:test";
import assert from "node:assert/strict";
import { parseRecorded } from "../src/lib/backend.js";

test("parseRecorded keeps the exact question and drops blanks", () => {
  assert.deepEqual(
    parseRecorded({ queries: [" how does attention work ", "", "how does attention work", "neural radiance fields view synthesis"] }),
    ["how does attention work", "neural radiance fields view synthesis"],
  );
});

test("parseRecorded ignores a body without a list", () => {
  assert.deepEqual(parseRecorded(null), []);
  assert.deepEqual(parseRecorded({ ok: true }), []);
  assert.deepEqual(parseRecorded({ queries: "attention" }), []);
});
