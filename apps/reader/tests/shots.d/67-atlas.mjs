// RRM-67: hover, click, Read in full, then the atlas over the paper.
export default async function (page, { width, base, shot, fixtures }) {
  const input = page.locator('input[aria-label="Question"]').first();
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await input.waitFor({ timeout: 20000 });
  await page.waitForFunction(() => {
    const el = document.querySelector('input[aria-label="Question"]');
    return Boolean(el) && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
  }, null, { timeout: 20000 });
  await input.fill(fixtures.question);
  await input.press("Enter");
  await page.waitForSelector("[data-live-map] .lane", { timeout: 30000 });
  await page.waitForTimeout(700);
  const lanes = await page.locator("[data-live-map] .lane").count();
  if (lanes < 2) throw new Error(`esperaba al menos 2 carriles, hay ${lanes}`);
  const named = await page.locator("[data-live-map] .ln-name").count();
  if (named < 2) throw new Error(`esperaba al menos 2 nombres, hay ${named}`);
  if (lanes >= 4 && (await page.locator("[data-live-map] .lane.is-far").count()) < 1) throw new Error("falta el carril far");

  const dot = page.locator("[data-live-map] .p").nth(2);
  const id = await dot.getAttribute("data-id");
  await dot.hover();
  await page.waitForSelector("[data-live-map] .peek", { timeout: 4000 });
  await shot("67-atlas-hover");
  await dot.click();
  await page.waitForFunction((cid) => document.querySelector(".atlas-screen .card")?.getAttribute("data-id") === cid, id, { timeout: 4000 });
  await shot("67-atlas-card");

  // Read in full only the paper the offline store actually has. Other ids return 404
  // and the paper screen stays on the loading shell, with no minimap.
  const fullId = String(fixtures.full || "");
  if (!fullId) throw new Error("los datos no traen un paper completo");
  const full = page.locator(`[data-live-map] .p[data-id="${fullId}"]`);
  await full.click();
  await page.waitForFunction((cid) => document.querySelector(".atlas-screen .card")?.getAttribute("data-id") === cid, fullId, { timeout: 4000 });
  await page.getByRole("button", { name: "Read in full", exact: true }).click();
  await page.waitForSelector('[data-screen="paper"] .paper-head', { timeout: 20000 });
  await page.getByRole("button", { name: "Open the atlas" }).waitFor({ timeout: 20000 });
  await shot("67-read");

  const mini = page.getByRole("button", { name: "Open the atlas" });
  await mini.click();
  await page.waitForSelector(".ovl-panel", { timeout: 4000 });
  await page.waitForTimeout(500);
  if (width <= 400) {
    const box = await page.locator(".ovl-panel").boundingBox();
    if (!box || box.width < width - 2 || box.height < 700) throw new Error("el atlas grande no ocupa la pantalla");
  }
  await shot("67-overlay");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".ovl", { state: "detached", timeout: 3000 });
  await page.waitForSelector('[data-screen="paper"]', { timeout: 3000 });
}
