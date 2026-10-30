// E2E de navegador contra el backend REAL desplegado, con tiempos. NO corre en `npm test`.
// Gasta lo que gasten Modal y el reader, así que exige --approved (Franklin aprobó esta etapa y su presupuesto).
//
//   NEXT_PUBLIC_BURST_URL=... NEXT_PUBLIC_READER_URL=... NEXT_PUBLIC_RRM_DEMO_TOKEN=... npm run build
//   node scripts/e2e_real.mjs --approved --question "how does self-attention work"
//
// El build inlinea las URLs y el token en out/. El backend solo acepta los orígenes de rrm/demo_guard.py,
// por eso se sirve en el puerto 3100. El informe lleva tiempos y comprobaciones, sin URLs ni token; no lo commitees.
import http from "node:http";
import { createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");

const arg = (n, d) => { const i = process.argv.indexOf(n); return i < 0 ? d : process.argv[i + 1]; };
const flag = (n) => process.argv.includes(n);
const question = arg("--question", "");
const settleMs = Number(arg("--settle-timeout", 240)) * 1000;
const burstMs = Number(arg("--burst-timeout", 160)) * 1000;
const outFile = arg("--out", "e2e-real-report.json");
const shots = arg("--shots", "e2e-shots");
const PORT = 3100;
const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".woff2": "font/woff2", ".svg": "image/svg+xml" };

if (!question) { console.error("falta --question"); process.exit(2); }
if (!flag("--approved")) { console.error("rechazado: falta --approved (aprobación de Franklin para esta etapa y su presupuesto)"); process.exit(3); }
if (!existsSync(join(OUT, "index.html"))) { console.error("falta out/: corre `npm run build` con las tres variables NEXT_PUBLIC_*"); process.exit(2); }

const server = http.createServer((req, res) => {
  let f = join(OUT, normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^(\.\.[/\\])+/, ""));
  if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
  if (!existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": MIME[extname(f)] || "application/octet-stream" }); createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(PORT, "127.0.0.1", r));
mkdirSync(shots, { recursive: true });

const report = { question_chars: question.length, steps: {}, checks: {}, net: { failed: [], statuses: {} }, console_errors: [], stop: null };
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
page.on("pageerror", (e) => report.console_errors.push(e.message));
page.on("response", (r) => { const u = new URL(r.url()); if (u.hostname === "127.0.0.1") return; const k = `${r.request().method()} ${u.pathname} ${r.status()}`; report.net.statuses[k] = (report.net.statuses[k] || 0) + 1; });
page.on("requestfailed", (r) => report.net.failed.push(`${r.method()} ${new URL(r.url()).pathname} ${r.failure()?.errorText}`));

const t0 = Date.now();
const lap = (name) => { report.steps[name + "_s"] = Math.round((Date.now() - t0) / 100) / 10; };
async function step(name, fn) { try { await fn(); lap(name); return true; } catch (e) { report.stop = `${name}: ${String(e.message).split("\n")[0]}`; await page.screenshot({ path: join(shots, `fail-${name}.png`) }).catch(() => {}); return false; } }

try {
  await page.goto(`http://127.0.0.1:${PORT}/`);
  await page.fill('input[aria-label="Pregunta"]', question);
  await page.click('button:has-text("Buscar")');
  const ok =
    (await step("burst", () => page.waitForSelector(".live-cov", { timeout: burstMs }))) &&
    (await step("settled_and_panorama", () => page.waitForSelector(".sim .predict-banner, .sim [role=alert]", { timeout: settleMs }))) &&
    (await (async () => {
      report.checks.coverage = (await page.$eval(".live-cov", (e) => e.textContent)).replace(/\s+/g, " ").trim();
      report.checks.progress = (await page.$eval(".sim-progress", (e) => e.textContent)).replace(/\s+/g, " ").trim();
      report.checks.server_panorama = /en el servidor/.test(await page.$eval(".sim .chips", (e) => e.textContent));
      report.checks.panorama_fallback = Boolean(await page.$("[data-srv-fallback]"));
      return true;
    })()) &&
    (await step("reveal", async () => { await page.click(".predict-banner .link"); await page.waitForSelector(".pano-claim .conv", { timeout: 15000 }); }));
  if (ok) {
    report.checks.gate_rejected = Number(await page.$eval(".gate", (e) => e.dataset.rejected));
    report.checks.claims = (await page.$$(".pano-claim")).length;
    report.checks.matrix_dots = { yes: (await page.$$(".matrix .dot.yes")).length, no: (await page.$$(".matrix .dot.no")).length, failed: (await page.$$(".matrix .dot.na")).length };
    await page.screenshot({ path: join(shots, "panorama.png"), fullPage: true });
    if (report.checks.matrix_dots.yes > 0) {
      await step("open_paper", async () => { await page.click(".evi .link >> nth=0"); await page.waitForSelector(".paper", { timeout: 60000 }); });
      await page.waitForTimeout(1500);
      report.checks.figures = await page.$$eval(".paper figure img", (n) => ({ total: n.length, loaded: n.filter((i) => i.complete && i.naturalWidth > 0).length }));
      report.checks.tables = (await page.$$(".paper .table-fig")).length;
      await page.screenshot({ path: join(shots, "paper.png"), fullPage: false });
    }
  }
} finally {
  report.steps.total_s = Math.round((Date.now() - t0) / 100) / 10;
  if (report.console_errors.length) report.checks.console_errors = report.console_errors.length;
  writeFileSync(outFile, JSON.stringify(report, null, 2));
  await browser.close(); server.close();
}
console.log(JSON.stringify(report, null, 2));
console.log(`informe: ${outFile}; capturas: ${shots}/ (no commitear)\nAHORA apaga lo encendido: modal app stop rrm-reader; modal app stop rrm-burst; modal app list`);
const bad = report.stop || report.console_errors.length || report.checks.figures?.loaded < report.checks.figures?.total;
process.exit(bad ? 1 : 0);
