// Offline shots for rrm-widget/0.4 (RRM-90). $0: no Meta, no Modal, no network.
// Mounts each widget with the real mountSandbox (sandboxed iframe, CSP, DPR 2) on a bare page that
// paints the 0.4 host blocks (hook, readouts, takeaway, controls), then screenshots every control state
// the gate samples. Usage: node scripts/liveart_shots04.mjs [outdir]   (needs Chromium + Playwright).
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const LIB = resolve(HERE, "../src/lib/liveart");
const OUT = resolve(process.argv[2] || resolve(HERE, "../../../evals/shots/liveart/v04"));
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>
:root{--sheet:#fff;--ink:#1d1a16;--ink-2:#5a5348;--ink-3:#6b6357;--rule:#e2d9c8;--rule-2:#cfc4b0;--page-2:#f6f1e7;--data-track:#efe8da;--data-raw:#8c8271;--hl-soft:rgba(255,225,77,.38);--accent:#0b6782;--viz-2:#b4501f;--viz-3:#7b4a8c;--viz-4:#7d6418}
body{margin:0;padding:18px 22px;width:578px;background:#f6f1e7;color:#1d1a16;font:14px/1.45 system-ui,sans-serif}
h2{font:600 21px/1.25 Georgia,serif;margin:0 0 10px}.reads{display:flex;gap:16px;flex-wrap:wrap;margin:0 0 8px;font-size:12.5px;color:#6b6357}.reads b{font-size:15px;color:#1d1a16;margin-left:6px}
#stage{position:relative;border-radius:12px;overflow:hidden;background:#fff;box-shadow:inset 0 0 0 1px #e2d9c8}
.take{margin:10px 0 6px;font-size:15px}.ctrls{font-size:12.5px;color:#5a5348}.note{color:#b4501f}</style></head><body>
<h2 id="hook"></h2><div class="reads" id="reads"></div><div id="stage"></div><p class="take" id="take"></p><p class="ctrls" id="ctrls"></p>
<script type="module">
import { mountSandbox } from "/lib/mount.js";
import { V04 } from "/lib/v04.js";
import { NOSLIDER } from "/lib/noslider.js";
import { ROUND } from "/lib/round.js";
const all = [...V04, ...NOSLIDER, ...ROUND].map((e) => e.widget);
window.mountOne = (id, patch) => new Promise((done) => {
  const w = all.find((x) => x.id === id);
  const st = {}; for (const c of w.controls) st[c.id] = c.value; Object.assign(st, patch || {});
  document.getElementById("hook").textContent = w.hook || w.title;
  const fmt = (r, v) => r.format === "pct" ? (v * 100).toFixed(r.digits ?? 0) + "%" : v.toFixed(r.digits ?? 2) + (r.unit || "");
  let shown = false;
  const api = mountSandbox(document.getElementById("stage"), w, {
    v04: true,
    onStatus: (s) => { if (!s.ok) { document.getElementById("take").innerHTML = '<span class="note">fallback: ' + s.reasons.join(" ") + "</span>"; done({ ok: false, reasons: s.reasons }); } },
    onFrame: (f, state) => {
      if (!f) { document.getElementById("ctrls").textContent = "0.3 widget (text in its own canvas)"; if (!shown) { shown = true; setTimeout(() => done({ ok: true, frame: null }), 60); } return; }
      const rs = (w.readouts || []).filter((r) => r.show !== false && r.id in f.readouts);
      document.getElementById("reads").innerHTML = rs.map((r) => r.label + "<b>" + fmt(r, f.readouts[r.id]) + "</b>").join("");
      const tpl = typeof w.takeaway === "string" ? w.takeaway : (w.takeaway || {})[f.say] || "";
      document.getElementById("take").textContent = tpl.replace(/\\{(\\w+)\\}/g, (_, k) => { const r = (w.readouts || []).find((q) => q.id === k); return r ? fmt(r, f.readouts[k]) : String(state[k]); });
      document.getElementById("ctrls").textContent = w.controls.map((c) => c.label + " " + (c.options ? (c.kind === "predict" ? (state[c.id] ? c.options[state[c.id] - 1] : "—") : c.options[state[c.id]]) : state[c.id])).join(" · ") + (f.cmarks.length ? "  |  " + f.cmarks.map((m) => m.control + ": " + m.label + " @ " + (+m.value).toFixed(2)).join(", ") : "");
      if (!shown) { shown = true; setTimeout(() => done({ ok: true, frame: f }), 60); }
    },
  });
  for (const [k, v] of Object.entries(patch || {})) api.set(k, v);
});
</script></body></html>`;

const server = createServer(async (req, res) => {
  try {
    if (req.url === "/" || req.url.startsWith("/?")) { res.writeHead(200, { "content-type": "text/html" }); return res.end(PAGE); }
    if (req.url.startsWith("/lib/")) {
      const body = await readFile(join(LIB, req.url.slice(5).split("?")[0]));
      res.writeHead(200, { "content-type": extname(req.url) === ".js" ? "text/javascript" : "text/plain" }); return res.end(body);
    }
    res.writeHead(404); res.end();
  } catch { res.writeHead(404); res.end(); }
});

function states(w) {
  const out = [["default", {}]];
  for (const c of w.controls) {
    const kind = c.kind || "slider";
    if (kind === "predict") { out.push([c.id + "=" + c.answer, Object.assign({ [c.id]: c.answer }, c.reveal || {})]); continue; }
    const vals = ["select", "toggle", "button", "pick"].includes(kind) ? Array.from({ length: Math.round((c.max - c.min) / c.step) + 1 }, (_, i) => c.min + i * c.step) : [c.min, c.max];
    for (const v of vals) if (v !== c.value) out.push([c.id + "=" + v, { [c.id]: v }]);
  }
  return out;
}

server.listen(0, async () => {
  const port = server.address().port;
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 622, height: 420 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const ids = process.env.IDS ? process.env.IDS.split(",") : ["adam-valley", "rope-shift", "kl-policy", "int8-outlier", "giou-gap", "double-descent", "lottery-keep", "resid-stream"];
  const log = [];
  for (const id of ids) {
    await page.goto(`http://localhost:${port}/`);
    const list = await page.evaluate(async (i) => {
      const all = [...(await import("/lib/v04.js")).V04, ...(await import("/lib/noslider.js")).NOSLIDER, ...(await import("/lib/round.js")).ROUND].map((e) => e.widget);
      return all.find((x) => x.id === i);
    }, id);
    if (!list) { log.push(`${id}: not found`); continue; }
    for (const [tag, patch] of states(list)) {
      await page.goto(`http://localhost:${port}/`);
      const r = await Promise.race([page.evaluate(([i, p]) => window.mountOne(i, p), [id, patch]), new Promise((ok) => setTimeout(() => ok({ ok: false, reasons: ["harness_timeout"] }), 8000))]);
      await page.waitForTimeout(150);
      const file = `${id}__${tag.replace(/[^a-z0-9=._-]/gi, "_")}.png`;
      await page.screenshot({ path: join(OUT, file), fullPage: true });
      const rep = r.frame ? r.frame.report : null;
      log.push(`${id} ${tag}: ${r.ok ? "ok" : "fallback " + r.reasons.join(",")}${r.ok && !rep ? " (0.3)" : ""}${rep ? ` labels=${rep.labels} dropped=${rep.dropped.length} free_text=${rep.free_text || 0}` : ""}`);
    }
  }
  await browser.close();
  server.close();
  await writeFile(join(OUT, "shots.log"), log.join("\n") + "\n" + (errors.length ? "page errors: " + errors.join(" | ") + "\n" : ""));
  console.log(log.join("\n"));
  if (errors.length) console.log("page errors:", errors.join(" | "));
});
