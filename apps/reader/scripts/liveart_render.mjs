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
    const glyphs = [];
    const rects = [];
    const segs = [];
    let cx = 0;
    let cy = 0;
    for (const call of result.calls || []) {
      const args = call.a || [];
      if (call.m === "fillText" && args.length) {
        const text = String(args[0]);
        texts.push(text);
        glyphs.push({ t: text, x: Number(args[1]) || 0, y: Number(args[2]) || 0 });
      } else if (call.m === "fillRect" && args.length >= 4) {
        rects.push({ x: Number(args[0]) || 0, y: Number(args[1]) || 0, w: Number(args[2]) || 0, h: Number(args[3]) || 0 });
      } else if (call.m === "moveTo" && args.length >= 2) {
        cx = Number(args[0]) || 0;
        cy = Number(args[1]) || 0;
      } else if (call.m === "lineTo" && args.length >= 2) {
        const x = Number(args[0]) || 0;
        const y = Number(args[1]) || 0;
        segs.push({ x0: cx, y0: cy, x1: x, y1: y });
        cx = x;
        cy = y;
      }
    }
    out.push({ texts, glyphs, rects, segs });
  } catch (err) {
    out.push({ error: String((err && err.message) || err).slice(0, 180) });
  }
}
process.stdout.write(JSON.stringify(out));
