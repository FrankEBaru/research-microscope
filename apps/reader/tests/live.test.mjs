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
async function live({ statuses, burstStatus = 200, ids = [1, 2, 3, 4], burstBody, panorama, paper, init = {}, search = true, hash = "" }) {
  const p = await browser.newPage({ viewport: { width: 1280, height: 1000 } }); p.errs = []; p.posts = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); await p.addInitScript((o) => { window.__RRM_SIM_MS = 20; Object.assign(window, o); }, init);
  const papers = ids.map((i) => ({ corpusid: i, title: `Paper ${ARX[i]}`, year: 2020 })); let call = 0;
  await p.route("http://b.test/**", (r) => r.request().method() === "OPTIONS" ? r.fulfill({ status: 204, headers: H }) : burstStatus !== 200 ? r.fulfill({ status: burstStatus, headers: H, body: "x" }) : r.fulfill({ json: burstBody || { papers, edges: [] }, headers: H }));
  await p.route("http://r.test/**", (r) => {
    const u = new URL(r.request().url()); if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: H });
    if (u.pathname === "/status") { const rows = statuses[Math.min(call++, statuses.length - 1)]; return r.fulfill({ json: { papers: rows.map(([id, status, reason]) => ({ id, status, reason })) }, headers: H }); }
    if (u.pathname === "/panorama") { p.posts.push({ headers: r.request().headers(), body: r.request().postDataJSON() }); return panorama ? panorama(r) : r.fulfill({ status: 404, headers: H }); }
    if (u.pathname === "/paper" && paper) return paper(r, u);
    if (u.pathname === "/paper") { const doc = JSON.parse(readFileSync(join(PUB, `${ARX[u.searchParams.get("id")]}.json`))); return r.fulfill({ json: { status: "done", paper: doc, meta: {} }, headers: H }); }
    r.fulfill({ status: 404, headers: H });
  });
  await p.goto(base + hash); if (!search) return p;
  await p.fill('input[aria-label="Pregunta"]', "attention scaling laws"); await p.click('button:has-text("Buscar")');
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

const DONE4 = [[1, "done"], [2, "done"], [3, "abstract_only"], [4, "failed", "sin pdf ni e-print"]];
/** Una oración real y sin matemática de un paper local (lo que un backend devolvería desde blocks[].sents). */
function realSentence(arxiv) {
  const doc = JSON.parse(readFileSync(join(PUB, `${arxiv}.json`)));
  for (const b of doc.blocks) if (b.kind === "p") for (const s of b.sents || []) {
    const t = s.map((x) => (x.t === "text" ? x.v : null)); if (t.includes(null)) continue;
    const q = t.join("").replace(/\s+/g, " ").trim(); if (q.length >= 60 && q.length <= 300) return q;
  }
  throw new Error("sin oración");
}

test("en vivo: el Panorama usa POST /panorama del servidor (simulado) y la compuerta de la UI rechaza lo inventado", async () => {
  const real = realSentence("1706.03762");
  const claims = [{ id: "t0", statement: "Lo que dicen los papers sobre «attention»", selections: [{ paper: "1", quote: real }, { paper: "2", quote: "Esta frase no existe en ningún paper de la ráfaga y debe ser rechazada." }] }];
  const p = await live({ statuses: [DONE4], panorama: (r) => r.fulfill({ json: claims, headers: H }) });
  await p.waitForSelector(".sim .predict-banner", { timeout: 10000 });
  await p.click('input[type=checkbox] >> nth=1'); // apagar «simular fallas»: solo cuenta lo que mandó el servidor
  await p.click(".predict-banner .link");
  assert.match(await p.$eval(".sim .chips", (e) => e.textContent), /Selección simulada en el servidor/);
  assert.equal(await p.$("[data-srv-fallback]"), null);
  assert.equal(await p.$eval(".gate", (e) => e.dataset.rejected), "1");
  assert.equal((await p.$$(".matrix .dot.yes")).length, 1);
  assert.match(await p.$eval(".matrix thead", (e) => e.textContent), /attention/);
  assert.equal(p.posts.length, 1); assert.deepEqual(p.posts[0].body, { question: "attention scaling laws", ids: ["1", "2", "3"] });
  assert.equal(p.posts[0].headers["x-rrm-demo"], "test"); assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: si /panorama no está disponible cae al simulador del navegador y lo dice", async () => {
  const p = await live({ statuses: [DONE4], panorama: (r) => r.fulfill({ status: 501, json: { error: "meta" }, headers: H }) });
  await p.waitForSelector(".sim .predict", { timeout: 10000 });
  assert.match(await p.$eval("[data-srv-fallback]", (e) => e.textContent), /El servidor falló \(501\).*simulador del navegador; ambos son simulados/);
  assert.match(await p.$eval(".sim .chips", (e) => e.textContent), /Muse Spark simulado/); assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: errores de la ráfaga con mensaje claro (401 token, 429, ráfaga vacía)", async () => {
  for (const [burstStatus, re] of [[401, /rechazó el token de la demo/], [429, /demasiadas peticiones/], [503, /falló \(503\)/]]) {
    const p = await live({ statuses: [[]], burstStatus }); await p.waitForSelector(".fail-reason", { timeout: 8000 });
    assert.match(await p.$eval(".fail-reason", (e) => e.textContent), re); assert.ok(!(await p.content()).includes("b.test")); await p.close();
  }
  const p = await live({ statuses: [[]], burstBody: { papers: [], edges: [] } });
  await p.waitForSelector("text=no encontró papers", { timeout: 8000 }); assert.equal(await p.$(".sim"), null); await p.close();
});

test("en vivo: un paper lento no cuelga el Panorama; cuenta como no leído", async () => {
  const p = await live({ statuses: [[[1, "done"], [2, "done"], [3, "done"], [4, "done"]]], init: { __RRM_TIMEOUT_MS: 300 },
    paper: (r, u) => (u.searchParams.get("id") === "1" ? undefined : r.fulfill({ json: { status: "done", paper: JSON.parse(readFileSync(join(PUB, `${ARX[u.searchParams.get("id")]}.json`))), meta: {} }, headers: H })) });
  await p.waitForSelector(".sim .predict", { timeout: 15000 });
  assert.match(await p.$eval(".sim-progress", (e) => e.textContent), /3 de 4 papers leídos/); assert.equal(await p.$(".sim [role=alert]"), null);
  assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: abrir un paper que falla muestra el motivo y no se queda en «Cargando…» sin decir nada", async () => {
  const p = await live({ statuses: [[]], search: false, hash: "#/p/1", paper: (r) => r.fulfill({ status: 500, body: "x", headers: H }) });
  await p.waitForSelector(".fail-reason", { timeout: 10000 });
  assert.match(await p.$eval(".fail-reason", (e) => e.textContent), /falló \(500\)/); assert.deepEqual(p.errs, []); await p.close();
});

test("en vivo: papers que no terminan no bloquean para siempre; se puede armar con los ya leídos", async () => {
  const p = await live({ statuses: [[[1, "done"], [2, "done"], [3, "queued"], [4, "queued"]]], init: { __RRM_PATIENCE_MS: 300 } });
  await p.waitForSelector("text=Armar el Panorama con los ya leídos", { timeout: 8000 }); assert.equal(await p.$(".sim"), null);
  await p.click("text=Armar el Panorama con los ya leídos"); await p.waitForSelector(".sim .predict", { timeout: 10000 });
  assert.match(await p.$eval(".sim-progress", (e) => e.textContent), /2 de 4 papers leídos · 2 sin leer/); assert.deepEqual(p.errs, []); await p.close();
});
