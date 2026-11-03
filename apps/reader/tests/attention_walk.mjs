// RRM-81. Walks Attention Is All You Need in offline mode and screenshots each section.
// Builds the local fixture from the arXiv e-print when offline-fixtures-attention/ is missing.
// Does not call Modal or Meta. Needs RRM_LICENSE_FIXTURE=1, which this script sets on the API only.
//
//   node apps/reader/tests/attention_walk.mjs

import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "package.json"));
const HERE = path.dirname(fileURLToPath(import.meta.url));
const READER = path.resolve(HERE, "..");
const ROOT = path.resolve(READER, "..", "..");
const FIX = process.env.RRM_OFFLINE_DIR || path.join(ROOT, "offline-fixtures-attention");
const OUT = path.join(READER, "shots", "attention");
const UI_PORT = Number(process.env.RRM_ATTN_PORT || 3118);
const API_PORT = Number(process.env.RRM_ATTN_API_PORT || 8798);
const BASE = `http://127.0.0.1:${UI_PORT}`;
const API = `http://127.0.0.1:${API_PORT}`;
const CID = "13756489";
const ASK = "The Transformer is based solely on attention and dispenses with recurrence.";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const children = [];

function launch(cmd, args, opts) {
  const child = spawn(cmd, args, { ...opts, detached: true, stdio: ["ignore", "pipe", "pipe"] });
  let tail = "";
  const keep = (buf) => { tail = (tail + buf.toString()).slice(-2500); };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.tail = () => tail;
  children.push(child);
  return child;
}

function stopAll() {
  for (const child of children) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* ended */ }
  }
}
process.on("SIGINT", () => { stopAll(); process.exit(130); });
process.on("SIGTERM", () => { stopAll(); process.exit(143); });

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
    if (child.exitCode !== null) throw new Error(`${label} exited:\n${child.tail()}`);
    if ((await ping(url)) === 200) return;
    await sleep(400);
  }
  throw new Error(`${label} no 200 in ${ms / 1000}s:\n${child.tail()}`);
}

function ensureFixture() {
  const paper = path.join(FIX, "papers", `${CID}.json`);
  if (existsSync(paper) && existsSync(path.join(FIX, "manifest.json"))) return;
  const made = spawnSync("python3", [path.join(ROOT, "scripts", "build_attention_fixture.py"), "--out", FIX], {
    cwd: ROOT, encoding: "utf8", timeout: 180000,
  });
  if (made.status !== 0) throw new Error(made.stderr || made.stdout || "fixture build failed");
  process.stdout.write(made.stdout);
}

function slug(text, i) {
  const clean = String(text || "section").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  return `${String(i + 1).padStart(2, "0")}-${clean || "section"}`;
}

async function main() {
  ensureFixture();
  const { chromium } = require("playwright");
  mkdirSync(OUT, { recursive: true });
  const env = { ...process.env, RRM_FEATURES: "core", RRM_LICENSE_FIXTURE: "1" };
  delete env.MODEL_API_KEY;
  const api = launch("python3", ["-m", "rrm.offline", "--root", FIX, "--host", "127.0.0.1", "--port", String(API_PORT)], { cwd: ROOT, env });
  await waitFor(`${API}/`, api, 20000, "offline api");
  const ui = launch("npx", ["next", "dev", "-p", String(UI_PORT)], {
    cwd: READER,
    env: {
      ...env,
      NEXT_PUBLIC_RRM_FEATURES: "core",
      NEXT_PUBLIC_BURST_URL: API,
      NEXT_PUBLIC_READER_URL: API,
      NEXT_PUBLIC_RRM_DEMO_TOKEN: "local",
      NEXT_PUBLIC_RRM_OFFLINE: "1",
      NEXT_PUBLIC_RRM_ARTIFACTS_V2: "1",
      NEXT_PUBLIC_RRM_FIG_PASSAGES: "1",
    },
  });
  await waitFor(`${BASE}/`, ui, 180000, "next dev");

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const issues = [];
  const note = (msg) => issues.push(msg);

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('input[aria-label="Question"]', { timeout: 30000 });
  await page.waitForFunction(() => {
    const el = document.querySelector('input[aria-label="Question"]');
    return Boolean(el) && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
  }, { timeout: 30000 });
  await page.fill('input[aria-label="Question"]', "attention");
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-live-map]", { timeout: 30000 });
  await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, CID);
  await page.waitForSelector(".paper", { timeout: 30000 });
  await page.getByRole("tab", { name: "Read", exact: true }).click({ timeout: 10000 });
  await page.waitForSelector("[data-toc]", { timeout: 15000 });
  await sleep(600);

  const rights = await page.locator(".rights").innerText();
  if (!/Local fixture/.test(rights)) note(`rights line missing the fixture note: ${rights.slice(0, 180)}`);
  if (/Abstract and our explanations only/.test(rights)) note("rights line still says abstract only");

  const heads = await page.locator("[data-toc]").evaluateAll((els) => els.map((el) => (el.textContent || "").replace(/\s+/g, " ").trim()));
  if (heads.length < 8) note(`only ${heads.length} sections rendered`);
  const shots = [];
  for (let i = 0; i < heads.length; i++) {
    const name = `81-${slug(heads[i], i)}.png`;
    await page.locator("[data-toc]").nth(i).scrollIntoViewIfNeeded();
    await sleep(250);
    await page.screenshot({ path: path.join(OUT, name) });
    shots.push({ section: heads[i], file: name });
  }

  const math = await page.evaluate(() => ({
    katex: document.querySelectorAll(".eq .katex").length,
    errors: [...document.querySelectorAll(".katex-error")].slice(0, 8).map((el) => (el.getAttribute("title") || el.textContent || "").slice(0, 120)),
    figs: [...document.querySelectorAll("figure.fig")].map((fig) => ({
      caption: (fig.querySelector("figcaption")?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 80),
      loaded: [...fig.querySelectorAll("img")].filter((img) => img.complete && img.naturalWidth > 0).length,
      missing: fig.querySelectorAll(".fig-missing").length,
      cited: fig.querySelectorAll(".cited-row").length,
    })),
    artifacts: [...document.querySelectorAll("[data-artifact]")].map((el) => el.getAttribute("data-artifact")),
    eqTags: [...document.querySelectorAll(".eq")].slice(0, 6).map((el) => (el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 80)),
    rawRefs: (document.querySelector(".paper")?.innerText || "").match(/\b(?:fig|eq|tab|sec):[A-Za-z0-9_:-]+/g) || [],
  }));
  const inline = await page.locator(".paper .katex").count();
  if (math.katex < 5) note(`only ${math.katex} display equations rendered`);
  if (inline < 40) note(`only ${inline} KaTeX nodes`);
  if (math.errors.length) note(`KaTeX errors: ${math.errors.join(" | ")}`);
  const loaded = math.figs.reduce((n, fig) => n + fig.loaded, 0);
  if (!loaded) note("no figure image loaded");
  if (!math.figs.some((fig) => fig.cited > 0)) note("no figure-citing passages");
  if (!math.artifacts.length) note(`no artifacts (${math.artifacts.join(",")})`);
  if (math.rawRefs.length) note(`unresolved refs: ${[...new Set(math.rawRefs)].slice(0, 8).join(", ")}`);

  const fig = page.locator("figure.fig").filter({ has: page.locator(".cited") }).first();
  if (await fig.count()) {
    await fig.scrollIntoViewIfNeeded();
    await sleep(300);
    await page.screenshot({ path: path.join(OUT, "81-figure-cited.png") });
  }
  const eq = page.locator(".eq").first();
  if (await eq.count()) {
    await eq.scrollIntoViewIfNeeded();
    await sleep(200);
    await page.screenshot({ path: path.join(OUT, "81-equation.png") });
  }

  await page.locator("[data-toc]").first().scrollIntoViewIfNeeded();
  const explain = page.getByRole("button", { name: /Explain/ }).first();
  await explain.click({ timeout: 8000 });
  const form = page.locator("form.ask-card").first();
  await form.locator("textarea").fill(ASK);
  await form.locator('button[type="submit"]').click();
  await page.waitForSelector(".ask-result .claim", { timeout: 20000 });
  const verdicts = await page.locator(".ask-result section").evaluateAll((els) => els.map((el) => (el.innerText || "").replace(/\s+/g, " ").trim().slice(0, 160)));
  const flat = verdicts.join("\n").toLowerCase();
  for (const label of ["matches", "contradicts", "no support", "you missed"]) {
    if (!flat.includes(label)) note(`ask verdict missing: ${label}`);
  }
  await form.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, "81-ask.png") });

  const report = { heads, shots, math, verdicts, issues };
  writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 1));
  console.log(JSON.stringify({ sections: heads.length, katex: math.katex, figures: loaded, artifacts: math.artifacts, issues }, null, 0));
  await browser.close();
  if (issues.length) return 1;
  return 0;
}

let code = 1;
try {
  code = await main();
} catch (err) {
  console.error(String(err?.stack || err));
  code = 1;
} finally {
  stopAll();
}
process.exit(code);
