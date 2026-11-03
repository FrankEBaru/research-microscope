// Tabla B.1. Abre el paper solo. En core, __RRM_FORCE_CHART muestra la gráfica
// solo si el build es offline (NEXT_PUBLIC_RRM_OFFLINE=1).
async function fits(page) {
  const box = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
  console.log(`scrollWidth ${box.scrollWidth} innerWidth ${box.innerWidth}`);
  if (box.scrollWidth > box.innerWidth) throw new Error(`scrollWidth ${box.scrollWidth} > innerWidth ${box.innerWidth}`);
}

async function ask(page, question) {
  const input = page.locator('input[aria-label="Question"]').first();
  await input.waitFor({ timeout: 20000 });
  await page.waitForFunction((selector) => {
    const el = document.querySelector(selector);
    return Boolean(el) && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
  }, 'input[aria-label="Question"]', { timeout: 20000 });
  await input.fill(question);
  await input.press("Enter");
}

export default async function (page, { base, shot, fixtures }) {
  if (!fixtures?.question || !fixtures?.full) throw new Error("no hay paper completo para la tabla");
  await page.addInitScript(() => { window.__RRM_FORCE_CHART = 1; });
  await page.goto(base, { waitUntil: "domcontentloaded" });
  await ask(page, fixtures.question);
  await page.waitForSelector("[data-live-map], [data-screen='map']", { timeout: 30000 });
  await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, fixtures.full);
  const table = page.locator(".table-fig:has(.tchart-toggle)").first();
  await table.waitFor({ timeout: 20000 });
  await table.scrollIntoViewIfNeeded();
  await fits(page);
  await table.locator("tbody tr").first().hover({ timeout: 5000 });
  await page.waitForTimeout(200);
  await shot("70-tabla-hover");
  await fits(page);

  await table.locator(".tchart-toggle").click({ timeout: 5000 });
  await table.locator(".tbar-row").first().waitFor({ timeout: 8000 });
  await fits(page);
  await shot("70-tabla-grafica");
  const predict = table.getByRole("switch", { name: "Predict first" });
  if (!(await predict.count())) return;
  await predict.click({ timeout: 5000 });
  await table.locator(".tbar-row.hid").first().click({ timeout: 5000 });
  await table.locator(".tp-result").waitFor({ timeout: 5000 });
  await fits(page);
  await shot("70-tabla-prediccion");
}
