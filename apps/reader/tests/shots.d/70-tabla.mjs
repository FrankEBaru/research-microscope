// Tabla B.1. La gráfica no está en core; __RRM_FORCE_CHART la enciende en el cliente ya montado, sin otro servidor.
async function fits(page) {
  const box = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
  console.log(`scrollWidth ${box.scrollWidth} innerWidth ${box.innerWidth}`);
  if (box.scrollWidth > box.innerWidth) throw new Error(`scrollWidth ${box.scrollWidth} > innerWidth ${box.innerWidth}`);
}

async function showChart(page, { fixtures }) {
  if (await page.locator(".tchart-toggle").count()) return;
  await page.addInitScript(() => { window.__RRM_FORCE_CHART = 1; });
  await page.reload({ waitUntil: "domcontentloaded" });
  const toggle = page.locator(".tchart-toggle").first();
  try {
    await toggle.waitFor({ timeout: 20000 });
    return;
  } catch { /* la recarga no restauró el paper */ }
  const input = page.locator('input[aria-label="Pregunta"]').first();
  await input.waitFor({ timeout: 20000 });
  await page.waitForFunction((selector) => {
    const el = document.querySelector(selector);
    return Boolean(el) && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
  }, 'input[aria-label="Pregunta"]', { timeout: 20000 });
  await input.fill(fixtures.question);
  await input.press("Enter");
  await page.waitForSelector("[data-live-map], [data-screen='map']", { timeout: 30000 });
  if (!fixtures.full) throw new Error("no hay paper completo para la gráfica");
  await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, fixtures.full);
  await page.locator(".table-fig").first().waitFor({ timeout: 20000 });
  await toggle.waitFor({ timeout: 20000 });
}

export default async function (page, ctx) {
  const { shot } = ctx;
  const table = page.locator(".table-fig").first();
  await table.scrollIntoViewIfNeeded({ timeout: 8000 });
  await fits(page);
  await table.locator("tbody tr").first().hover({ timeout: 5000 });
  await page.waitForTimeout(200);
  await shot("70-tabla-hover");
  await fits(page);

  await showChart(page, ctx);
  const chart = page.locator(".table-fig").first();
  await chart.scrollIntoViewIfNeeded({ timeout: 8000 });
  await chart.locator(".tchart-toggle").click({ timeout: 5000 });
  await page.locator(".tchart .tbar-row").first().waitFor({ timeout: 8000 });
  await fits(page);
  await shot("70-tabla-grafica");
  await page.locator(".tchart [role='switch']").first().click({ timeout: 5000 });
  await page.locator(".tbar-row.hid").first().click({ timeout: 5000 });
  await page.locator(".tp-result").waitFor({ timeout: 5000 });
  await fits(page);
  await shot("70-tabla-prediccion");
}
