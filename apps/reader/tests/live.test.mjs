// Modo en vivo con un backend SIMULADO en el navegador (requiere `npm run build:live`, que genera out-live/ con las URLs de prueba).
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");

const OUT = fileURLToPath(new URL("../out-live/", import.meta.url));
const PUB = fileURLToPath(new URL("../public/papers/", import.meta.url));
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".woff2": "font/woff2", ".svg": "image/svg+xml" };
const H = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };
const ARX = { 1: "1706.03762", 2: "2001.08361", 3: "2203.15556", 4: "1409.0473" };
let server, base, browser;

before(async () => {
  assert.ok(existsSync(join(OUT, "index.html")), "falta out-live/: corre `npm run build:live`");
  server = http.createServer((req, res) => {
    let p = normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^(\.\.[/\\])+/, ""); let f = join(OUT, p);
    if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
    if (!existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": MIME[extname(f)] || "application/octet-stream" }); createReadStream(f).pipe(res);
  });
  await new Promise((r) => server.listen(0, r)); base = `http://localhost:${server.address().port}/`; browser = await chromium.launch();
});
after(async () => { await browser?.close(); server?.close(); });

/** statuses: lista de respuestas sucesivas de /status (la última se repite); burstStatus: código de /burst. */
async function live({ statuses, burstStatus = 200, ids = [1, 2, 3, 4] }) {
  const p = await browser.newPage({ viewport: { width: 1280, height: 1000 } }); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); await p.addInitScript(() => { window.__RRM_SIM_MS = 20; });
  const papers = ids.map((i) => ({ corpusid: i, title: `Paper ${ARX[i]}`, year: 2020 })); let call = 0;
  await p.route("http://b.test/**", (r) => r.request().method() === "OPTIONS" ? r.fulfill({ status: 204, headers: H }) : burstStatus !== 200 ? r.fulfill({ status: burstStatus, headers: H, body: "x" }) : r.fulfill({ json: { papers, edges: [] }, headers: H }));
  await p.route("http://r.test/**", (r) => {
    const u = new URL(r.request().url()); if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: H });
    if (u.pathname === "/status") { const rows = statuses[Math.min(call++, statuses.length - 1)]; return r.fulfill({ json: { papers: rows.map(([id, status, reason]) => ({ id, status, reason })) }, headers: H }); }
    if (u.pathname === "/paper") { const doc = JSON.parse(readFileSync(join(PUB, `${ARX[u.searchParams.get("id")]}.json`))); return r.fulfill({ json: { status: "done", paper: doc, meta: {} }, headers: H }); }
    r.fulfill({ status: 404, headers: H });
  });
  await p.goto(base); await p.fill('input[aria-label="Pregunta"]', "attention scaling laws"); await p.click('button:has-text("Buscar")');
  return p;
}

test("en vivo: mezcla de estados; fallido con ×, abstract rotulado, predicción y apertura del paper", async () => {
  const p = await live({ statuses: [[[1, "done"], [2, "done"], [3, "abstract_only"], [4, "failed", "sin pdf"]]] });
  await p.waitForSelector(".sim .predict", { timeout: 10000 });
  assert.match(await p.$eval(".live-cov", (e) => e.textContent), /3 de 4 papers leídos/);
  assert.match(await p.$eval(".sim-progress", (e) => e.textContent), /3 de 4 papers leídos · 1 sin leer/);
  await p.click(".predict .pills button >> nth=1"); await p.waitForSelector(".pano-claim .conv");
  const rows = await p.$$eval(".matrix tbody tr", (n) => n.map((r) => r.innerText.replace(/\s+/g, " ")));
  assert.match(rows[2], /abstract/); assert.match(rows[3], /×/);
  await p.click(".evi .link >> nth=0"); await p.waitForSelector(".paper", { timeout: 8000 }); assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: llegada progresiva; el Panorama espera a que todos terminen y los en cola no cuentan", async () => {
  const p = await live({ statuses: [[[1, "queued"], [2, "queued"], [3, "queued"], [4, "queued"]], [[1, "done"], [2, "queued"], [3, "queued"], [4, "queued"]], [[1, "done"], [2, "done"], [3, "done"], [4, "done"]]] });
  await p.waitForSelector(".live-cov"); assert.equal(await p.$(".sim"), null, "mientras haya papers en cola no se arma el Panorama");
  await p.waitForSelector(".sim", { timeout: 12000 }); await p.waitForSelector(".sim .predict", { timeout: 10000 });
  assert.match(await p.$eval(".sim-progress", (e) => e.textContent), /4 de 4 papers leídos/); assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: si ningún paper se pudo leer, lo dice y no inventa conteos", async () => {
  const p = await live({ statuses: [[[1, "failed", "x"], [2, "failed", "x"], [3, "failed", "x"], [4, "failed", "x"]]] });
  await p.waitForSelector(".sim [role=alert]", { timeout: 10000 });
  assert.match(await p.$eval(".sim [role=alert]", (e) => e.textContent), /No se pudo leer ningún paper/);
  assert.equal(await p.$(".predict"), null, "no pide predecir sobre 0 papers"); assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: si la ráfaga falla muestra el error y se puede volver", async () => {
  const p = await live({ statuses: [[]], burstStatus: 500 });
  await p.waitForSelector(".fail-reason", { timeout: 8000 }); assert.equal(await p.$(".sim"), null);
  await p.click("text=volver a la ráfaga curada"); await p.waitForSelector(".platina"); await p.close();
});
