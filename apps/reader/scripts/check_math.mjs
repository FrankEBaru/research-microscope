// Renderiza con KaTeX TODAS las fórmulas de los bundles y reporta cuántas fallan (nada se omite en silencio).
import katex from "katex";
import { readFileSync, readdirSync } from "node:fs";

const dir = new URL("../public/papers/", import.meta.url);
let total = 0, fail = 0;
const fails = [];
function walk(inls, id) {
  for (const x of inls || []) {
    if (x.t === "math") check(x.v, x.display, id);
    else if (x.t === "note") for (const b of x.blocks) walk(b.inlines, id);
    else if (Array.isArray(x.c)) walk(x.c, id);
  }
}
function check(tex, display, id) {
  total++;
  try { katex.renderToString(tex, { displayMode: display, throwOnError: true, trust: true, strict: "ignore" }); }
  catch (e) { fail++; fails.push(`${id}: ${e.message.slice(0, 90)} :: ${tex.slice(0, 60)}`); }
}
for (const f of readdirSync(dir)) {
  if (!f.endsWith(".json") || f.startsWith("_")) continue;
  const p = JSON.parse(readFileSync(new URL(f, dir)));
  const before = total, bf = fail;
  for (const b of p.blocks) {
    if (b.kind === "eq") check(b.tex, true, p.arxivId);
    walk(b.inlines, p.arxivId);
    (b.items || []).forEach((it) => walk(it, p.arxivId));
    walk(b.caption, p.arxivId);
    for (const row of [...(b.head || []), ...(b.body || [])]) for (const c of row) walk(c, p.arxivId);
  }
  console.log(`${p.arxivId}: ${total - before} fórmulas, ${fail - bf} con error`);
}
console.log(`TOTAL: ${total - fail}/${total} renderizan sin error`);
fails.forEach((l) => console.log("  FALLA " + l));
const MAX = Number(process.env.MAX_FAIL_RATE ?? 0.02);
console.log(`umbral de fallos: ${(100 * MAX).toFixed(1)}% (actual ${(100 * fail / total).toFixed(2)}%)`);
process.exit(fail / total > MAX ? 1 : 0);
