// Tabla B.1: fila bajo el puntero. La gráfica solo existe en modo all (el harness de capturas arranca en core).
export default async function (page, { shot }) {
  const table = page.locator(".table-fig").first();
  await table.scrollIntoViewIfNeeded({ timeout: 8000 });
  const row = table.locator("tbody tr").first();
  await row.hover({ timeout: 5000 });
  await page.waitForTimeout(200);
  await shot("70-tabla-hover");

  const toggle = table.locator(".tchart-toggle");
  if (!(await toggle.count())) return;
  await toggle.click({ timeout: 5000 });
  await page.locator(".tchart .tbar-row").first().waitFor({ timeout: 8000 });
  await shot("70-tabla-grafica");
  await page.locator(".tchart [role='switch']").first().click({ timeout: 5000 });
  await page.locator(".tbar-row.hid").first().click({ timeout: 5000 });
  await page.locator(".tp-result").waitFor({ timeout: 5000 });
  await shot("70-tabla-prediccion");
}
