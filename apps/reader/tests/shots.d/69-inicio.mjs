// RRM-69: inicio con una pregunta reciente y el atajo de búsqueda.
export default async function (page, { base, shot, fixtures }) {
  await page.goto(base, { waitUntil: "domcontentloaded" });
  const input = page.locator('input[aria-label="Pregunta"]').first();
  await input.waitFor({ timeout: 30000 });
  await page.waitForFunction(
    (selector) => {
      const el = document.querySelector(selector);
      return Boolean(el) && Object.keys(el).some((key) => key.startsWith("__reactProps$"));
    },
    'input[aria-label="Pregunta"]',
    { timeout: 20000 },
  );
  await input.fill(fixtures.question);
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-live-map]", { timeout: 90000 });
  await page.waitForTimeout(400);
  await page.locator("a.wm").click();
  await page.waitForSelector('[data-screen="start"] .b1-try button', { timeout: 15000 });
  await page.waitForTimeout(300);
  await shot("69-inicio-reciente");
  await page.keyboard.press("Control+k");
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === "rrm-ask", { timeout: 5000 });
  await page.waitForTimeout(200);
  await shot("69-inicio-cmdk");
}
