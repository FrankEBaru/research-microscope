// Clic real en un punto del mapa vivo. 1280 y 390. No entra en check.sh: levanta next dev.
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(import.meta.url)("playwright");
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const H = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,OPTIONS" };

const PAPERS = [
  { corpusid: 11, title: "Attention Is All You Need", year: 2017, citationcount: 10 },
  { corpusid: 12, title: "What Can Neural Networks Do", year: 2022, citationcount: 4 },
  { corpusid: 13, title: "Neural Machine Translation", year: 2014, citationcount: 8 },
];

let api, ui, browser, base;

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
}

before(async () => {
  api = http.createServer((req, res) => {
    if (req.method === "OPTIONS") {
      res.writeHead(204, H);
      return res.end();
    }
    const url = new URL(req.url, "http://127.0.0.1");
    const json = (body) => {
      res.writeHead(200, { ...H, "content-type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (url.pathname === "/warm") return json({ ready: true });
    if (url.pathname === "/burst") return json({ papers: PAPERS, edges: [], layout: null });
    if (url.pathname === "/labels") {
      return json({
        ok: true,
        by_id: { "11": { authors: ["Ashish Vaswani"], abstract: "Attention." } },
        papers: PAPERS,
      });
    }
    if (url.pathname === "/status") {
      return json({ papers: PAPERS.map((paper) => ({ id: paper.corpusid, status: "done", text: true, source: "latex" })) });
    }
    if (url.pathname === "/paper") return json({ status: "done", paper: { ...PAPERS[0], full: true, blocks: [] }, meta: { source: "latex" } });
    json({});
  });
  const port = await listen(api);
  const origin = `http://127.0.0.1:${port}`;
  ui = spawn("npx", ["next", "dev", "-p", "3211"], {
    cwd: ROOT,
    detached: true,
    env: {
      ...process.env,
      NEXT_PUBLIC_RRM_FEATURES: "core",
      NEXT_PUBLIC_BURST_URL: origin,
      NEXT_PUBLIC_READER_URL: origin,
      NEXT_PUBLIC_RRM_DEMO_TOKEN: "test",
      NEXT_PUBLIC_RRM_OFFLINE: "",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  base = "http://127.0.0.1:3211/";
  const ready = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("next dev no arrancó")), 90000);
    const on = (buf) => {
      const text = buf.toString();
      if (text.includes("Ready") || text.includes("started server") || text.includes("Local:")) {
        clearTimeout(timer);
        resolve();
      }
    };
    ui.stdout.on("data", on);
    ui.stderr.on("data", on);
    ui.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`next dev salió ${code}`));
    });
  });
  void ready;
  browser = await chromium.launch();
});

after(async () => {
  await Promise.race([browser?.close(), new Promise((resolve) => setTimeout(resolve, 3000))]);
  if (ui?.pid) {
    try { process.kill(-ui.pid, "SIGKILL"); } catch { try { ui.kill("SIGKILL"); } catch { /* ya salió */ } }
  }
  await new Promise((resolve) => api?.close(() => resolve()));
});

async function openMap(width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  page.errs = [];
  page.on("pageerror", (err) => page.errs.push(err.message));
  await page.goto(base);
  await page.fill('input[aria-label="Question"]', "attention");
  await page.click('button:has-text("Ver el mapa")');
  await page.waitForSelector(".node-dot circle", { timeout: 15000 });
  return page;
}

for (const [width, height] of [[1280, 900], [390, 844]]) {
  test(`un clic en el punto abre la tarjeta a ${width}`, async () => {
    const page = await openMap(width, height);
    await page.click(".node-dot circle");
    await page.waitForSelector(".map-tip", { timeout: 5000 });
    assert.match(await page.$eval(".map-tip h3", (node) => node.textContent), /Attention|What Can|Neural Machine/);
    assert.deepEqual(page.errs, []);
    await page.close();
  });
}

test("un arrastre de más de 6 px no abre la tarjeta", async () => {
  const page = await openMap(1280, 900);
  const circle = await page.$(".node-dot circle");
  const box = await circle.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 14, y + 4);
  await page.mouse.up();
  await page.waitForTimeout(400);
  assert.equal(await page.$(".map-tip"), null);
  await page.close();
});
