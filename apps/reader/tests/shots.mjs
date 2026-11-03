// Capturas de la UI con Playwright. Uso: node apps/reader/tests/shots.mjs
//
// Levanta la API local (rrm.offline) y `next dev`, recorre la UI a 1440 y 390 px
// y escribe apps/reader/shots/<ancho>-<nombre>.png más report.json.
// Datos: RRM_OFFLINE_DIR si existe; si no, fixtures sintéticos en un temporal.
// Puertos: RRM_SHOTS_PORT (3100) y RRM_SHOTS_API_PORT (8787).
// Sale con 1 si hay pageerror o si faltan las capturas 01, 03 o 05.

import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const READER = path.resolve(HERE, "..");
const ROOT = path.resolve(READER, "..", "..");
const OUT = path.join(READER, "shots");
const UI_PORT = Number(process.env.RRM_SHOTS_PORT || 3100);
const API_PORT = Number(process.env.RRM_SHOTS_API_PORT || 8787);
const BASE = `http://127.0.0.1:${UI_PORT}`;
const API = `http://127.0.0.1:${API_PORT}`;
const SIZES = [[1440, 900], [390, 844]];
const REQUIRED = ["01-inicio", "03-atlas", "05-paper-vistazo"];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const children = [];
let tmpFixtures = "";

function stopAll() {
  for (const child of children) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* ya terminó */ }
  }
  if (tmpFixtures) {
    try { rmSync(tmpFixtures, { recursive: true, force: true }); } catch { /* temporal */ }
    tmpFixtures = "";
  }
}
process.on("SIGINT", () => { stopAll(); process.exit(130); });
process.on("SIGTERM", () => { stopAll(); process.exit(143); });

function launch(cmd, args, opts) {
  const child = spawn(cmd, args, { ...opts, detached: true, stdio: ["ignore", "pipe", "pipe"] });
  let tail = "";
  const keep = (buf) => { tail = (tail + buf.toString()).slice(-4000); };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.tail = () => tail;
  children.push(child);
  return child;
}

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => { res.resume(); resolve(res.statusCode); });
    req.on("error", () => resolve(0));
    req.setTimeout(3000, () => { req.destroy(); resolve(0); });
  });
}

async function waitFor(url, child, ms, label) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (child.exitCode !== null) throw new Error(`${label} terminó antes de responder:\n${child.tail()}`);
    if ((await ping(url)) === 200) return;
    await sleep(500);
  }
  throw new Error(`${label} no respondió 200 en ${ms / 1000} s:\n${child.tail()}`);
}

function fixturesDir() {
  const given = process.env.RRM_OFFLINE_DIR;
  if (given) {
    if (!existsSync(path.join(given, "manifest.json"))) throw new Error("RRM_OFFLINE_DIR no tiene manifest.json.");
    return { dir: given, synthetic: false };
  }
  tmpFixtures = mkdtempSync(path.join(tmpdir(), "rrm-shots-"));
  const dir = path.join(tmpFixtures, "fx");
  const made = spawnSync("python3", [path.join(ROOT, "scripts", "build_ui_fixtures.py"), "--out", dir], { cwd: ROOT, encoding: "utf8" });
  if (made.status !== 0) throw new Error(`no pude generar los fixtures sintéticos:\n${made.stderr || made.stdout}`);
  return { dir, synthetic: true };
}

function readJson(file) {
  try { return JSON.parse(readFileSync(file, "utf8")); } catch { return null; }
}

/** Pregunta, papers y texto de la caja, leídos del directorio de datos. */
function describe(dir) {
  const manifest = readJson(path.join(dir, "manifest.json")) || {};
  const row = (manifest.queries || [])[0] || {};
  const papers = {};
  const folder = path.join(dir, "papers");
  if (existsSync(folder)) {
    for (const name of readdirSync(folder).sort()) {
      if (!/^\d+\.json$/.test(name)) continue;
      const body = readJson(path.join(folder, name));
      if (body) papers[name.replace(".json", "")] = body.status || body.meta?.status || "";
    }
  }
  const index = readJson(path.join(dir, "ask", "index.json"));
  const rows = Array.isArray(index) ? index : index?.rows || [];
  const ask = rows.find((r) => r.stage === "revisar") || rows[0] || null;
  const done = Object.keys(papers).filter((id) => papers[id] === "done");
  const full = (ask && papers[String(ask.focus)] === "done" ? String(ask.focus) : done[0]) || "";
  const abstract = Object.keys(papers).find((id) => papers[id] === "abstract_only") || "";
  return { question: String(row.q || ""), full, abstract, askText: ask ? String(ask.text || "") : "" };
}

const sel = (...list) => list.join(", ");
const S = {
  input: sel('[data-screen="start"] input', '[data-screen="inicio"] input', 'input[aria-label="Question"]'),
  atlas: sel('[data-screen="atlas"] [data-live-map]', "[data-live-map]"),
  dot: sel(".node-dot:not(.is-faint) circle", ".node-dot circle", "[data-live-map] .p"),
  tip: sel(".map-tip", "[data-live-map] .peek"),
  paper: sel('[data-screen="paper"] .paper-head', ".paper-head"),
  ask: sel('[data-screen="paper"] form.ask-card', "form.ask-card"),
  alert: '[role="alert"], .fail-reason, .center-msg, [data-screen="error"]',
  empty: sel('[data-screen="vacio"]', "p.muted"),
};

async function ask(page, question) {
  await page.waitForSelector(S.input, { timeout: 20000 });
  // Escribir antes de la hidratación pierde el texto: espera a que React tome el input.
  await page.waitForFunction(
    (selector) => { const el = document.querySelector(selector); return Boolean(el) && Object.keys(el).some((k) => k.startsWith("__reactProps$")); },
    S.input,
    { timeout: 20000 },
  );
  await page.fill(S.input, question);
  await page.keyboard.press("Enter");
}

async function main() {
  const { chromium } = require("playwright");
  const { dir, synthetic } = fixturesDir();
  const info = describe(dir);
  if (!info.question) throw new Error("el manifest no trae ninguna pregunta.");
  mkdirSync(OUT, { recursive: true });
  for (const name of readdirSync(OUT)) if (/\.(png|json)$/.test(name)) rmSync(path.join(OUT, name));

  const env = { ...process.env, RRM_FEATURES: "core" };
  delete env.MODEL_API_KEY;
  const api = launch("python3", ["-m", "rrm.offline", "--root", dir, "--host", "127.0.0.1", "--port", String(API_PORT)], { cwd: ROOT, env });
  await waitFor(`${API}/`, api, 20000, "la API local");
  const ui = launch("npx", ["next", "dev", "-p", String(UI_PORT)], {
    cwd: READER,
    env: {
      ...env,
      NEXT_PUBLIC_RRM_FEATURES: "core",
      NEXT_PUBLIC_BURST_URL: API,
      NEXT_PUBLIC_READER_URL: API,
      NEXT_PUBLIC_RRM_DEMO_TOKEN: "local",
      NEXT_PUBLIC_RRM_OFFLINE: "1",
    },
  });
  await waitFor(`${BASE}/`, ui, 180000, "next dev");

  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
  const launchOpts = proxy ? { proxy: { server: proxy, bypass: "127.0.0.1,localhost" } } : {};
  if (process.env.RRM_CHROME) launchOpts.executablePath = process.env.RRM_CHROME;
  const browser = await chromium.launch(launchOpts);
  const report = { synthetic, question: info.question, ui: BASE, api: API, widths: {}, pageerrors: [], console: [], api_errors: [], other_http: [] };
  const captured = new Set();
  const extras = readdirSync(path.join(HERE, "shots.d")).filter((n) => n.endsWith(".mjs")).sort();

  // Calentamiento: `next dev` compila cada ruta en la primera visita y eso hace fallar al primer paso.
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    try {
      await page.goto(BASE, { waitUntil: "domcontentloaded" });
      await ask(page, info.question);
      await page.waitForSelector(S.atlas, { timeout: 90000 });
      if (info.full) {
        await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, info.full);
        await page.waitForSelector(S.paper, { timeout: 90000 });
      }
      await sleep(1000);
    } catch (err) {
      console.log(`  calentamiento: ${String(err?.message || err).split("\n")[0]}`);
    }
    await context.close();
  }

  for (const [width, height] of SIZES) {
    const steps = [];
    report.widths[width] = steps;
    const context = await browser.newContext({ viewport: { width, height } });
    const watch = (page) => {
      page.on("pageerror", (err) => report.pageerrors.push({ width, step: current, message: String(err?.message || err), stack: String(err?.stack || "").split("\n").slice(0, 5).join(" | ").slice(0, 600) }));
      page.on("console", (msg) => { if (msg.type() === "error") report.console.push({ width, text: msg.text().slice(0, 300) }); });
      page.on("response", (res) => {
        if (res.status() < 400) return;
        const row = { width, step: current, status: res.status(), url: res.url().replace(/([?&]k=)[^&]*/, "$1…").slice(0, 200) };
        if (res.url().startsWith(API)) report.api_errors.push(row);
        else report.other_http.push(row);
      });
    };
    const fresh = async () => { const page = await context.newPage(); watch(page); return page; };
    const shotOf = (page) => async (name) => {
      await page.screenshot({ path: path.join(OUT, `${width}-${name}.png`) });
      captured.add(`${width}:${name}`);
    };
    let current = "";
    const step = async (name, fn) => {
      current = name;
      try {
        try {
          await fn();
        } catch (err) {
          if (err?.name !== "TimeoutError") throw err;
          await fn(); // un reintento: next dev a veces tarda en compilar
        }
        steps.push({ name, status: "ok" });
      } catch (err) {
        const why = String(err?.message || err).split("\n")[0].slice(0, 200);
        steps.push({ name, status: "omitido", why });
        console.log(`  [${width}] ${name}: omitido (${why})`);
      }
    };

    let page = await fresh();
    let shot = shotOf(page);
    await step("01-inicio", async () => {
      await page.goto(BASE, { waitUntil: "domcontentloaded" });
      await page.waitForSelector(S.input, { timeout: 30000 });
      await sleep(500);
      await shot("01-inicio");
    });

    await step("02-arranque", async () => {
      const slow = await fresh();
      await slow.route(new RegExp(`^${API.replace(/[.]/g, "\\.")}/(warm|burst)`), async (route) => {
        await sleep(4000);
        await route.continue().catch(() => {});
      });
      await slow.goto(BASE, { waitUntil: "domcontentloaded" });
      await ask(slow, info.question);
      await sleep(2000);
      await shotOf(slow)("02-arranque");
      await slow.close();
    });

    await step("03-atlas", async () => {
      await page.goto(BASE, { waitUntil: "domcontentloaded" });
      await ask(page, info.question);
      await page.waitForSelector(S.atlas, { timeout: 30000 });
      await sleep(1500);
      await shot("03-atlas");
    });

    await step("03b-atlas-hover", async () => {
      const dot = page.locator(S.dot).first();
      await dot.hover({ timeout: 5000 });
      await page.waitForSelector(S.tip, { timeout: 5000 });
      await sleep(200);
      await shot("03b-atlas-hover");
    });
    await step("03c-atlas-tarjeta", async () => {
      const dot = page.locator(S.dot).first();
      const id = await dot.getAttribute("data-id");
      await dot.click({ timeout: 5000 });
      if (id) {
        await page.waitForFunction((cid) => document.querySelector(".atlas-screen .card")?.getAttribute("data-id") === cid, id, { timeout: 5000 });
      } else {
        await page.waitForSelector(S.tip, { timeout: 5000 });
      }
      await sleep(300);
      await shot("03c-atlas-tarjeta");
    });
    await step("04-lista", async () => {
      await page.getByRole("button", { name: "List", exact: true }).click({ timeout: 5000 });
      await page.waitForSelector(".core-list", { timeout: 5000 });
      await sleep(300);
      await shot("04-lista");
    });

    const openPaper = async (id) => {
      if (!id) throw new Error("no hay paper en los datos");
      await page.mouse.move(2, 2); // un popover abierto del paper anterior no debe sobrevivir al cambio
      await sleep(400);
      await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, id);
      await page.waitForSelector(S.paper, { timeout: 20000 });
      await sleep(1500);
    };
    await step("05-paper-vistazo", async () => {
      await openPaper(info.full);
      await shot("05-paper-vistazo");
    });
    await step("05b-paper-leer", async () => {
      await page.getByRole("tab", { name: "Read", exact: true }).click({ timeout: 5000 });
      await sleep(800);
      await shot("05b-paper-leer");
    });
    await step("05c-ecuacion-hover", async () => {
      const eq = page.locator(".eq.blk").first();
      await eq.scrollIntoViewIfNeeded({ timeout: 5000 });
      await eq.hover({ timeout: 5000 });
      await sleep(700);
      await shot("05c-ecuacion-hover");
    });
    await step("05d-atlas-encima", async () => {
      const toggle = page.locator('[aria-label*="atlas" i]').first();
      if (!(await toggle.count())) throw new Error("no hay control de atlas en el paper");
      await toggle.click({ timeout: 5000 });
      await sleep(500);
      await shot("05d-atlas-encima");
      await page.keyboard.press("Escape");
      await page.waitForSelector(".ovl", { state: "detached", timeout: 3000 });
    });
    await step("06-caja", async () => {
      if (!info.askText) throw new Error("los datos no traen texto para la caja");
      let form = page.locator(S.ask).first();
      if (!(await form.count())) {
        await page.locator(".yw").first().click({ timeout: 5000 });
        form = page.locator(S.ask).first();
      }
      await form.scrollIntoViewIfNeeded({ timeout: 5000 });
      await form.locator("textarea").fill(info.askText);
      await form.locator('button[type="submit"]').click({ timeout: 5000 });
      await page.waitForSelector(".ask-result .feedback, .ask-card .fail-reason, .ask-card [role=\"status\"]", { timeout: 15000 });
      await sleep(600);
      await form.scrollIntoViewIfNeeded();
      await shot("06-caja");
    });
    await step("07-tabla", async () => {
      const table = page.locator(".table-fig").first();
      await table.scrollIntoViewIfNeeded({ timeout: 5000 });
      await sleep(500);
      await shot("07-tabla");
    });
    await step("08-solo-abstract", async () => {
      await openPaper(info.abstract);
      await shot("08-solo-abstract");
    });

    const ignoreCache = async (page) => {
      await page.addInitScript(() => {
        const orig = Storage.prototype.getItem;
        Storage.prototype.getItem = function (key) {
          if (key === "rrm.questions.v1") return null;
          return orig.call(this, key);
        };
      });
    };
    const dropCache = async (page) => {
      await page.evaluate(async () => {
        try { localStorage.clear(); sessionStorage.clear(); } catch { /* private mode */ }
        await new Promise((resolve) => {
          try {
            const req = indexedDB.deleteDatabase("rrm-questions");
            req.onsuccess = () => resolve();
            req.onerror = () => resolve();
            req.onblocked = () => resolve();
          } catch { resolve(); }
        });
      });
    };
    const failing = async (name, query, handler, url = BASE) => {
      const bad = await fresh();
      await ignoreCache(bad);
      await bad.route(new RegExp(`^${API.replace(/[.]/g, "\\.")}/burst`), handler);
      await bad.goto(url, { waitUntil: "domcontentloaded" });
      await ask(bad, query);
      await bad.waitForSelector(S.alert, { timeout: 20000 }).catch(() => {});
      await sleep(800);
      await shotOf(bad)(name);
      await bad.close();
    };
    await step("09-error-500", () => failing("09-error-500", info.question, (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "fallo de prueba" }) })));
    await step("09b-timeout", () => failing("09b-timeout", info.question, (route) => route.abort("timedout")));
    await step("09c-no-grabada", async () => {
      const miss = await fresh();
      await miss.goto(BASE, { waitUntil: "domcontentloaded" });
      await dropCache(miss);
      await ask(miss, "una pregunta inventada que no está grabada");
      await miss.waitForSelector(S.alert, { timeout: 20000 });
      await sleep(600);
      await shotOf(miss)("09c-no-grabada");
      await miss.close();
    });
    await step("09d-vacio", async () => {
      const none = await fresh();
      await ignoreCache(none);
      await none.route(new RegExp(`^${API.replace(/[.]/g, "\\.")}/burst`), (route) => route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ query: info.question, papers: [], similar: [], edges: [], layout: null }),
      }));
      await none.goto(BASE, { waitUntil: "domcontentloaded" });
      await ask(none, info.question);
      await none.waitForSelector(S.empty, { timeout: 20000 });
      await sleep(600);
      await shotOf(none)("09d-vacio");
      await none.close();
    });
    await step("10-debug", () => failing("10-debug", info.question, (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }), `${BASE}/?debug=1&dev=1`));

    // Pasos extra de otras entregas: shots.d/*.mjs, en orden alfabético.
    for (const file of extras) {
      await step(`extra:${file}`, async () => {
        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await dropCache(page);
        await ask(page, info.question);
        await page.waitForSelector(S.atlas, { timeout: 30000 });
        if (info.full) await openPaper(info.full);
        const mod = await import(pathToFileURL(path.join(HERE, "shots.d", file)).href);
        await mod.default(page, { width, base: BASE, shot, fixtures: { dir, ...info } });
      });
    }
    await context.close();
  }

  await browser.close();
  const missing = REQUIRED.flatMap((name) => SIZES.map(([w]) => `${w}:${name}`)).filter((key) => !captured.has(key));
  report.omitidos = Object.entries(report.widths).flatMap(([w, list]) => list.filter((s) => s.status !== "ok").map((s) => `${w}:${s.name}`));
  report.faltan = missing;
  writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 1));
  const total = Object.values(report.widths).reduce((n, list) => n + list.filter((s) => s.status === "ok").length, 0);
  console.log(`capturas: ${total} ok, ${report.omitidos.length} omitidas, ${report.pageerrors.length} pageerror, ${report.api_errors.length} respuestas 4xx/5xx de la API local`);
  console.log(`ruta: ${OUT}`);
  if (report.pageerrors.length) { console.error("pageerror:", report.pageerrors.map((e) => e.message).join(" | ")); return 1; }
  if (missing.length) { console.error(`faltan capturas obligatorias: ${missing.join(", ")}`); return 1; }
  const a11y = report.omitidos.filter((name) => name.includes("71-a11y"));
  if (a11y.length) { console.error(`71-a11y falló: ${a11y.join(", ")}`); return 1; }
  return 0;
}

let code = 1;
try {
  code = await main();
} catch (err) {
  console.error(String(err?.stack || err));
} finally {
  stopAll();
}
process.exit(code);
