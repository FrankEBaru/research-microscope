// Every emulated widget and the four gold draws must pass the 0.3 sandbox.
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { verifyWidget } from "../src/lib/liveart/verify.js";

const repo = fileURLToPath(new URL("../../..", import.meta.url));

test("gold and catalog draws pass the 0.3 sandbox", () => {
  const py = spawnSync("python3", ["-c", `
import json
from rrm.liveart.emulated import CATALOG
from rrm.liveart.offline import gold_widget
rows = []
for name in ("positional_encoding", "softmax_temperature", "attention_scale", "stddev"):
    rows.append({"widget": gold_widget(name), "claim": ""})
for row in CATALOG:
    rows.append({"widget": row["widget"], "claim": row["claim"]["text"]})
print(json.dumps(rows))
`], { cwd: repo, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  assert.equal(py.status, 0, py.stderr);
  const rows = JSON.parse(py.stdout);
  const bad = [];
  for (const row of rows) {
    const report = verifyWidget(row.widget, { claim: row.claim });
    if (!report.accept) bad.push(row.widget.id + " " + report.reasons.join(","));
  }
  assert.deepEqual(bad, []);
  assert.ok(rows.length >= 40);
});
