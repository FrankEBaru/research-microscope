// RRM-66: margen (símbolo fijado y nota al pie) y caja al final de una sección.
export default async function (page, { shot }) {
  const read = page.getByRole("tab", { name: "Read", exact: true });
  await read.waitFor({ timeout: 15000 });
  if ((await read.getAttribute("aria-selected")) !== "true") await read.click();
  await page.waitForSelector(".yw", { timeout: 10000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
  await shot("05b-paper-leer");

  const eq = page.locator(".eq.blk").first();
  await eq.scrollIntoViewIfNeeded({ timeout: 8000 });
  await eq.hover();
  await page.waitForTimeout(400);
  await shot("05c-ecuacion-hover");

  const sym = page.locator("[data-tex]").first();
  await sym.scrollIntoViewIfNeeded({ timeout: 8000 });
  await sym.click();
  const fn = page.locator("sup.fn").first();
  await fn.scrollIntoViewIfNeeded({ timeout: 8000 });
  await fn.click();
  await page.waitForTimeout(600);
  await shot("05e-margen");

  const end = page.locator(".yw").first();
  await end.scrollIntoViewIfNeeded({ timeout: 8000 });
  await end.click();
  await page.waitForSelector(".sec-end form.ask-card", { timeout: 8000 });
  await page.waitForTimeout(400);
  await shot("05f-fin-seccion");
}
