// The retry rule lives in Python. This checks the fixture against that code. No network.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const fixture = path.join(path.dirname(fileURLToPath(import.meta.url)), "crops_retry_cases.json");

test("a stored missing key does not stay skipped once the key exists", () => {
  const py = `
import json, sys
from rrm.reader.sam import key_blocks_crops, segmented_pages
cases = json.load(open(sys.argv[1], encoding="utf-8"))
out = []
for case in cases:
    out.append({
        "skip": key_blocks_crops(case["error"], case["key"]),
        "done": sorted(segmented_pages(case["index"], case["key"])),
    })
json.dump(out, sys.stdout)
`;
  const r = spawnSync("python3", ["-c", py, fixture], { cwd: root, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  const got = JSON.parse(r.stdout);
  const cases = JSON.parse(readFileSync(fixture, "utf8"));
  cases.forEach((c, i) => {
    assert.equal(got[i].skip, c.skip);
    assert.deepEqual(got[i].done, c.done);
  });
});
