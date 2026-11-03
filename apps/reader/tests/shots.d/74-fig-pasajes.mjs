// Pasajes que citan una figura. El paper ya está abierto (describe() elige uno con texto).
async function fits(page) {
  const box = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
  if (box.scrollWidth > box.innerWidth) throw new Error(`scrollWidth ${box.scrollWidth} > innerWidth ${box.innerWidth}`);
}

export default async function (page, { shot }) {
  await fits(page);
  const fig = page.locator("figure").filter({ has: page.locator(".cited") }).first();
  if (!(await fig.count())) {
    console.log("sin figuras citadas");
    return;
  }
  await fig.scrollIntoViewIfNeeded({ timeout: 8000 });
  await shot("74-fig-pasajes");
  const more = fig.getByRole("button", { name: /^\d+ more$/ });
  if (await more.count()) {
    await more.click({ timeout: 5000 });
    await shot("74-fig-pasajes-more");
  }
  await fig.locator(".cited-row").first().click({ timeout: 5000 });
  await page.waitForFunction(() => {
    const el = document.querySelector(".sent.flash");
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= window.innerHeight && r.left >= 0 && r.right <= window.innerWidth;
  }, { timeout: 8000 });
  await shot("74-fig-pasajes-salto");
  await fits(page);
}
