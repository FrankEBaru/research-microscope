// Headless fillText capture for the quality gate. No Chrome, no Meta.
import { readFileSync } from "node:fs";

import { runDraw } from "../src/lib/liveart/run.js";

const job = JSON.parse(readFileSync(0, "utf8"));
const cap = job.cap || 200000;
const out = [];
for (const state of job.states || []) {
  try {
    const result = runDraw(job.draw || "", state, 0, cap);
    const texts = [];
    for (const call of result.calls || []) {
      if (call.m === "fillText" && call.a && call.a.length) texts.push(String(call.a[0]));
    }
    out.push({ texts });
  } catch (err) {
    out.push({ error: String((err && err.message) || err).slice(0, 180) });
  }
}
process.stdout.write(JSON.stringify(out));
