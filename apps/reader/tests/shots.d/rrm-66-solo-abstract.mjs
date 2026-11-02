// RRM-66: paper sin cuerpo (solo abstract) a 1440 y 390.
export default async function (page, { shot, fixtures }) {
  if (!fixtures.abstract) throw new Error("no hay paper de solo abstract en los fixtures");
  await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, fixtures.abstract);
  await page.waitForSelector('[data-screen="paper"] .paper-head', { timeout: 20000 });
  await page.waitForSelector(".notice-absence", { timeout: 10000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await shot("66-solo-abstract");
}
