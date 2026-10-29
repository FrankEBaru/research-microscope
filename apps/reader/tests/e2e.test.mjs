// Pruebas de extremo a extremo (RRM-9): requieren `npm run data && npm run build` previos. Servidor estático propio.
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
const { chromium } = createRequire(import.meta.url)("playwright");

const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".svg": "image/svg+xml" };
let server, base, browser;
const PAPERS = ["1706.03762", "1810.04805", "2001.08361", "2203.15556", "2406.12907"];

before(async () => {
  assert.ok(existsSync(join(OUT, "index.html")), "falta out/: corre `npm run build`");
  server = http.createServer((req, res) => {
    let p = normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
    let f = join(OUT, p); if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
    if (!existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": MIME[extname(f)] || "application/octet-stream" }); createReadStream(f).pipe(res);
  });
  await new Promise((r) => server.listen(0, r)); base = `http://localhost:${server.address().port}/`;
  browser = await chromium.launch();
});
after(async () => { await browser?.close(); server?.close(); });

async function page(hash, w = 1280, h = 900) {
  const p = await browser.newPage({ viewport: { width: w, height: h } }); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); p.on("console", (m) => m.type() === "error" && p.errs.push(m.text()));
  await p.goto(base + hash); await p.addStyleTag({ content: "html{scroll-behavior:auto!important}" }); await p.evaluate(() => document.fonts.ready); return p;
}

test("área: mapa con 2 preguntas, lentes y minimapa; sin errores", async () => {
  const p = await page("#/"); await p.waitForSelector(".platina");
  assert.equal(await p.$$eval(".qtabs button", (b) => b.length), 2);
  assert.match(await p.$eval(".hud-step.on", (e) => e.textContent), /Área/);
  await p.click('.lenses button:has-text("×4")'); await p.waitForTimeout(800);
  assert.match(await p.$eval(".lenses .on", (e) => e.textContent), /×4/);
  await p.focus(".platina"); await p.keyboard.press("0"); await p.waitForTimeout(700);
  assert.match(await p.$eval(".hud-step.on", (e) => e.textContent), /Área/);
  assert.ok(await p.$(".mm-view"), "minimapa con rectángulo visible");
  assert.deepEqual(p.errs, []); await p.close();
});

test("mapa: rueda hasta el nivel Paper y la lente ofrece abrir el paper", async () => {
  const p = await page("#/"); await p.waitForSelector(".platina");
  const bb = await (await p.$(".platina")).boundingBox(); await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2 + 30);
  for (let i = 0; i < 9; i++) await p.mouse.wheel(0, -240);
  await p.waitForTimeout(400);
  assert.match(await p.$eval(".hud-step.on", (e) => e.textContent), /Paper|Cluster/);
  await p.click('.lenses button:has-text("×1")'); await p.waitForTimeout(700);
  await p.click(".node-dot >> nth=2"); await p.waitForTimeout(1000);
  assert.ok(await p.$(".ov"), "vista de un minuto");
  await p.click(".ov .primary"); await p.waitForSelector(".paper");
  assert.deepEqual(p.errs, []); await p.close();
});

test("Attention: ecuaciones, numeración, figuras, tablas e índice", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper"); await p.waitForTimeout(500);
  assert.equal(await p.$$eval(".math-fail", (n) => n.length), 0);
  assert.ok((await p.$$eval(".katex", (n) => n.length)) >= 138);
  assert.equal(await p.$$eval(".katex .tag", (n) => n.length), 3, "ecuaciones (1) (2) (3)");
  assert.equal(await p.$$eval(".fig", (n) => n.length), 5); assert.equal(await p.$$eval(".table-fig", (n) => n.length), 4);
  const st = await p.$$eval(".fig img", (is) => Promise.all(is.map((i) => fetch(i.src).then((r) => r.status))));
  assert.ok(st.length >= 8 && st.every((s) => s === 200), "imágenes disponibles");
  assert.ok((await p.$$eval(".toc a", (n) => n.length)) >= 20);
  assert.equal(await p.$$eval(".abstract", (n) => n.length), 1);
  assert.deepEqual(p.errs, []); await p.close();
});

test("hover: símbolo con definición del paper, cita y celda de tabla", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  // Se despacha el mouseover sobre el elemento (los manejadores delegan en el <article>): prueba la lógica del popover
  // sin depender de la temporización del puntero real, que en este arnés resultó intermitente (ver RRM-9).
  const over = async (el) => { await el.evaluate((e) => { e.scrollIntoView({ block: "center" }); e.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); }); await p.waitForTimeout(450); };
  await over(await p.$("#blk-b27 [data-sym=dk]"));
  assert.match(await p.$eval(".popover", (e) => e.textContent), /Definido en el paper/);
  await over(await p.$(".cite"));
  assert.ok((await p.$eval(".popover", (e) => e.textContent)).length > 30);
  await over(await p.$(".table-wrap td[data-pop]"));
  assert.match(await p.$eval(".popover", (e) => e.textContent), /Columna/);
  await p.close();
});

test("figura que acompaña: la referencia «Figura n» muestra la figura original", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  const el = await p.$('.xref[data-pop^="f|"]'); assert.ok(el, "hay referencias a figuras");
  await el.evaluate((e) => { e.scrollIntoView({ block: "center" }); e.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); }); await p.waitForTimeout(450);
  assert.ok(await p.$(".popover .pop-figs img"), "imagen en la vista previa");
  assert.match(await p.$eval(".popover", (e) => e.textContent), /Figura \d/);
  await p.close();
});

test("BibTeX: la ficha del paper trae el id de arXiv", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  const b = await p.$eval("button.bib", (e) => e.dataset.bibtex);
  assert.match(b, /@misc\{vaswani2017attention/); assert.match(b, /eprint = \{1706\.03762\}/); await p.close();
});

test("tensión: el deslizador muestra los factores de Kaplan y Chinchilla", async () => {
  const p = await page("#/q/escalado/c/desacuerdo"); await p.waitForSelector(".tslider");
  const rows = await p.$$eval(".trow em", (n) => n.map((e) => e.textContent));
  assert.equal(rows.length, 4); assert.ok(rows.some((t) => /tamaño del modelo ×5\.4/.test(t)), "×10: 10^0.73 ≈ 5.4");
  assert.ok(rows.some((t) => /×3\.2/.test(t))); await p.close();
});

test("instrumento √d_k: apuesta, comprobación y advertencia de σ²", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".instrument");
  await p.click('.bet-buttons button:has-text("Se duplica")');
  assert.match(await p.$eval(".bet-result", (e) => e.textContent), /Coincide con tu apuesta/);
  assert.match(await p.$eval(".stats .good", (e) => e.textContent), /coincide/);
  assert.equal(await p.$(".inst-warn"), null);
  await p.$eval('input[aria-label="sigma cuadrado"]', (e) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; s.call(e, "3"); e.dispatchEvent(new Event("input", { bubbles: true })); });
  await p.waitForTimeout(300);
  assert.ok(await p.$(".inst-warn"), "σ² ≠ 1 avisa que cambia el supuesto");
  assert.doesNotMatch(await p.$eval(".instrument", (e) => e.textContent), /verificad/i, "nunca «verificada»");
  await p.close();
});

test("esc sube de nivel", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  await p.keyboard.press("Escape"); await p.waitForSelector(".lvl2"); await p.keyboard.press("Escape"); await p.waitForSelector(".lvl1"); await p.close();
});

for (const id of PAPERS) {
  test(`paper ${id}: se abre sin errores, sin desborde y con pocas fórmulas crudas`, async () => {
    for (const [w, h] of [[1280, 900], [390, 800]]) {
      const p = await page(`#/q/atencion/c/modelo/p/${id}`, w, h); await p.waitForSelector(".paper"); await p.waitForTimeout(500);
      const r = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, fail: document.querySelectorAll(".math-fail").length, xr: [...document.querySelectorAll(".xref")].filter((e) => /^\[.*:.*\]$/.test(e.textContent)).length, xt: document.querySelectorAll(".xref").length }));
      assert.ok(r.sw <= w, `desborde horizontal ${r.sw} > ${w}`); assert.ok(r.fail <= 9, `fórmulas crudas: ${r.fail}`); assert.ok(r.xr <= Math.max(3, 0.08 * r.xt), `referencias sin resolver: ${r.xr} de ${r.xt}`);
      assert.deepEqual(p.errs, []); await p.close();
    }
  });
}

test("móvil: el mapa no desborda", async () => {
  const p = await page("#/", 390, 800); await p.waitForSelector(".platina");
  assert.ok((await p.evaluate(() => document.documentElement.scrollWidth)) <= 390); await p.close();
});

test("compañero: apagado por defecto, ofrece tras repeticiones, respeta el «no» y no guarda ni envía nada", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  const reqs = []; p.on("request", (r) => reqs.push([r.method(), r.url()]));
  assert.equal(await p.$(".companion"), null, "no aparece sin activarlo");
  assert.match(await p.$eval(".companion-toggle", (e) => e.textContent), /apagado/);
  await p.keyboard.press("c"); await p.waitForSelector(".companion");
  assert.match(await p.$eval(".companion-toggle", (e) => e.textContent), /activado/);
  const hover = (n) => p.$eval("#blk-b27 [data-sym=dk]", (e, k) => { e.scrollIntoView({ block: "center" }); for (let i = 0; i < k; i++) e.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); }, n);
  await hover(2); await p.waitForTimeout(300); assert.equal(await p.$(".c-bubble"), null, "2 pasadas no bastan");
  await hover(1); await p.waitForSelector(".c-bubble");
  assert.match(await p.$eval(".c-bubble", (e) => e.textContent), /No guardo ni envío/);
  await p.click(".c-no"); await p.waitForTimeout(200); assert.equal(await p.$(".c-bubble"), null);
  await hover(5); await p.waitForTimeout(300); assert.equal(await p.$(".c-bubble"), null, "no repite lo descartado");
  assert.equal(await p.evaluate(() => localStorage.length + sessionStorage.length + document.cookie.length), 0, "sin almacenamiento");
  assert.ok(reqs.every(([m, u]) => m === "GET" && u.startsWith(base)), "sin red externa ni escrituras");
  await p.close();
});

test("compañero: aceptar lleva a la definición; alternar personaje; se oculta con un clic", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper"); await p.keyboard.press("c");
  await p.$eval("#blk-b27 [data-sym=dk]", (e) => { for (let i = 0; i < 3; i++) e.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
  await p.waitForSelector(".c-bubble"); await p.click(".c-yes"); await p.waitForTimeout(400);
  assert.equal(await p.$(".c-bubble"), null); assert.ok(await p.$(".flash"), "el bloque de la definición se resalta");
  assert.ok(await p.$(".char-tardigrado")); await p.click(".c-swap"); assert.ok(await p.$(".char-diatomea")); await p.click(".c-swap"); assert.ok(await p.$(".char-volvox"));
  await p.click(".c-avatar"); await p.waitForTimeout(200); assert.equal(await p.$(".companion"), null);
  await p.close();
});

test("gráficas vivas: la Tabla 2 de Attention se ve como barras con los números del paper", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  const toggles = await p.$$(".tchart-toggle"); assert.ok(toggles.length >= 1, "al menos una tabla numérica es graficable");
  const fig = (await p.$$(".table-fig"))[1]; await fig.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await (await fig.$(".tchart-toggle")).click(); await p.waitForSelector(".tchart .tbar-row");
  assert.match(await p.$eval(".tchart .chips", (e) => e.textContent), /sin cambiar/);
  const rows = await p.$$eval(".tchart .tbar-row", (n) => n.map((e) => [e.dataset.rowLabel, e.querySelector(".tb-val").textContent.trim()]));
  assert.ok(rows.length >= 6); assert.ok(rows.some(([l, v]) => /ByteNet/.test(l) && v === "23.75"), "ByteNet 23.75, tal cual la tabla");
  await p.selectOption(".tchart select", "desc"); await p.waitForTimeout(300);
  const first = await p.$eval(".tchart .tbar-row .tb-val", (e) => parseFloat(e.textContent)); const all = await p.$$eval(".tchart .tb-val", (n) => n.map((e) => parseFloat(e.textContent)));
  assert.equal(first, Math.max(...all), "orden de mayor a menor");
  await p.click(".tchart .pills button >> nth=1"); await p.waitForTimeout(300); assert.ok((await p.$$(".tchart .tbar-row")).length >= 3);
  await (await p.$(".tchart .tbar-row")).hover(); await p.waitForTimeout(200); assert.ok(await p.$("tr.row-on"), "la fila de la tabla se resalta");
  assert.deepEqual(p.errs, []); await p.close();
});

test("compañero por permanencia: una ecuación quieta ofrece desglosar sus símbolos (curado, sin texto generado)", async () => {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } }); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); await p.addInitScript(() => { window.__RRM_DWELL_MS = 900; });
  await p.goto(base + "#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper"); await p.keyboard.press("c");
  await p.$eval(".eq.blk", (e) => e.scrollIntoView({ block: "center" }));
  await p.waitForSelector(".c-bubble", { timeout: 6000 });
  assert.match(await p.$eval(".c-bubble", (e) => e.textContent), /desgloso sus símbolos/);
  await p.click(".c-yes"); await p.waitForSelector(".breakdown");
  assert.match(await p.$eval(".breakdown .chips", (e) => e.textContent), /no texto generado/);
  assert.ok((await p.$$(".breakdown li")).length >= 3, "símbolos de la ecuación con su definición");
  assert.deepEqual(p.errs, []); await p.close();
});
