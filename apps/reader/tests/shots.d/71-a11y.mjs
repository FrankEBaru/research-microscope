// RRM-71: tab order keeps a visible focus ring, the page does not scroll sideways,
// and ten key texts clear a 4.5 contrast ratio against their effective background.

const MIN = 4.5;

function parseColor(value) {
  const m = String(value || "").match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] == null ? 1 : Number(m[4])];
}

function channel(c) {
  const x = c / 255;
  return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
}

function lum(rgb) {
  return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
}

function ratio(fg, bg) {
  const a = lum(fg);
  const b = lum(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

async function measure(page, name, selector) {
  const row = await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const parse = (value) => {
      const m = String(value || "").match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
      if (!m) return null;
      return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] == null ? 1 : Number(m[4])];
    };
    const fg = parse(getComputedStyle(el).color);
    const stack = [];
    let node = el;
    while (node) {
      const bg = parse(getComputedStyle(node).backgroundColor);
      if (bg && bg[3] > 0.01) stack.push(bg);
      if (bg && bg[3] >= 0.99) break;
      node = node.parentElement;
    }
    const base = stack.length ? stack[stack.length - 1].slice(0, 3) : [253, 250, 244];
    let bg = base;
    for (let i = stack.length - 2; i >= 0; i--) {
      const c = stack[i];
      bg = [0, 1, 2].map((k) => c[k] * c[3] + bg[k] * (1 - c[3]));
    }
    const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 42);
    return { fg, bg, text };
  }, selector);
  if (!row || !row.fg) return null;
  return { name, selector, text: row.text, fg: row.fg.map((n) => Math.round(n)).join(","), bg: row.bg.map((n) => Math.round(n)).join(","), ratio: ratio(row.fg, row.bg) };
}

async function noSideScroll(page, name) {
  const box = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  if (box.sw > box.iw + 1) throw new Error(`${name}: scroll horizontal ${box.sw} > ${box.iw}`);
}

async function noteCounts(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const s = getComputedStyle(el);
      if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) return false;
      const r = el.getBoundingClientRect();
      return r.width > 1 && r.height > 1 && (el.innerText || "").trim().length > 0;
    };
    return {
      markers: document.querySelectorAll("sup.fn").length,
      margin: [...document.querySelectorAll(".folio .side .sn")].filter(visible).length,
      inline: [...document.querySelectorAll(".folio ol.notes li")].filter(visible).length,
    };
  });
}

async function assertNotes(page, width) {
  await page.setViewportSize({ width, height: 900 });
  const wantMargin = width >= 1280;
  let info = await noteCounts(page);
  const end = Date.now() + 4000;
  const placed = (row) => row.markers > 0 && (wantMargin ? row.margin >= row.markers : row.inline >= row.markers);
  while (Date.now() < end && !placed(info)) {
    await page.waitForTimeout(50);
    info = await noteCounts(page);
  }
  if (info.markers < 1) throw new Error(`${width}: el paper no tiene notas al pie`);
  if (wantMargin && info.margin < info.markers) throw new Error(`${width}: las notas no están en el margen (${info.margin}/${info.markers}, en línea ${info.inline})`);
  if (!wantMargin && info.inline < info.markers) throw new Error(`${width}: las notas no están en línea (${info.inline}/${info.markers}, margen ${info.margin})`);
}

async function openPopoverQuote(page) {
  const selectors = [
    ".folio .abstract [data-pop^='m|']",
    ".table-fig [data-pop^='t|']",
    ".folio [data-pop^='m|']",
  ];
  await page.evaluate(() => {
    const el = document.activeElement;
    if (el && el !== document.body && el !== document.documentElement && typeof el.blur === "function") el.blur();
  });
  for (const sel of selectors) {
    const el = page.locator(sel).first();
    if (!(await el.count())) continue;
    for (let attempt = 0; attempt < 2; attempt++) {
      await el.evaluate((node) => node.scrollIntoView({ block: "center", inline: "nearest" }));
      await el.hover({ timeout: 4000 }).catch(() => {});
      await el.dispatchEvent("mouseover");
      const quote = page.locator(".popover .pop-quote").first();
      const ok = await quote.waitFor({ state: "visible", timeout: 2500 }).then(() => true).catch(() => false);
      if (ok) return true;
    }
  }
  return false;
}

async function tabFocus(page, name) {
  await page.evaluate(() => {
    document.body.setAttribute("tabindex", "-1");
    document.body.focus();
  });
  const bad = [];
  for (let i = 0; i < 20; i++) {
    await page.keyboard.press("Tab");
    const hit = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      if (!visible) return null;
      const shadow = getComputedStyle(el).boxShadow;
      const label = (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40);
      return { shadow, label, tag: el.tagName };
    });
    if (!hit) continue;
    if (!hit.shadow || hit.shadow === "none") bad.push(`${hit.tag} ${hit.label}`);
  }
  if (bad.length) throw new Error(`${name}: foco sin box-shadow (${bad.length}): ${bad.slice(0, 4).join(" | ")}`);
}

export default async function (page, { width, base, fixtures }) {
  const found = [];
  const take = async (name, selector) => {
    if (found.some((row) => row.name === name)) return;
    const row = await measure(page, name, selector);
    if (row) found.push(row);
  };

  await page.goto(base, { waitUntil: "domcontentloaded" });
  await page.locator("#rrm-ask").waitFor({ timeout: 20000 });
  await page.waitForFunction(() => {
    const el = document.querySelector("#rrm-ask");
    return Boolean(el) && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
  }, { timeout: 20000 });
  await noSideScroll(page, "inicio");
  await tabFocus(page, "inicio");
  await take("title", "[data-screen='start'] h1");
  await take("ink-3", "[data-screen='start'] .cap");
  await take("primary", ".b1-go");

  const input = page.locator("#rrm-ask");
  await input.fill(fixtures.question);
  await page.locator(".b1-go").click();
  await page.waitForSelector("[data-live-map]", { timeout: 30000 });
  await page.waitForTimeout(400);
  await noSideScroll(page, "atlas");
  await tabFocus(page, "atlas");
  await take("map title", "[data-screen='map'] h1");
  if (!(await page.locator(".card h2").count())) {
    await page.locator("[data-live-map] .p").first().click();
    await page.waitForSelector(".card h2", { timeout: 4000 });
  }
  await take("card", ".card h2");

  await page.getByRole("button", { name: "List", exact: true }).click();
  await page.waitForSelector(".core-list", { timeout: 5000 });
  await noSideScroll(page, "lista");
  await tabFocus(page, "lista");

  const paperId = fixtures.read || fixtures.full;
  if (paperId) {
    await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, String(paperId));
    await page.waitForSelector('[data-screen="paper"] h1', { timeout: 20000 });
    await page.waitForTimeout(300);
    await noSideScroll(page, "paper");
    await tabFocus(page, "paper");
    await take("paper title", "[data-screen='paper'] h1");
    await take("body", ".folio .blk p");
    await take("meta", ".ah-meta");
    await take("link", ".colo a, .folio .ah-links a");

    if (!(await openPopoverQuote(page))) throw new Error("no apareció .popover .pop-quote");
    await take("pop-quote", ".popover .pop-quote");
    if (await page.locator(".popover .pop-line").count()) await take("pop-line", ".popover .pop-line");
    if (!found.some((row) => row.name === "pop-quote")) throw new Error("falta .pop-quote en el contraste");

    const read = page.getByRole("tab", { name: "Read", exact: true });
    if (await read.count()) await read.click();
    await page.locator("sup.fn").first().waitFor({ timeout: 8000 });
    const saved = await page.evaluate(() => ({ w: window.innerWidth, h: window.innerHeight }));
    for (const w of [1200, 1279, 1440]) await assertNotes(page, w);
    await page.setViewportSize({ width: saved.w, height: saved.h });
  }
  if (fixtures.abstract) {
    await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, String(fixtures.abstract));
    await page.waitForSelector(".notice", { timeout: 20000 });
    await noSideScroll(page, "notice");
    await take("notice", ".notice");
  }

  const low = found.filter((row) => row.ratio < MIN);
  console.log(`contraste ${width}px:`);
  for (const row of found) console.log(`  ${row.ratio.toFixed(2)}  ${row.name}  «${row.text}»  fg ${row.fg}  bg ${row.bg}`);
  if (found.length < 10) throw new Error(`solo ${found.length} textos de contraste, faltan 10`);
  if (low.length) throw new Error(`contraste < ${MIN}: ${low.map((row) => `${row.name} ${row.ratio.toFixed(2)}`).join(", ")}`);
}
