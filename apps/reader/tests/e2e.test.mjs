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

test("Panorama: frases literales, convergencia contada, matriz y apertura del paper", async () => {
  const p = await page("#/"); await p.waitForSelector(".view-toggle");
  await p.click('.view-toggle button:has-text("Panorama")'); await p.waitForSelector(".pano-claim");
  assert.equal(await p.$$eval(".pano-claim", (n) => n.length), 3, "3 enunciados en la pregunta de atención");
  assert.match(await p.$eval(".pano-lead", (e) => e.textContent), /No es un veredicto/);
  const conv = await p.$$eval(".conv span", (n) => n.map((e) => e.textContent));
  assert.ok(conv.some((t) => /3 de 6/.test(t)) && conv.some((t) => /4 de 6/.test(t)) && conv.some((t) => /2 de 6/.test(t)), "k de n contados: " + conv.join(" | "));
  assert.match(conv[0], /Wilson 95%/);
  assert.equal(await p.$$eval(".matrix tbody tr", (n) => n.length), 6); assert.equal(await p.$$eval(".matrix .dot.yes", (n) => n.length), 9, "9 frases en la matriz (3+2+4)");
  assert.match(await p.$eval(".pano-claim .muted", (e) => e.textContent), /No es lo mismo que «no lo dice»/);
  assert.match(await p.$eval(".pano > .small", (e) => e.textContent), /simulado|simula/);
  await p.click(".pano-claim .evi .link >> nth=0"); await p.waitForSelector(".paper"); assert.deepEqual(p.errs, []); await p.close();
});

test("Panorama simulado: cualquier pregunta, llegada progresiva, predicción opcional y compuerta con fallas", async () => {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } }); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); await p.addInitScript(() => { window.__RRM_SIM_MS = 60; });
  await p.goto(base + "#/"); await p.waitForSelector(".view-toggle");
  await p.click('.view-toggle button:has-text("Panorama")'); await p.click('button:has-text("Cualquier pregunta")');
  assert.match(await p.$eval(".pano.sim .chips", (e) => e.textContent), /simulado/);
  await p.fill('input[aria-label="Pregunta para el Panorama"]', "attention scaling laws"); await p.click('button:has-text("Armar Panorama")');
  await p.waitForSelector(".predict", { timeout: 8000 });                                   // al terminar, pide predecir antes de ver
  assert.equal(await p.$$eval(".pano-claim .evi", (n) => n.length), 0, "con la predicción pendiente no se ve el resultado");
  assert.equal(await p.$eval(".sim-progress .coverage-bar div", (e) => e.style.width), "100%", "la barra termina llena");
  assert.match(await p.$eval(".predict-banner", (e) => e.textContent), /Antes de ver, predice/);
  await p.click(".predict .pills button >> nth=2"); await p.waitForSelector(".pano-claim .conv");
  assert.match(await p.$eval(".pano-claim .conv span", (e) => e.textContent), /tu predicción: 2/);
  await p.click(".predict-banner .link"); await p.waitForFunction(() => !document.querySelector(".predict"));   // «ver todo sin predecir»
  assert.ok((await p.$$eval(".pano-claim .evi li blockquote", (n) => n.length)) >= 2, "hay frases literales");
  const rej = Number(await p.$eval(".gate", (e) => e.dataset.rejected)); assert.equal(rej, 3, "las 3 fallas simuladas las rechaza la compuerta");
  assert.match(await p.$eval(".gate", (e) => e.textContent), /Compuerta/);
  assert.ok((await p.$$eval(".matrix .dot.yes", (n) => n.length)) >= 2);
  await p.click(".pano-claim .evi .link >> nth=0"); await p.waitForSelector(".paper"); assert.deepEqual(p.errs, []); await p.close();
});

test("gráfica: predecir antes de ver oculta las barras hasta elegir y luego revela el valor más alto", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  const fig = (await p.$$(".table-fig"))[1]; await fig.evaluate((e) => e.scrollIntoView({ block: "center" }));
  await (await fig.$(".tchart-toggle")).click(); await p.waitForSelector(".tchart .tbar-row");
  await p.check(".tpredict input"); assert.equal(await p.$$eval(".tbar-row.hid .tb-val", (n) => n.every((e) => e.textContent === "?")), true);
  await p.click(".tbar-row.hid >> nth=0"); await p.waitForSelector(".tp-result");
  assert.match(await p.$eval(".tp-result", (e) => e.textContent), /Acertaste|el más alto es/);
  assert.equal(await p.$$eval(".tbar-row.hid", (n) => n.length), 0, "al elegir se revelan los valores"); assert.deepEqual(p.errs, []); await p.close();
});

test("compañero que señala: al aceptar se desliza hasta la ecuación; sin objetivo se queda quieto", async () => {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } }); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); await p.addInitScript(() => { window.__RRM_DWELL_MS = 900; });
  await p.goto(base + "#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper"); await p.keyboard.press("c");
  assert.equal(await p.$eval(".companion", (e) => e.getAttribute("data-pointing")), null, "quieto por defecto");
  await p.$eval(".eq.blk", (e) => e.scrollIntoView({ block: "start" }));
  await p.waitForSelector(".c-bubble", { timeout: 6000 }); await p.click(".c-yes");
  await p.waitForSelector('.companion[data-pointing^="blk-"]'); assert.match(await p.$eval(".companion", (e) => e.style.transform), /translateY\(-?\d/);
  assert.deepEqual(p.errs, []); await p.close();
});

test("figura con zonas: cada parte de la arquitectura enlaza con la frase del paper que la explica", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".zone");
  assert.equal(await p.$$eval(".zone", (n) => n.length), 6);
  await p.$eval('[data-zone="dec-masked"]', (e) => e.scrollIntoView({ block: "center" })); await p.hover('[data-zone="dec-masked"]');
  assert.match(await p.$eval(".zone-card", (e) => e.textContent), /Atención enmascarada[\s\S]*prevent positions from attending to subsequent positions/);
  assert.match(await p.$eval(".zonefig .chips", (e) => e.textContent), /sin modelo/);
  await p.click(".zone-card .link"); await p.waitForTimeout(600);
  assert.ok(await p.$eval("#blk-b20", (e) => e.classList.contains("flash")), "va al párrafo del decodificador");
  assert.deepEqual(p.errs, []); await p.close();
});

async function simPage(hash) {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } }); p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message)); await p.addInitScript(() => { window.__RRM_SIM_MS = 30; });
  await p.goto(base + hash); await p.waitForSelector(".view-toggle");
  await p.click('.view-toggle button:has-text("Panorama")'); await p.click('button:has-text("Cualquier pregunta")'); return p;
}

test("Panorama simulado: la pregunta de la segunda área (escalado, en español) trae frases de los papers de escalado", async () => {
  const p = await simPage("#/q/escalado");
  assert.equal(await p.inputValue('input[aria-label="Pregunta para el Panorama"]'), "¿Cuánto cómputo y cuántos datos necesita un modelo de lenguaje?");
  await p.click('button:has-text("Armar Panorama")'); await p.waitForSelector(".predict", { timeout: 8000 });
  await p.uncheck('.sim-opts input >> nth=0');                                                   // apagar «predecir antes de ver»
  await p.waitForSelector(".pano-claim .evi li blockquote");
  assert.match(await p.$$eval(".pano-claim h3", (n) => n.map((e) => e.textContent).join(" ")), /cómputo|datos/i);
  const who = await p.$$eval(".pano-claim .who", (n) => n.map((e) => e.textContent.toLowerCase()));
  assert.ok(who.some((w) => /kaplan|hoffmann|brown|brandfonbrener|porian/.test(w)), "autores de escalado: " + who.join(","));
  assert.deepEqual(p.errs, []); await p.close();
});

test("Panorama simulado: sin fallas simuladas la compuerta no rechaza nada; con fallas rechaza 3; pregunta vacía no hace nada", async () => {
  const p = await simPage("#/");
  await p.fill('input[aria-label="Pregunta para el Panorama"]', "   "); await p.click('button:has-text("Armar Panorama")');
  assert.equal(await p.$(".sim-progress"), null, "una pregunta vacía no arma nada");
  await p.fill('input[aria-label="Pregunta para el Panorama"]', "self-attention recurrence"); await p.uncheck('.sim-opts input >> nth=1');
  await p.click('button:has-text("Armar Panorama")'); await p.waitForSelector(".gate", { timeout: 8000 });
  assert.equal(await p.$eval(".gate", (e) => e.dataset.rejected), "0"); assert.match(await p.$eval(".gate", (e) => e.textContent), /todas las selecciones existen literalmente/);
  await p.check('.sim-opts input >> nth=1'); await p.click('button:has-text("Volver a armar")'); await p.waitForFunction(() => document.querySelector(".gate")?.dataset.rejected === "3", null, { timeout: 8000 });
  await p.click(".gate summary"); assert.equal(await p.$$eval(".gate li", (n) => n.length), 3);
  assert.deepEqual(p.errs, []); await p.close();
});

test("Panorama simulado: «ver sin predecir» muestra el resultado sin marca de predicción; los términos genéricos no inflan el conteo", async () => {
  const p = await simPage("#/");
  await p.fill('input[aria-label="Pregunta para el Panorama"]', "language models"); await p.click('button:has-text("Armar Panorama")');
  await p.waitForSelector(".predict", { timeout: 8000 }); await p.click(".predict button.link >> nth=0"); await p.waitForSelector(".pano-claim .conv");
  assert.doesNotMatch(await p.$eval(".pano-claim .conv span", (e) => e.textContent), /tu predicción/);
  assert.equal(await p.$(".conv-track .guess"), null); await p.close();
});

test("figura con zonas en Kaplan: tres paneles (cómputo, dataset, parámetros) enlazan con la frase del paper", async () => {
  const p = await page("#/q/escalado/c/leyes/p/2001.08361"); await p.waitForSelector(".zone", { timeout: 8000 });
  assert.deepEqual(await p.$$eval(".zone", (n) => n.map((e) => e.dataset.zone)), ["compute", "dataset", "params"]);
  await p.$eval('[data-zone="compute"]', (e) => e.scrollIntoView({ block: "center" })); await p.hover('[data-zone="compute"]');
  assert.match(await p.$eval(".zone-card", (e) => e.textContent), /Cómputo[\s\S]*optimally allocated compute budget/); await p.close();
});

test("compañero: apagado por defecto, la tecla C lo prende y apaga, y sin él no hay panel ni rastro", async () => {
  const p = await page("#/q/atencion/c/modelo/p/1706.03762"); await p.waitForSelector(".paper");
  assert.equal(await p.$(".companion"), null); assert.match(await p.$eval(".companion-toggle", (e) => e.textContent), /apagado/);
  await p.keyboard.press("c"); await p.waitForSelector(".companion"); assert.equal(await p.$eval(".companion", (e) => e.getAttribute("data-pointing")), null, "quieto sin objetivo");
  await p.keyboard.press("c"); await p.waitForFunction(() => !document.querySelector(".companion")); await p.close();
});
