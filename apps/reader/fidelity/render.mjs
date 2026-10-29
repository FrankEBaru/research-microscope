// Renderiza cada fórmula (la que salió de pandoc) con KaTeX con las MISMAS opciones que la UI y captura el elemento.
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const katexDir = new URL("../node_modules/katex/dist/", import.meta.url);
const [, , todoPath, outDir, outJson] = process.argv;
const todo = JSON.parse(readFileSync(todoPath));
const katex = (await import(new URL("katex.mjs", katexDir))).default;
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
const tmp = new URL("./out/_page.html", import.meta.url);
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 900, height: 400 }, deviceScaleFactor: 2 });
const out = [];
for (const c of todo) {
  let h = null, err = "";
  try { h = katex.renderToString(c.tex, { displayMode: c.display, throwOnError: true, trust: true, strict: "ignore" }); } catch (e) { err = String(e.message).slice(0, 160); }
  let text = "";
  if (h) {
    writeFileSync(tmp, `<meta charset="utf-8"><link rel="stylesheet" href="${new URL("katex.min.css", katexDir).href}"><style>body{margin:0;background:#fff} #m{display:block;width:${c.display ? 760 : 0}px;padding:10px;font-size:1.3em}</style><div id="m">${h}</div>`);
    await p.goto(tmp.href); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(60);
    text = await p.evaluate(() => document.querySelector(".katex-html").textContent);
    await (await p.$("#m")).screenshot({ path: `${outDir}/${c.id}.png` });
  }
  out.push({ id: c.id, error: err, text });
}
await b.close(); writeFileSync(outJson, JSON.stringify(out));
