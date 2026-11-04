// Integration (RRM-95 verification, 4 nov): raw LaTeX that the parser left in prose. Display-only cleanup;
// the stored paper is untouched. `isTexJunk` flags paragraphs that are only layout machinery (ICML/NeurIPS
// style macros, \iftoggle wrappers) so the reader can skip them.

const DROP_ARG = ["footnotetext", "label", "eat", "vspace", "hspace", "vskip", "noalign", "resizebox", "includegraphics", "icmlsetsymbol", "footnotemark"];
const KEEP_ARG = ["textbf", "textit", "emph", "texttt", "textrm", "textsc", "textsf", "underline", "mbox", "caption", "shortstack"];
const NAMES = { sysname: "FlashAttention", model: "LLaMA", method: "the method", ours: "ours" };

/** Removes a command with N balanced-brace arguments; keep=true keeps the last argument's content. */
function stripCmd(s, name, keep) {
  const re = new RegExp(`\\\\${name}\\*?(\\[[^\\]]*\\])?\\s*\\{`, "g");
  let out = "", last = 0, m;
  while ((m = re.exec(s))) {
    let i = m.index + m[0].length, depth = 1;
    while (i < s.length && depth) { if (s[i] === "{") depth++; else if (s[i] === "}") depth--; i++; }
    out += s.slice(last, m.index) + (keep ? s.slice(m.index + m[0].length, i - 1) : "");
    last = i; re.lastIndex = i;
  }
  return out + s.slice(last);
}

export function cleanTexText(raw) {
  let s = String(raw ?? "");
  if (!/[\\{]/.test(s)) return s;
  s = s.replace(/\\makeatletter[\s\S]*?\\makeatother/g, "");
  for (const n of DROP_ARG) s = stripCmd(s, n, false);
  for (const n of KEEP_ARG) s = stripCmd(s, n, true);
  s = stripCmd(s, "keywords", true);
  s = stripCmd(s, "answerYes", true).replace(/\\answer(?:No|NA)\b/g, "");
  s = s
    .replace(/\{\\(?:sl|sc|small|footnotesize|scriptsize|large|Large)\s+([^{}]*)\}/g, "$1")
    .replace(/\\(?:sl|sc|small|footnotesize|scriptsize|normalsize|large|Large|centering|noindent|indent|par|clearpage|newpage|medskip|smallskip|bigskip|hfill|vfill|raggedright|null|onecolumn|twocolumn)\b/g, "")
    .replace(/\\looseness\s*=\s*-?\d+/g, "")
    .replace(/\\(?:begin|end)\s*\{[^}]*\}(?:\[[^\]]*\])?(?:\{[^}]*\})?/g, " ")
    .replace(/\\iftoggle\s*\{[^}]*\}/g, "")
    .replace(/\\(?:STATE|ENDFOR|ENDWHILE|ENDIF)\b/g, " ")
    .replace(/\\(?:FOR|WHILE|IF)\s*\{([^{}]*)\}/g, " $1: ")
    .replace(/\\REQUIRE\b/g, "Require:")
    .replace(/\\ENSURE\b/g, "Ensure:")
    .replace(/\\item\b/g, "•")
    .replace(/\\and\b/g, ",")
    .replace(/\\textasciitilde(?![A-Za-z])\s*/g, "~")
    .replace(/\\textasciicircum(?![A-Za-z])\s*/g, "^")
    .replace(/\\textendash(?![A-Za-z])\s*/g, "–")
    .replace(/\\textemdash(?![A-Za-z])\s*/g, "—")
    .replace(/\\textcolor\s*\{[^{}]*\}\s*/g, "")
    .replace(/\\ding\s*\{\s*55\s*\}/g, "✗")
    .replace(/\\ding\s*\{\s*51\s*\}/g, "✓")
    .replace(/\\(?:cmark|checkmark)\b/g, "✓")
    .replace(/\\xmark\b/g, "✗")
    .replace(/\{[lcr|]*@\{\\extracolsep\{\\fill\}\}[lcr|\s]*\}/g, "")
    .replace(/^\s*\\if\b\s*/g, "")
    .replace(/\\(?:newline|cr|linebreak)\b/g, " ")
    .replace(/\\\\(?=\s)/g, " ")
    .replace(/\d*\.?\d+\\(?:textwidth|linewidth|columnwidth)\b/g, "")
    .replace(/\\[@a-z]*@[A-Za-z@]*/g, "")
    .replace(/\\(sysname|model|method|ours)\b/g, (m, k) => NAMES[k] || k)
    .replace(/\\"([a-z])/g, "$1")
    .replace(/\{\s*\}/g, "")
    .replace(/\{([✓✗])\}/g, "$1")
    .replace(/[ \t]{2,}/g, " ");
  return s;
}

/** A paragraph that is only TeX machinery: internal @-macros (\@setfontsize, \@startsection…) or an
 * \iftoggle wrapper with almost no words. Proofs with bare math and algorithm blocks are content: kept. */
export function isTexJunk(text) {
  const t = String(text || "");
  if (t.length < 20) return false;
  const at = (t.match(/\\[a-z]*@/g) || []).length;
  if (at >= 3) return true;
  if (/^\s*\\iftoggle\b/.test(t)) {
    const words = (cleanTexText(t).replace(/\\[A-Za-z@]+/g, " ").match(/[A-Za-z]{3,}/g) || []).filter((w) => !/^(figure|algorithm|table|begin|end|icmlworkshop|arxiv)$/i.test(w));
    return words.length < 6;
  }
  return false;
}

/** After parseProse: font switches it did not turn into bold/italic (unbalanced braces) are dropped. */
export function cleanLeftover(raw) {
  const s = String(raw ?? "");
  if (!/\\(?:bf|it|em|tt)\b/.test(s)) return s;
  return s.replace(/\{?\\(?:bf|it|em|tt)\b\s*/g, "").replace(/[ \t]{2,}/g, " ");
}

/** The real section title hidden at the end of an \@startsection junk block ("…\bf}{: Algorithm, Analysis} }"). */
export function junkTitle(text) {
  const m = /\\bf\s*\}\s*\{\s*:?\s*([^{}\\]{3,90}?)\s*\}\s*\}\s*$/.exec(String(text || ""));
  return m ? m[1].trim() : "";
}

/** A quoted sentence whose math was flattened by the phrase store ("nablatheta LDPO(pitheta;piref)…",
 * "{align p^*…}"): not shown as a quote. */
export function messyQuote(text) {
  const t = String(text || "");
  const cmds = (t.match(/\\[A-Za-z]+/g) || []).length;
  return cmds >= 3 || /\{\s*(align|equation|split|gather)\b/.test(t) || /\b[a-z]*(nabla|mathbb|mathcal|underbrace)[a-z]*\b/.test(t) || /\b[a-z]{2,}(theta|beta|sigma|alpha)[a-z]*\(/.test(t);
}
