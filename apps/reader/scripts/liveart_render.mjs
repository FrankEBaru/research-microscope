// Headless fillText capture for the quality gate. No Chrome, no Meta.
import { readFileSync } from "node:fs";

import { runDraw } from "../src/lib/liveart/run.js";
import { isV04, v04On } from "../src/lib/liveart/spec.js";

const job = JSON.parse(readFileSync(0, "utf8"));
const cap = job.cap || 200000;
// 0.4 (RRM-90): with RRM_LIVEART_V04 on and a 0.4 widget, the draw gets ui and the frame reports the
// host text. The gate reads texts, so readouts, takeaway and control marks come back as plain lines.
const widget = job.widget && isV04(job.widget) && (job.v04 || v04On(process.env)) ? job.widget : null;
function fmt(r, v) {
  if (r && r.format === "pct") return (v * 100).toFixed(r.digits == null ? 0 : r.digits) + "%";
  return v.toFixed(r && r.digits != null ? r.digits : 2) + (r && r.unit ? r.unit : "");
}
function hostLines(frame) {
  if (!frame || !widget) return [];
  const lines = [];
  for (const r of widget.readouts || []) if (r.id in (frame.readouts || {})) lines.push(r.label + " = " + fmt(r, frame.readouts[r.id]));
  const take = typeof widget.takeaway === "string" ? widget.takeaway : (widget.takeaway || {})[frame.say];
  if (take) lines.push(take.replace(/\{(\w+)\}/g, (_, k) => { const r = (widget.readouts || []).find((q) => q.id === k); return r && k in frame.readouts ? fmt(r, frame.readouts[k]) : "{" + k + "}"; }));
  for (const m of frame.cmarks || []) if (m.label) lines.push(String(m.label).replace(/\{v\}/g, (+m.value).toFixed(2)) + " " + (+m.value).toFixed(2));
  return lines;
}
const out = [];
for (const state of job.states || []) {
  try {
    const result = runDraw(job.draw || "", state, 0, cap, widget ? { v04: true, widget } : undefined);
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
        let gx = Number(args[1]) || 0;
        let gy = Number(args[2]) || 0;
        if (widget) {
          // Normalize to left / alphabetic, the box the gate assumes (7 px per glyph, ascent 12).
          const w = text.length * 7;
          if (call.align === "right" || call.align === "end") gx -= w;
          else if (call.align === "center") gx -= w / 2;
          if (call.base === "middle") gy += 4.5;
          else if (call.base === "top") gy += 11;
        }
        glyphs.push({ t: text, x: gx, y: gy });
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
    const host = hostLines(result.frame);
    out.push(widget ? { texts: texts.concat(host), glyphs, rects, segs, host, frame: result.frame } : { texts, glyphs, rects, segs });
  } catch (err) {
    out.push({ error: String((err && err.message) || err).slice(0, 180) });
  }
}
process.stdout.write(JSON.stringify(out));
