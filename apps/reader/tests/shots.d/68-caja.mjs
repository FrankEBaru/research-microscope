// Caja: revisar el texto grabado y comprobar que el borrador sigue tras recargar.

const PARTS = /^(Matches|Contradicts|No support|You missed)$/;

async function showBox(page) {
  await page.locator("form.ask-card").first().evaluate((el) => {
    const bar = document.querySelector(".topbar");
    const gap = (bar ? bar.getBoundingClientRect().height : 72) + 16;
    const y = el.getBoundingClientRect().top + window.scrollY - gap;
    window.scrollTo({ top: Math.max(0, y), behavior: "instant" });
  });
  await page.waitForTimeout(200);
}

export default async function (page, { shot, fixtures }) {
  const read = page.getByRole("tab", { name: "Read", exact: true });
  if (await read.count()) await read.click({ timeout: 5000 });
  const opener = page.getByRole("button", { name: /your words|tus palabras|explain/i });
  if (await opener.count()) await opener.first().click({ timeout: 5000 }).catch(() => {});

  const form = page.locator("form.ask-card").first();
  await form.waitFor({ timeout: 15000 });
  const text = fixtures.askText || "Frase de prueba: la atención reemplaza la recurrencia.";
  await form.locator("textarea").fill(text);
  await form.locator('button[type="submit"]').click({ timeout: 5000 });
  await page.locator(".ask-result").getByText(PARTS).first().waitFor({ timeout: 20000 });
  await page.getByText("Draft saved", { exact: true }).waitFor({ timeout: 8000 });
  await showBox(page);
  await shot("68-caja");

  await page.evaluate(() => { history.scrollRestoration = "manual"; });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    (sample) => {
      const el = document.querySelector("form.ask-card textarea");
      return Boolean(el && el.value.includes(sample));
    },
    text.slice(0, 24),
    { timeout: 25000 },
  );
  await page.getByText("Draft saved", { exact: true }).waitFor({ timeout: 8000 });
  await showBox(page);
  await shot("68-caja-reload");
}
