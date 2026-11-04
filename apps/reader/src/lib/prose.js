// Render-time cleanup of LaTeX that the parser left inside text nodes.
// The stored paper is not rewritten. Idempotent: running twice changes nothing.

const UNWRAP = new Set([
  "textbf", "textit", "textrm", "texttt", "textsc", "emph", "mbox", "text",
  "underline", "hbox", "edit", "ensuremath",
]);
const DROP = new Set([
  "rule", "cmidrule", "cline", "specialrule", "cellcolor", "color", "rowcolor",
  "definecolor", "newcommand", "renewcommand", "providecommand", "vspace", "hspace",
  "label", "includegraphics", "title", "author", "affil", "maketitle",
  "tableofcontents", "setcounter", "setlength", "newlength", "pagestyle",
  "thispagestyle", "bibliography", "bibliographystyle", "nocite", "pagebreak",
  "clearpage", "newpage", "cleardoublepage", "frenchspacing", "let",
  "ignorespaces", "noindent", "leavevmode", "protect", "normalcolor",
  "centering", "raggedright", "raggedleft", "arraystretch", "hline", "hdashline",
  "toprule", "midrule", "bottomrule", "tabularnewline",
]);
const STYLE = { it: "em", em: "em", bf: "strong", bfit: "strong", sc: "em", rm: "span", tt: "code", textbf: "strong", textit: "em" };
const STRUCTURAL = new Set([
  "footnote", "footnotetext", "footnotemark", "caption", "subcaption", "captionof",
  "paragraph", "subparagraph", "section", "subsection", "subsubsection",
  "chapter", "part", "item", "abstract", "thanks", "title", "author",
  "cite", "ref", "eqref", "url", "href", "label", "captionsetup",
]);
const ACCENT = {
  '"': { a: "ä", e: "ë", i: "ï", o: "ö", u: "ü", y: "ÿ", A: "Ä", E: "Ë", I: "Ï", O: "Ö", U: "Ü" },
  "'": { a: "á", e: "é", i: "í", o: "ó", u: "ú", y: "ý", A: "Á", E: "É", I: "Í", O: "Ó", U: "Ú" },
  "`": { a: "à", e: "è", i: "ì", o: "ò", u: "ù", A: "À", E: "È", I: "Ì", O: "Ò", U: "Ù" },
  "^": { a: "â", e: "ê", i: "î", o: "ô", u: "û", A: "Â", E: "Ê", O: "Ô", U: "Û" },
  "~": { n: "ñ", a: "ã", o: "õ", N: "Ñ", A: "Ã", O: "Õ" },
  "=": { a: "ā", e: "ē", o: "ō", u: "ū" },
  ".": { z: "ż", e: "ė" },
};
const CITE_DUMP = /\\def\\citename#1\{[\s\S]*?\\@citexb\[\]}\{([^{}]+)\}/;

function readGroup(s, i) {
  if (s[i] !== "{") return null;
  let d = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === "\\") { j += 1; continue; }
    if (s[j] === "{") d += 1;
    else if (s[j] === "}") {
      d -= 1;
      if (d === 0) return [s.slice(i + 1, j), j + 1];
    }
  }
  return null;
}

function readCommand(s, i) {
  const m = /^\\([A-Za-z@]+|.)/.exec(s.slice(i));
  if (!m) return null;
  let j = i + m[0].length;
  const name = m[1];
  if (s[j] === "*") j += 1;
  const args = [];
  while (true) {
    let k = j;
    while (s[k] === " " || s[k] === "\n" || s[k] === "\t") k += 1;
    if (s[k] !== "[" && s[k] !== "{") break;
    j = k;
    if (s[j] === "[") {
      let d = 0;
      let closed = false;
      for (let k = j; k < s.length; k++) {
        if (s[k] === "[") d += 1;
        else if (s[k] === "]") {
          d -= 1;
          if (d === 0) { j = k + 1; closed = true; break; }
        }
      }
      if (!closed) break;
      continue;
    }
    const g = readGroup(s, j);
    if (!g) break;
    args.push(g[0]);
    j = g[1];
  }
  return { name, args, j };
}

function accentChar(name, s, j) {
  const table = ACCENT[name];
  if (!table) return null;
  if (s[j] === "{") {
    const g = readGroup(s, j);
    if (!g) return null;
    const ch = g[0].trim();
    if (ch.length === 1 && table[ch]) return [table[ch], g[1]];
    return null;
  }
  const ch = s[j];
  if (ch && table[ch]) return [table[ch], j + 1];
  return null;
}

function takeMath(s, i) {
  if (s[i] !== "$") return null;
  if (s.startsWith("$$", i)) {
    const end = s.indexOf("$$", i + 2);
    if (end < 0) return null;
    return [s.slice(i + 2, end).trim(), end + 2, true];
  }
  let j = i + 1;
  while (j < s.length) {
    if (s[j] === "\\") { j += 2; continue; }
    if (s[j] === "$") return [s.slice(i + 1, j).trim(), j + 1, false];
    j += 1;
  }
  return null;
}

/** Turn one text run into text / em / strong / math / cite. */
export function parseProse(input) {
  const s0 = String(input ?? "");
  const out = [];
  let buf = "";
  let boldNext = false;
  const flush = () => {
    if (!buf) return;
    out.push({ t: "text", v: buf });
    buf = "";
  };
  const pushParsed = (nodes) => {
    for (const n of nodes) {
      if (n.t === "text") buf += n.v;
      else { flush(); out.push(n); }
    }
  };

  let i = 0;
  let depth = 0;
  const s = s0;
  while (i < s.length) {
    if (s.startsWith("\\begingroup", i)) {
      const window = s.slice(i, i + 900);
      if (window.includes("NAT@")) {
        const endg = window.indexOf("\\endgroup");
        const chunk = endg >= 0 ? window.slice(0, endg) : window.slice(0, 500);
        const braced = [...chunk.matchAll(/\{([A-Za-z][A-Za-z0-9:_+-]{2,})\}/g)];
        const bare = chunk.match(/[A-Z][A-Za-z0-9:_+-]{3,}/g);
        const key = braced.length ? braced[braced.length - 1][1] : (bare ? bare[bare.length - 1] : "");
        if (key) {
          flush();
          out.push({ t: "cite", keys: [key] });
          const at = chunk.lastIndexOf(key);
          let next = i + at + key.length;
          if (endg >= 0 && endg < at + key.length + 40) next = i + endg + "\\endgroup".length;
          i = next;
          continue;
        }
      }
    }
    if (s.startsWith("\\def\\citename#1", i)) {
      const m = CITE_DUMP.exec(s.slice(i));
      if (m && m.index === 0) {
        flush();
        out.push({ t: "cite", keys: [m[1]] });
        i += m[0].length;
        continue;
      }
    }
    if (s.startsWith("\\(", i) || s.startsWith("\\[", i)) {
      const display = s.startsWith("\\[", i);
      const close = display ? "\\]" : "\\)";
      const end = s.indexOf(close, i + 2);
      if (end > i) {
        const body = s.slice(i + 2, end).trim();
        if (body) {
          flush();
          out.push({ t: "math", v: body, display });
        }
        i = end + close.length;
        continue;
      }
    }
    if (s.startsWith("$$", i) || s[i] === "$") {
      const got = takeMath(s, i);
      if (got && got[0]) {
        flush();
        const body = boldNext ? `\\mathbf{${got[0]}}` : got[0];
        boldNext = false;
        out.push({ t: "math", v: body, display: got[2] });
        i = got[1];
        continue;
      }
    }
    if (s.startsWith("``", i)) { buf += "“"; i += 2; continue; }
    if (s.startsWith("''", i)) { buf += "”"; i += 2; continue; }
    if (s[i] === '"' && buf.endsWith("“") === false && /[A-Za-z0-9”]$/.test(buf) && out.some((n) => n.t === "text" && n.v.includes("“")) || (buf.includes("“") && s[i] === '"')) {
      buf += "”"; i += 1; continue;
    }
    if (s[i] === "{") {
      const g = readGroup(s, i);
      if (g && g[0].trim() === "") { i = g[1]; continue; }
      if (g) {
        const inner = g[0];
        const styled = /^\s*\\(it|em|bf|bfit|sc|rm|tt|textbf|textit)\b\s*([\s\S]*)$/.exec(inner);
        if (styled && STYLE[styled[1]]) {
          const kind = STYLE[styled[1]];
          const kids = parseProse(styled[2]);
          flush();
          if (kind === "code") out.push({ t: "code", v: kids.map((n) => n.t === "text" ? n.v : "").join("") });
          else if (kind === "span") pushParsed(kids);
          else out.push({ t: kind, c: kids });
          i = g[1];
          continue;
        }
      }
    }
    if (s[i] === "\\") {
      if (s[i + 1] === "\\") { buf += " "; i += 2; continue; }
      const loose = takeLooseMath(s, i);
      if (loose) {
        flush();
        out.push({ t: "math", v: loose[0], display: false });
        i = loose[1];
        continue;
      }
      const cmd = readCommand(s, i);
      if (!cmd) { buf += s[i]; i += 1; continue; }
      const accent = accentChar(cmd.name, s, cmd.j);
      if (accent && cmd.args.length === 0) { buf += accent[0]; i = accent[1]; continue; }
      if (cmd.name === "tnote" || cmd.name === "tnotetext") {
        if (cmd.args.length) { i = cmd.j; continue; }
        if (s[cmd.j] === "{") {
          const g = readGroup(s, cmd.j);
          i = g ? g[1] : cmd.j + 1;
          continue;
        }
        i = cmd.j;
        continue;
      }
      if (cmd.name === "boldmath") {
        const arg = cmd.args[0] || "";
        const inner = /^\$([^$]+)\$$/.exec(arg.trim());
        if (inner) {
          flush();
          out.push({ t: "math", v: `\\mathbf{${inner[1]}}`, display: false });
        } else if (arg) {
          pushParsed(parseProse(arg).map((n) => n.t === "math" ? { ...n, v: `\\mathbf{${n.v}}` } : n));
        } else boldNext = true;
        i = cmd.j;
        continue;
      }
      if ((UNWRAP.has(cmd.name) || STYLE[cmd.name]) && cmd.args.length) {
        const arg = cmd.args[cmd.args.length - 1];
        const kids = parseProse(arg);
        const kind = STYLE[cmd.name];
        if (kind === "em" || kind === "strong") {
          flush();
          out.push({ t: kind, c: kids });
        } else if (kind === "code") {
          flush();
          out.push({ t: "code", v: kids.map((n) => n.t === "text" ? n.v : "").join("") });
        } else pushParsed(kids);
        i = cmd.j;
        continue;
      }
      if ((UNWRAP.has(cmd.name) || STYLE[cmd.name]) && s[cmd.j] === "{") {
        i = cmd.j + 1;
        continue;
      }
      if ((cmd.name === "multirow" || cmd.name === "multicolumn") && cmd.args.length >= 3) {
        pushParsed(parseProse(cmd.args[2]));
        i = cmd.j;
        continue;
      }
      if (cmd.name === "eq" && cmd.args.length === 1) {
        flush();
        out.push({ t: "ref", label: cmd.args[0].trim() });
        i = cmd.j;
        continue;
      }
      if (DROP.has(cmd.name)) { i = cmd.j; continue; }
      if (isAnnotation(cmd)) { i = cmd.j; continue; }
      if (cmd.args.length && !/\\/.test(cmd.args[cmd.args.length - 1])) {
        pushParsed(parseProse(cmd.args[cmd.args.length - 1]));
        i = cmd.j;
        continue;
      }
      if (cmd.name === "%" || cmd.name === "&" || cmd.name === "#" || cmd.name === "$" || cmd.name === "_" ) {
        buf += cmd.name; i = cmd.j; continue;
      }
      if (cmd.name === "{" || cmd.name === "}") { buf += cmd.name; i = cmd.j; continue; }
      if (cmd.name === "," || cmd.name === ";" || cmd.name === ":" || cmd.name === "!" || cmd.name === " " || cmd.name === "quad" || cmd.name === "qquad") {
        buf += cmd.name === "!" ? "" : " ";
        i = cmd.j;
        continue;
      }
      // unknown command: keep it so nothing is dropped silently
      buf += s.slice(i, cmd.j);
      i = cmd.j;
      continue;
    }
    if (s[i] === "{") { depth += 1; buf += "{"; i += 1; continue; }
    if (s[i] === "}") {
      if (depth > 0) { depth -= 1; buf += "}"; }
      i += 1;
      continue;
    }
    if (s[i] === "~") { buf += "\u00a0"; i += 1; continue; }
    buf += s[i];
    i += 1;
  }
  flush();
  return tidy(out);
}

const GREEK = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", theta: "θ", lambda: "λ",
  mu: "μ", pi: "π", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", omega: "ω",
  Theta: "Θ", Sigma: "Σ", Omega: "Ω",
};

function flatMath(tex) {
  return String(tex || "")
    .replace(/\s+/g, "")
    .replace(/\\([A-Za-z]+)/g, (_, name) => GREEK[name] || "")
    .replace(/[{}\\^_]/g, "");
}

function echoOf(tex) {
  const flat = flatMath(tex);
  if (!flat || flat.length > 48) return "";
  return flat;
}

/** $d$ seguido de otra d, o θθ: el parser dejó el símbolo y además su texto. */
function collapseEcho(nodes) {
  const out = [];
  for (const n of nodes) {
    const prev = out[out.length - 1];
    if (n.t === "text" && prev && prev.t === "math") {
      const echo = echoOf(prev.v);
      if (echo && n.v.startsWith(echo)) {
        const rest = n.v.slice(echo.length);
        const boundary = echo.length > 1 || !/^[A-Za-z]/.test(rest) || rest[0] === echo[0];
        if (boundary) {
          if (rest) out.push({ ...n, v: rest });
          continue;
        }
      }
    }
    out.push(n);
  }
  return out;
}

/** \\intertext parte una ecuación que KaTeX no puede tragar entera. */
export function splitIntertext(tex) {
  const s = String(tex || "");
  const re = /\\intertext\s*\{/g;
  const parts = [];
  let i = 0;
  let m;
  while ((m = re.exec(s))) {
    const before = s.slice(i, m.index);
    let depth = 1;
    let j = re.lastIndex;
    for (; j < s.length && depth > 0; j++) {
      if (s[j] === "\\") { j += 1; continue; }
      if (s[j] === "{") depth += 1;
      else if (s[j] === "}") depth -= 1;
    }
    if (depth > 0) break;
    if (before.trim()) parts.push({ t: "math", v: before });
    const inner = s.slice(re.lastIndex, j - 1).trim();
    if (inner) parts.push({ t: "text", v: inner });
    i = j;
    re.lastIndex = j;
  }
  const tail = s.slice(i);
  if (tail.trim() || !parts.length) parts.push({ t: "math", v: tail });
  return parts;
}

const LOOSE_MATH = new Set([
  "frac", "dfrac", "tfrac", "sqrt", "binom", "sum", "prod", "int",
  "Big", "Bigg", "bigg", "bigl", "bigr", "Bigl", "Bigr", "Biggl", "Biggr",
  "left", "right", "mathrm", "mathbf", "boldsymbol", "operatorname", "mathbb",
  "overline", "bar", "hat", "tilde", "vec",
]);

/** Fórmulas que perdieron los dólares: \\Big(\\frac{x}{\\sqrt{2}}\\Big). */
function takeLooseMath(s, i) {
  const name = /^\\([A-Za-z]+)/.exec(s.slice(i));
  if (!name || !LOOSE_MATH.has(name[1])) return null;
  let j = i;
  let depth = 0;
  let started = false;
  while (j < s.length) {
    const c = s[j];
    if (c === "\\") {
      const nxt = /^\\([A-Za-z]+)/.exec(s.slice(j));
      if (depth === 0 && started && nxt && !LOOSE_MATH.has(nxt[1]) && !GREEK[nxt[1]]) break;
      if (!nxt) break;
      started = true;
      j += nxt[0].length;
      continue;
    }
    if (c === "{") { depth += 1; started = true; j += 1; continue; }
    if (c === "}") {
      if (!depth) break;
      depth -= 1;
      j += 1;
      continue;
    }
    if (depth === 0 && started && /[A-Za-z]/.test(c)) break;
    if (depth === 0 && started && c === " " && s[j + 1] !== "\\" && s[j + 1] !== "^" && s[j + 1] !== "_") break;
    if ("^_(),.[]|+-=<>*/ ".includes(c) || /[0-9]/.test(c)) { started = true; j += 1; continue; }
    break;
  }
  let body = s.slice(i, j).trim();
  if (!/\\(?:frac|dfrac|tfrac|sqrt|Big|boldsymbol|mathrm)/.test(body)) return null;
  body = body.replace(/(\\(?:Bigg|bigg|Big|big)[r)])(?:\s*\1)+$/, "$1");
  return [body, j];
}

function isAnnotation(cmd) {
  if (!cmd || !cmd.args || !cmd.args.length) return false;
  if (UNWRAP.has(cmd.name) || STYLE[cmd.name] || DROP.has(cmd.name) || STRUCTURAL.has(cmd.name)) return false;
  const arg = String(cmd.args[cmd.args.length - 1] || "");
  if (arg.length < 40 || (arg.match(/ /g) || []).length <= 4) return false;
  const commentName = /todo|fixme|comment|xxx|remark/i.test(cmd.name);
  const personal = /\b(?:I|we|I'd|I'm|TODO|FIXME)\b/.test(arg);
  return commentName || personal;
}

function tidy(nodes) {
  const out = [];
  for (const n of nodes) {
    if (n.t === "text") {
      const v = n.v
        .replace(/\[cite\]/gi, "")
        .replace(/([\u0391-\u03A9\u03B1-\u03C9])\1/g, "$1")
        .replace(/[ \t]{2,}/g, " ")
        .replace(/,{2,}/g, ",");
      if (!v) continue;
      const prev = out[out.length - 1];
      if (prev && prev.t === "text") prev.v += v;
      else out.push({ t: "text", v });
    } else if ((n.t === "em" || n.t === "strong") && Array.isArray(n.c) && n.c.length === 0) {
      continue;
    } else out.push(n);
  }
  return out;
}

function flat(nodes) {
  return nodes.map((n) => {
    if (n.t === "text" || n.t === "code") return n.v;
    if (n.t === "math") {
      const plain = n.v.replace(/\\%/g, "%").replace(/\\([&%#$_{}])/g, "$1").trim();
      if (plain && plain.length <= 16 && /^[\w%+\-.,() ]+$/.test(plain)) return plain;
      return `$${n.v}$`;
    }
    if (n.t === "cite" || n.t === "ref") return "";
    if (Array.isArray(n.c)) return flat(n.c);
    return "";
  }).join("");
}

export function polishText(s) {
  return flat(parseProse(s)).replace(/\s+/g, " ").trim();
}

function braceDelta(s, from = 0) {
  let d = 0;
  for (let i = from; i < s.length; i++) {
    if (s[i] === "\\") { i += 1; continue; }
    if (s[i] === "{") d += 1;
    else if (s[i] === "}") d -= 1;
  }
  return d;
}

/**
 * A \\newcommand whose `{` is closed in a later token (the parser split a math
 * node out of the argument) is not prose. Same for an overpic picture.
 */
function stripSplitDefs(inls) {
  const out = [];
  let depth = 0;
  let env = null;
  const absorb = (v) => {
    let d = depth;
    for (let i = 0; i < v.length; i++) {
      if (v[i] === "\\") { i += 1; continue; }
      if (v[i] === "{") d += 1;
      else if (v[i] === "}") {
        d -= 1;
        if (d <= 0) return [v.slice(i + 1), 0];
      }
    }
    return ["", d];
  };
  for (const x of inls || []) {
    if (!x) continue;
    if (env) {
      if (x.t === "text") {
        const close = `\\end{${env}}`;
        const end = x.v.indexOf(close);
        if (end >= 0) {
          env = null;
          const rest = x.v.slice(end + close.length);
          if (rest) out.push({ ...x, v: rest });
        }
      }
      continue;
    }
    if (depth > 0) {
      if (x.t !== "text") continue;
      const [rest, d] = absorb(x.v);
      depth = d;
      if (rest) out.push({ ...x, v: rest });
      continue;
    }
    if (x.t !== "text") { out.push(x); continue; }
    const v = x.v;
    const begin = /\\begin\{(overpic|picture)\}/.exec(v);
    const def = /\\(?:newcommand|renewcommand|providecommand)\b/.exec(v);
    const hit = [begin, def].filter(Boolean).sort((a, b) => a.index - b.index)[0];
    if (!hit) { out.push(x); continue; }
    if (hit.index > 0) out.push({ ...x, v: v.slice(0, hit.index) });
    if (hit[1] === "overpic" || hit[1] === "picture") {
      const close = `\\end{${hit[1]}}`;
      const at = v.indexOf(close, hit.index);
      if (at >= 0) {
        const rest = v.slice(at + close.length);
        if (rest) out.push({ ...x, v: rest });
      } else env = hit[1];
      continue;
    }
    if (braceDelta(v, hit.index) > 0) {
      depth = braceDelta(v, hit.index);
      continue;
    }
    out.push({ ...x, v: v.slice(hit.index) });
  }
  return out;
}

export function presentInlines(inls) {
  const out = [];
  let buf = [];
  const flush = () => {
    if (!buf.length) return;
    out.push(...parseProse(buf.map((x) => x.v).join("")));
    buf = [];
  };
  for (const x of stripSplitDefs(inls)) {
    if (!x) continue;
    if (x.t === "text") { buf.push(x); continue; }
    flush();
    if (x.t === "em" || x.t === "strong" || x.t === "span" || (x.t === "link" && Array.isArray(x.c))) {
      out.push({ ...x, c: presentInlines(x.c) });
    } else if (x.t === "note") {
      out.push({
        ...x,
        blocks: (x.blocks || []).map((b) => ({ ...b, inlines: presentInlines(b.inlines) })),
      });
    } else if (x.t === "math") {
      const v = String(x.v || "");
      const ref = /^\\(?:eqref|ref|autoref|cref|Cref)\{([^{}]+)\}$/.exec(v.trim());
      if (ref) out.push({ t: "ref", label: ref[1].trim() });
      else if (/\\texttt\b/.test(v) && /\([A-Za-z]+;/.test(v)) out.push(...parseProse(v));
      else out.push(x);
    } else out.push(x);
  }
  flush();
  return liftLabels(collapseEcho(out));
}

const LABEL_RE = /\b((?:fig|figure|tab|table|eq|eqn|app|appendix|sec|section|thm|lem|lemma|prop|cor|def|rem|alg|lst|assumption|claim|conj):[A-Za-z0-9_-]+)\b/g;

function liftLabels(nodes) {
  const out = [];
  for (const n of nodes) {
    if (n.t !== "text" || !LABEL_RE.test(n.v)) { LABEL_RE.lastIndex = 0; out.push(n); continue; }
    LABEL_RE.lastIndex = 0;
    let last = 0;
    let m;
    while ((m = LABEL_RE.exec(n.v))) {
      if (m.index > last) out.push({ t: "text", v: n.v.slice(last, m.index) });
      out.push({ t: "ref", label: m[1] });
      last = m.index + m[0].length;
    }
    if (last < n.v.length) out.push({ t: "text", v: n.v.slice(last) });
  }
  return out;
}

/** A paragraph whose only payload was preamble or \\includegraphics. */
export function visibleInlines(inls) {
  return presentInlines(inls).some((x) => {
    if (x.t === "text") return x.v.trim().length > 0;
    if (x.t === "math" || x.t === "cite" || x.t === "ref" || x.t === "code") return true;
    if (Array.isArray(x.c)) return visibleInlines(x.c);
    return false;
  });
}

export function pdfPagesOnly(blocks) {
  const paras = (blocks || []).filter((b) => b.kind === "p");
  if (!paras.length) return false;
  return paras.every((b) => {
    const raw = (b.inlines || []).map((x) => x.t === "text" ? x.v : "").join("");
    if (!/\\includegraphics/.test(raw)) return false;
    return !visibleInlines(b.inlines);
  });
}
