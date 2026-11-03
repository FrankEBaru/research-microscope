// RRM-73: open paper attribution, closed paper without body, global footer, /licenses.
export default async function (page, { width, base, shot, fixtures }) {
  const noScroll = async (where) => {
    const box = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
    if (box.sw > box.iw) throw new Error(`${where}: scroll horizontal ${box.sw} > ${box.iw} a ${width}`);
  };
  const open = async (id, needle) => {
    await page.evaluate((cid) => { location.hash = `#/p/${cid}`; }, String(id));
    await page.waitForSelector('[data-screen="paper"] .paper-head', { timeout: 20000 });
    if (needle) {
      await page.waitForFunction((text) => (document.querySelector(".rights")?.textContent || "").includes(text), needle, { timeout: 20000 });
    }
    await page.waitForTimeout(300);
  };

  if (!fixtures.full && !fixtures.gated) {
    console.log("73-licencia: sin paper abierto ni cerrado; no fallo");
    return;
  }
  if (fixtures.full) {
    await open(fixtures.full, "modified");
    const line = page.locator(".rights");
    if (!(await line.count())) {
      console.log("73-licencia: el paper abierto no trae .rights (sin licenses.json); no fallo");
    } else {
      const text = await line.innerText();
      if (!/CC BY/.test(text) || !/modified/.test(text)) throw new Error(`linea abierta: ${text}`);
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot("73-abierto");
      await noScroll("abierto");
    }
  }
  if (!fixtures.gated) {
    console.log("73-licencia: no hay paper cerrado o no hay licenses.json; no fallo");
    return;
  }
  await open(fixtures.gated, "arXiv license");
  const closed = await page.locator(".rights").innerText();
  if (!/arXiv license/.test(closed)) throw new Error(`linea cerrada: ${closed}`);
  const abstract = await page.locator(".ah-quote, .blk.abstract").count();
  if (!abstract) throw new Error("el paper cerrado no muestra abstract");
  const leaked = await page.evaluate(() => {
    const figs = document.querySelectorAll("figure, iframe").length;
    const body = [...document.querySelectorAll(".blk")].filter((el) => !el.classList.contains("abstract")).length;
    return figs + body;
  });
  if (leaked) throw new Error("el paper cerrado muestra figura, iframe o cuerpo");
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot("73-cerrado");
  await noScroll("cerrado");
  const foot = await page.locator(".site-foot").innerText();
  if (!/Thank you to arXiv/.test(foot)) throw new Error("falta el pie global");
  await page.goto(`${base}/licenses`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".licenses", { timeout: 20000 });
  await shot("73-licencias");
  await noScroll("licencias");
}
