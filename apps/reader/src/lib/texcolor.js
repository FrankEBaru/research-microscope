// Symbol coloring for KaTeX input and the macros papers use that KaTeX lacks. Plain JS so node tests can run it.

/** Macros papers define in their preamble or that KaTeX lacks. Display-only; the paper text is untouched. */
export const TEX_MACROS = {
  "\\textsc": "\\textrm{#1}",
  "\\textsl": "\\textit{#1}",
  "\\vmathbb": "\\mathbb",
  "\\softmax": "\\operatorname{softmax}",
  "\\piref": "\\pi_{\\text{ref}}",
  "\\ref": "\\vphantom{#1}",
  "\\eqref": "\\vphantom{#1}",
  "\\cite": "\\vphantom{#1}",
  "\\bm": "\\boldsymbol{#1}",
  "\\mathbbm": "\\mathbb{#1}",
  "\\diag": "\\operatorname{diag}",
  "\\rowsum": "\\operatorname{rowsum}",
  "\\dropout": "\\operatorname{dropout}",
  "\\mask": "\\operatorname{mask}",
  ...Object.fromEntries("ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((c) => [`\\vd${c}`, `\\mathbf{d${c}}`])),
  ...Object.fromEntries("ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((c) => [`\\v${c}`, `\\mathbf{${c}}`])),
};

const SKIP_BRACE = ["\\mathrm", "\\text", "\\textbf", "\\mathbf", "\\operatorname", "\\mathit"];

/** Wraps known symbols with a stable color (and data-sym for curated ones). */
export function colorize(tex, syms) {
  if (!syms || !syms.length) return tex;
  const multi = syms.filter((s) => s.latex.length > 1).sort((a, b) => b.latex.length - a.latex.length);
  const single = Object.fromEntries(syms.filter((s) => s.latex.length === 1).map((s) => [s.latex, s]));
  // Automatic symbols (RRM-95) carry a CSS class, no data-sym; the group keeps \hat L or \vec x valid.
  const wrap = (s) => (s.cls ? `{\\htmlClass{${s.cls}}{${s.latex}}}` : `\\htmlData{sym=${s.id}}{\\textcolor{${s.color}}{${s.latex}}}`);
  let out = "";
  let i = 0;
  while (i < tex.length) {
    const rest = tex.slice(i);
    const skip = SKIP_BRACE.find((c) => rest.startsWith(c + "{"));
    if (skip) {
      let depth = 0, j = i + skip.length;
      do { if (tex[j] === "{") depth++; else if (tex[j] === "}") depth--; j++; } while (depth > 0 && j < tex.length);
      out += tex.slice(i, j); i = j; continue;
    }
    if (tex[i] === "\\") {
      // Environment names and their column spec are not symbols.
      const env = /^\\(?:begin|end)\s*\{[^}]*\}(?:\{[^}]*\})?/.exec(rest);
      if (env) { out += env[0]; i += env[0].length; continue; }
      const m = /^\\([A-Za-z]+|.)/.exec(rest);
      out += m[0]; i += m[0].length; continue;
    }
    const prev = i > 0 ? tex[i - 1] : "";
    const ms = multi.find((s) => rest.startsWith(s.latex) && !/[A-Za-z]/.test(prev));
    if (ms) { out += wrap(ms); i += ms.latex.length; continue; }
    const ss = single[tex[i]];
    if (ss && prev !== "^" && prev !== "_") { out += wrap(ss); i++; continue; }
    out += tex[i]; i++;
  }
  return out;
}

/** Small repairs before KaTeX: an unescaped "_" inside \text{…} (e.g. DPO's \text{y_w}) is a parse error. */
export function texFix(src) {
  return String(src || "").replace(/\\text\{([^{}]*)\}/g, (m, body) => (/(^|[^\\])_/.test(body) ? `\\text{${body.replace(/(^|[^\\])_/g, "$1\\_")}}` : m));
}
