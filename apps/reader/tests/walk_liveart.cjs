// RRM-98 · End-to-end walk with live figures: question → map → paper (Read) → margin hook → panel.
// Measures hover→paint on the hook and click→panel open (after the grow animation), and saves JPGs.
//   node tests/walk_liveart.cjs <base> "<question>" <corpusid> <outPrefix> [width]
// Needs a running UI built with NEXT_PUBLIC_RRM_LIVEART=1 (scripts/demo.sh or next dev).
const { chromium } = require("playwright");
const [base, question, cid, out = "walk", width = "1440"] = process.argv.slice(2);

const med = (a) => (a.length ? a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)] : NaN);
const r1 = (x) => Math.round(x * 10) / 10;

(async () => {
  const b = await chromium.launch();
  const page = await (await b.newContext({ viewport: { width: +width, height: 900 }, deviceScaleFactor: 1 })).newPage();
  const t0 = Date.now();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
  const res = { question, cid };
  const stage = (n) => console.error(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${n}`);
  await page.goto(base, { waitUntil: "domcontentloaded" });
  const inp = 'input[aria-label="Question"], [data-screen="start"] input, [data-screen="inicio"] input';
  await page.waitForFunction((s) => { const el = document.querySelector(s); return el && Object.keys(el).some((k) => k.startsWith("__reactProps$")); }, inp, { timeout: 60000 });
  stage("asking");
  await page.fill(inp, question);
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-live-map]", { timeout: 300000 });
  stage("map");
  res.map_s = r1((Date.now() - t0) / 1000);
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}-1-map.jpg`, quality: 80 });
  res.inMap = await page.evaluate((c) => !!document.querySelector(`[data-id="${c}"], [data-cid="${c}"]`), cid);
  stage("open paper");
  const t1 = Date.now();
  await page.evaluate((c) => { location.hash = `#/p/${c}`; }, cid);
  await page.waitForSelector(".paper-head", { timeout: 300000 });
  stage("paper shown");
  const rd = await page.$('.folio button:has-text("Read")');
  if (rd) { await rd.click(); await page.waitForTimeout(800); }
  const hook = await page.waitForSelector(".lv96-hook", { timeout: 240000, state: "attached" }).catch(() => null);
  stage("hook");
  res.paper_to_hook_s = r1((Date.now() - t1) / 1000);
  res.hooks = await page.$$eval(".lv96-hook", (els) => els.map((e) => `${e.getAttribute("data-widget")}: ${e.querySelector(".lv96-hook-q")?.textContent?.replace(/\s+/g, " ")}`));
  res.inlineInstrument = await page.$$eval("figure.ins", (els) => els.filter((e) => !e.closest(".lv96-panel")).length);
  res.localDkDrawing = await page.$$eval(".sn", (els) => els.filter((e) => /dividing by √/.test(e.textContent || "")).length);
  if (!hook) {
    await page.screenshot({ path: `${out}-2-paper.jpg`, quality: 80 });
    res.errors = errs.slice(0, 8);
    console.log(JSON.stringify(res));
    await b.close();
    return;
  }
  await page.evaluate(() => document.querySelector(".lv96-hook").scrollIntoView({ block: "center" }));
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${out}-2-hook.jpg`, quality: 80 });
  const box = await (await page.$(".lv96-hook")).boundingBox();
  stage("hover");
  const hov = [];
  for (let i = 0; i < 12; i++) {
    await page.mouse.move(box.x - 80, box.y - 30);
    await page.waitForTimeout(250);
    await page.evaluate(() => { window.__h0 = performance.now(); });
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    hov.push(await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(performance.now() - window.__h0))))));
  }
  stage("panel");
  const opens = [];
  for (let i = 0; i < 4; i++) {
    await page.evaluate(() => { window.__o0 = performance.now(); });
    await page.click(".lv96-hook");
    await page.waitForSelector(".lv96-panel", { timeout: 10000 });
    opens.push(await page.evaluate(() => new Promise((r) => {
      const p = document.querySelector(".lv96-panel");
      const done = () => requestAnimationFrame(() => r(performance.now() - window.__o0));
      if (p.classList.contains("is-anim")) p.addEventListener("transitionend", done, { once: true }); else done();
    })));
    await page.waitForTimeout(1500);
    if (i === 0) {
      await page.screenshot({ path: `${out}-3-panel.jpg`, quality: 80 });
      if (await page.$(".lv96-tabs")) {
        await page.click('.lv96-tabs [role="tab"]:nth-child(2)');
        await page.waitForTimeout(2000);
        await page.screenshot({ path: `${out}-4-panel-muse.jpg`, quality: 80 });
      }
    }
    await page.keyboard.press("Escape");
    await page.waitForTimeout(600);
  }
  res.afterEsc = await page.evaluate(() => `${document.querySelector("[data-screen]")?.getAttribute("data-screen")} ${location.hash}`);
  res.hoverPaint_ms = { p50: r1(med(hov)), max: r1(Math.max(...hov)), n: hov.length };
  res.panelOpen_ms = { p50: r1(med(opens)), all: opens.map(r1) };
  res.errors = errs.slice(0, 8);
  console.log(JSON.stringify(res));
  await b.close();
})().catch((e) => { console.error(String(e).split("\n")[0]); process.exit(1); });
