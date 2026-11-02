// Dos dibujos. Puro, sin DOM. Si el test de oro no pasa, no hay dibujo.

import { makeNormal, mulberry32, softmax } from "./instrument.js";

export function normalizeMath(tex) {
  let text = String(tex || "");
  let prev = "";
  while (prev !== text) {
    prev = text;
    text = text.replace(/\\(?:text|mathrm|mathit|operatorname)\{([^{}]*)\}/g, "$1");
  }
  return text.replace(/([A-Za-z])_\{([A-Za-z0-9]+)\}/g, "$1_$2");
}

function brace(text, i) {
  if (text[i] !== "{") return null;
  let depth = 0;
  for (let j = i; j < text.length; j++) {
    if (text[j] === "\\" && j + 1 < text.length) { j += 1; continue; }
    if (text[j] === "{") depth += 1;
    else if (text[j] === "}") {
      depth -= 1;
      if (depth === 0) return [text.slice(i + 1, j), j + 1];
    }
  }
  return null;
}

export function sqrtDenominator(tex) {
  const text = String(tex || "");
  const names = ["\\dfrac", "\\tfrac", "\\frac"];
  for (let i = 0; i < text.length; i++) {
    const cmd = names.find((name) => text.startsWith(name, i));
    if (!cmd) continue;
    let k = i + cmd.length;
    while (text[k] === " " || text[k] === "\n") k += 1;
    const left = brace(text, k);
    if (!left) continue;
    k = left[1];
    while (text[k] === " " || text[k] === "\n") k += 1;
    const right = brace(text, k);
    if (!right) continue;
    if (right[0].includes("\\sqrt")) return right[0];
    i = right[1] - 1;
  }
  return "";
}

function readD(tex) {
  const norm = normalizeMath(tex).replace(/\s+/g, "");
  const numbered = norm.match(/d(?:_model)?=(\d+(?:\.\d+)?)/);
  if (numbered) return { d: Number(numbered[1]), illustrative: false };
  if (norm.includes("d_model")) return { d: 64, illustrative: true };
  return null;
}

function cell(pos, i, d) {
  return Math.sin(pos / (10000 ** ((2 * i) / d)));
}

function drift(i, d) {
  let sum = 0;
  for (let pos = 0; pos < 31; pos++) sum += Math.abs(cell(pos + 1, i, d) - cell(pos, i, d));
  return sum / 31;
}

export function matrixOf(tex) {
  const flat = String(tex || "").replace(/\s+/g, "");
  const sin = flat.includes("\\sin") || flat.includes("sin(");
  const cos = flat.includes("\\cos") || flat.includes("cos(");
  if (!sin || !cos || !flat.includes("10000")) return null;
  const found = readD(tex);
  if (!found || !Number.isFinite(found.d) || found.d <= 1) return null;
  const d = found.d;
  const last = Math.min(15, Math.floor((d - 1) / 2));
  if (last < 1) return null;
  // i = 0 es la frecuencia más alta (cambia más rápido). Las i grandes cambian lento.
  if (!(drift(0, d) > drift(last, d))) return null;
  const rows = [];
  for (let i = 0; i <= last; i++) {
    const cells = [];
    for (let pos = 0; pos < 32; pos++) cells.push(cell(pos, i, d));
    rows.push({ i, cells });
  }
  return {
    kind: "matriz",
    d,
    illustrative: found.illustrative,
    legend: found.illustrative ? "d = 64, ilustrativo" : `d = ${d}`,
    freq: "Cada fila es una dimensión. La de arriba (i = 0) cambia más rápido.",
    rows,
  };
}

function latexToExpr(src) {
  let text = normalizeMath(src).replace(/d_k/g, "64");
  let prev = "";
  while (prev !== text) {
    prev = text;
    text = text.replace(/\\sqrt\{([^{}]*)\}/g, "sqrt($1)");
    text = text.replace(/\\(?:d|t)?frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1)/($2)");
  }
  text = text.replace(/\\(?:cdot|times)/g, "*").replace(/\\(?:left|right)/g, "");
  text = text.replace(/[{}]/g, "").replace(/\s+/g, "");
  if (/\\/.test(text) || /[A-Za-z]/.test(text.replace(/sqrt/g, ""))) return null;
  return text;
}

function evalExpr(expr) {
  const tokens = [];
  let i = 0;
  while (i < expr.length) {
    const ch = expr[i];
    if (ch >= "0" && ch <= "9" || (ch === "." && expr[i + 1] >= "0" && expr[i + 1] <= "9")) {
      let j = i + 1;
      while (j < expr.length && /[0-9.]/.test(expr[j])) j += 1;
      tokens.push({ t: "n", v: Number(expr.slice(i, j)) });
      i = j;
      continue;
    }
    if (expr.startsWith("sqrt", i)) { tokens.push({ t: "sqrt" }); i += 4; continue; }
    if ("+-*/^()".includes(ch)) { tokens.push({ t: ch }); i += 1; continue; }
    return null;
  }
  let p = 0;
  const peek = () => tokens[p];
  const eat = (kind) => { if (!peek() || peek().t !== kind) return null; return tokens[p++]; };
  function parseSum() {
    let left = parseProd();
    if (left == null) return null;
    while (peek() && (peek().t === "+" || peek().t === "-")) {
      const op = tokens[p++].t;
      const right = parseProd();
      if (right == null) return null;
      left = op === "+" ? left + right : left - right;
    }
    return left;
  }
  function parseProd() {
    let left = parsePow();
    if (left == null) return null;
    while (peek() && (peek().t === "*" || peek().t === "/")) {
      const op = tokens[p++].t;
      const right = parsePow();
      if (right == null) return null;
      left = op === "*" ? left * right : left / right;
    }
    return left;
  }
  function parsePow() {
    const left = parseUnary();
    if (left == null) return null;
    if (peek() && peek().t === "^") {
      p += 1;
      const right = parsePow();
      if (right == null) return null;
      return left ** right;
    }
    return left;
  }
  function parseUnary() {
    if (peek() && peek().t === "-") { p += 1; const v = parseUnary(); return v == null ? null : -v; }
    return parsePrimary();
  }
  function parsePrimary() {
    if (eat("(")) {
      const v = parseSum();
      if (v == null || !eat(")")) return null;
      return v;
    }
    if (eat("sqrt")) {
      if (!eat("(")) return null;
      const v = parseSum();
      if (v == null || !eat(")")) return null;
      return Math.sqrt(v);
    }
    const num = eat("n");
    return num ? num.v : null;
  }
  const value = parseSum();
  if (value == null || p !== tokens.length || !Number.isFinite(value)) return null;
  return value;
}

function denomValue(tex) {
  const den = sqrtDenominator(tex);
  if (!den) return null;
  const expr = latexToExpr(den);
  if (!expr) return null;
  const value = evalExpr(expr);
  if (value == null || value === 0) return null;
  return value;
}

export function compareOf(tex) {
  const denom = denomValue(tex);
  if (denom == null) return null;
  const probe = [1, 2, 4, 8];
  const bare = softmax(probe);
  const scaled = softmax(probe.map((x) => x / denom));
  if (!(Math.max(...bare) > Math.max(...scaled))) return null;
  const normal = makeNormal(mulberry32(1));
  const xs = Array.from({ length: 8 }, () => normal());
  return {
    kind: "con_sin",
    legend: "d_k = 64, ilustrativo",
    look: "Sin dividir, casi todo el peso cae en una sola clave.",
    withLabel: "dividiendo entre √d_k",
    withoutLabel: "sin dividir",
    with: softmax(xs.map((x) => x / denom)),
    without: softmax(xs),
  };
}

// RRM-59. RRM_ARTIFACTS_V2=0 (o NEXT_PUBLIC_RRM_ARTIFACTS_V2=0) apaga esto.
// Default encendido. No clasifica con Muse: si el dibujo no sale, no hay artefacto.

const SHAPE = /\\mathbb\s*\{\s*R\s*\}\s*\^\{([^{}]+)\}/;
const ASSUME = /\b(?:we assume|assume that|assuming that|suppose that|supposing that|under the assumption that|without loss of generality|w\.l\.o\.g\.|given that)\b|\blet\s+\$[^$]{0,80}\$[^.]{0,40}\bbe\b/i;

export function artifactsV2(env = process.env.NEXT_PUBLIC_RRM_ARTIFACTS_V2) {
  if (env == null || env === "") return true;
  return !/^(0|off|false|no)$/i.test(String(env).trim());
}

function squash(text) {
  return String(text || "").replace(/\s+/g, "");
}

function plainBlock(block) {
  const walk = (nodes) => (nodes || []).map((node) => {
    if (!node || typeof node !== "object") return "";
    if (node.t === "text" || node.t === "code") return node.v || "";
    if (node.t === "math") return `$${node.v || ""}$`;
    if (Array.isArray(node.c)) return walk(node.c);
    if (Array.isArray(node.blocks)) return node.blocks.map((sub) => walk(sub.inlines)).join(" ");
    return "";
  }).join("");
  return walk(block?.inlines);
}

function rowsOf(items) {
  const out = [];
  let section = "";
  for (const item of items || []) {
    if (!item || typeof item !== "object") continue;
    if (item.kind === "h") section = plainBlock(item) || item.text || item.section || section;
    const text = item.text || plainBlock(item);
    out.push({
      id: String(item.id || ""),
      kind: item.kind || "",
      section: item.section || section,
      latex: String(item.latex || item.tex || ""),
      text: String(text || ""),
      raw: Boolean(item.raw),
    });
  }
  return out;
}

function shapeLabel(inner) {
  if (!/\\times|\d|\+/.test(inner || "")) return "";
  const label = String(inner)
    .replace(/\\times/g, "×")
    .replace(/\\(?:mathbf|mathrm|boldsymbol|text)\{([^{}]*)\}/g, "$1")
    .replace(/\\[,;! ]|~/g, " ")
    .replace(/[{}\\]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return label;
}

function escalaKind(latex) {
  const text = squash(latex);
  const low = text.toLowerCase();
  if (low.includes("softmax") && text.includes("\\sqrt")) return "softmax";
  if (text.includes("\\exp") && text.includes("\\sqrt") && /d[_}]|\/\\sqrt|\\sqrt\{d/.test(text)) return "softmax";
  if ((/\\over\\sigma|\/\\sigma/.test(text)) && text.includes("\\mu") && !low.includes("softmax")) return "ln";
  return "";
}

function gridKind(latex) {
  const text = squash(latex);
  if (/(?:sin|cos)\(pos\//.test(text)) return "pe";
  const sin = text.includes("\\sin") || text.includes("sin(");
  const cos = text.includes("\\cos") || text.includes("cos(");
  if (sin && cos && text.includes("10000")) return "pe";
  if (text.includes("\\sum") && /(?:\\sin|\\cos|sin|cos)\\frac\{/.test(text) && /k/.test(text) && /n/.test(text)) return "dct";
  return "";
}

const DIM_SQRT = /\\sqrt\{(d(?:_\{(?:k|z|model)\}|_(?:k|z|model))?)\}/;

export function scaleOf(tex) {
  const direct = compareOf(tex);
  if (direct) return direct;
  const found = DIM_SQRT.exec(String(tex || ""));
  if (!found) return null;
  const drawn = compareOf(String(tex).replace(new RegExp(DIM_SQRT.source, "g"), "\\sqrt{64}"));
  if (!drawn) return null;
  const sym = found[1].replace(/[{}]/g, "");
  return { ...drawn, legend: "ilustrativo", withLabel: `dividiendo entre √${sym}` };
}

export function layerOf(tex) {
  if (escalaKind(tex) !== "ln") return null;
  const normal = makeNormal(mulberry32(1));
  const xs = Array.from({ length: 6 }, () => normal());
  const mean = xs.reduce((sum, x) => sum + x, 0) / xs.length;
  const sigma = Math.sqrt(xs.reduce((sum, x) => sum + (x - mean) ** 2, 0) / xs.length);
  if (!(sigma > 1e-6)) return null;
  const before = xs.map((x) => Math.abs(x - mean));
  const after = before.map((x) => x / sigma);
  const gap = before.reduce((sum, x, i) => sum + Math.abs(x - after[i]), 0);
  if (gap < 1e-3) return null;
  return {
    kind: "con_sin",
    tag: "ilustrativo",
    legend: "ilustrativo",
    look: "Cada barra es una coordenada, antes y después de dividir entre σ.",
    withLabel: "después de dividir entre σ",
    withoutLabel: "antes de dividir",
    with: after,
    without: before,
  };
}

export function gridOf(tex) {
  if (gridKind(tex) !== "dct" || matrixOf(tex)) return null;
  const rows = [];
  for (let k = 0; k < 16; k++) {
    const cells = [];
    for (let n = 0; n < 32; n++) cells.push(Math.cos((k * n * Math.PI) / 32));
    rows.push({ i: k, cells });
  }
  const vary = rows.some((row) => Math.max(...row.cells) - Math.min(...row.cells) > 0.2);
  if (!vary) return null;
  return {
    kind: "matriz",
    tag: "ilustrativo",
    d: 32,
    illustrative: true,
    legend: "N = 32, ilustrativo",
    freq: "Cada fila es un k.",
    rows,
  };
}

function casesOf(latex) {
  const text = String(latex || "");
  let body = "";
  const cases = /\\begin\{cases\}([\s\S]*?)\\end\{cases\}/.exec(text);
  if (cases) body = cases[1];
  else if (/\\begin\{array\}/.test(text) && /\\(?:text|mbox|mathrm)\{if\b/.test(text)) {
    const arr = /\\begin\{array\}(?:\{[^{}]*\})?([\s\S]*?)\\end\{array\}/.exec(text);
    body = arr ? arr[1] : "";
  }
  if (!body) return null;
  const branches = body.split(/\\\\/).map((row) => row.replace(/\\(?:\\|cr|hline)\b/g, "").trim()).filter(Boolean).slice(0, 4);
  if (branches.length < 2) return null;
  return branches.map((row) => {
    const bits = row.split("&");
    return { expr: unwrapText(bits[0] || ""), cond: unwrapText(bits[1] || "") };
  }).filter((row) => row.expr || row.cond);
}

function unwrapText(src) {
  let text = String(src || "").replace(/,\s*$/, "").trim();
  let prev = "";
  while (prev !== text) {
    prev = text;
    text = text.replace(/\\(?:text|mbox|mathrm)\{([^{}]*)\}/g, "$1");
  }
  if (!text.includes("\\")) text = text.replace(/\$([^$]+)\$/g, "$1");
  return text.trim();
}

function dropLoose(text) {
  let depth = 0, out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "\\" && i + 1 < text.length) { out += ch + text[i + 1]; i += 1; continue; }
    if (ch === "{") { depth += 1; out += ch; continue; }
    if (ch === "}") { if (depth > 0) { depth -= 1; out += ch; } continue; }
    out += ch;
  }
  return out.trim();
}

function tidy(text) {
  return String(text || "")
    .replace(/\\(?:small|normalsize|bfseries|bf|displaystyle)\b/g, "")
    .replace(/~/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function takeBrace(text, i) {
  if (text[i] !== "{") return null;
  let depth = 0;
  for (let j = i; j < text.length; j++) {
    if (text[j] === "\\" && j + 1 < text.length) { j += 1; continue; }
    if (text[j] === "{") depth += 1;
    else if (text[j] === "}") {
      depth -= 1;
      if (depth === 0) return [text.slice(i + 1, j), j + 1];
    }
  }
  return null;
}

export function stepsOf(text) {
  const src = String(text || "");
  const start = src.search(/\\begin\{algorithm\*?\}/);
  if (start < 0) return null;
  const endRel = src.slice(start).search(/\\end\{algorithm\*?\}/);
  if (endRel < 0) return null;
  const before = src.slice(0, start);
  const body = src.slice(start, start + endRel);
  const cap = /\\caption\{([^{}]*)\}/.exec(body);
  const label = /\\label\{([^{}]*)\}/.exec(body);
  let inner = body
    .replace(/\\begin\{algorithm\*?\}(\[[^\]]*\])?/, "")
    .replace(/\\caption\{[^{}]*\}/, "")
    .replace(/\\label\{[^{}]*\}/, "")
    .replace(/\\begin\{algorithmic\}(\[[^\]]*\])?/, "")
    .replace(/\\end\{algorithmic\}/, "");
  const inputs = [];
  const re = /\\(?:KwIn|KwOut|REQUIRE|ENSURE|Require|Ensure)\b/g;
  let kept = "", last = 0, mark;
  while ((mark = re.exec(inner))) {
    kept += inner.slice(last, mark.index);
    let k = mark.index + mark[0].length;
    while (inner[k] === " " || inner[k] === "\n") k += 1;
    const held = takeBrace(inner, k);
    if (held) {
      inputs.push(tidy(held[0]));
      last = held[1];
      re.lastIndex = held[1];
    } else last = k;
  }
  kept += inner.slice(last);
  const steps = kept
    .split(/\\\\|\\(?:State|STATE|For|FOR|While|WHILE|If|IF|lIf|uIf|Else|Repeat|Until)\b/)
    .map((part) => tidy(part
      .replace(/\\(?:End(?:For|If|While)|ENDFOR|ENDIF|ENDWHILE|Do|Od|Return)\b/g, "")
      .replace(/\\(?:mbox|emph|textbf|textit)\{([^{}]*)\}/g, "$1")
      .replace(/\{\s*(?:\\bfseries\s*)?to\s*\}/g, " to ")
      .replace(/\\[{}]/g, "")
      .replace(/\}\s*\{\s+/g, " ")))
    .map((part) => dropLoose(part.replace(/\s+/g, " ").replace(/^[{}]+/, "").trim()))
    .filter((part) => part.length > 1 && /[A-Za-z0-9\\]/.test(part))
    .slice(0, 8);
  if (steps.length < 2) return null;
  return {
    title: cap ? tidy(cap[1]) : "",
    label: label ? label[1] : "",
    inputs,
    steps,
    appendix: /\\begin\{appendices\}|\\appendix\b/.test(before),
  };
}

function assumption(text) {
  const src = String(text || "");
  const found = ASSUME.exec(src);
  if (!found) return "";
  const win = src.slice(Math.max(0, found.index - 70), found.index + found[0].length + 70);
  if (!win.includes("$") && !win.includes("\\")) return "";
  let start = found.index;
  while (start > 0 && src[start - 1] !== "." && found.index - start < 160) start -= 1;
  if (src[start] === ".") start += 1;
  let end = src.indexOf(".", found.index + found[0].length);
  if (end < 0 || end - start > 320) end = Math.min(src.length, found.index + found[0].length + 140);
  else end += 1;
  let sentence = src.slice(start, end).replace(/\s+/g, " ").trim();
  const again = ASSUME.exec(sentence);
  if (again && /\\[A-Za-z]|@/.test(sentence.slice(0, again.index))) {
    sentence = sentence.slice(again.index - (sentence[again.index - 1] === "(" ? 1 : 0));
  }
  const stripped = sentence
    .replace(/\$[^$]*\\mathbb\s*\{\s*R\s*\}[^$]*\$/g, "")
    .replace(/\\mathbb\s*\{\s*R\s*\}\s*(?:\^\{[^{}]*\})?/g, "");
  if (/\\mathbb/.test(sentence) && !/[$\\]/.test(stripped)) return "";
  return sentence.slice(0, 280);
}

function whyQuote(rows) {
  const blob = rows.map((row) => row.text).join("\n");
  const re = /gradient|counteract|variance/gi;
  let mark;
  while ((mark = re.exec(blob))) {
    let start = blob.lastIndexOf(".", mark.index);
    if (start < 0 || mark.index - start > 280) start = Math.max(0, mark.index - 100);
    else start += 1;
    let end = blob.indexOf(".", mark.index);
    if (end < 0) end = Math.min(blob.length, mark.index + 160);
    else end += 1;
    const sentence = blob.slice(start, end).replace(/\s+/g, " ").trim();
    if (/softmax|gradient/i.test(sentence) && /scale|counteract|variance|sqrt|softmax/i.test(sentence)) {
      return sentence.slice(0, 280);
    }
  }
  return "";
}

function appendixSection(section) {
  return /appendix|apéndice|anexo|приложение/i.test(section || "");
}

export function collectV2(items, flag) {
  const on = flag === undefined ? artifactsV2() : artifactsV2(flag);
  if (!on) return { notes: [], artifacts: [] };
  const rows = rowsOf(items);
  const artifacts = [];
  const seenShape = new Set();
  const seenScale = new Set();
  const seenGrid = new Set();
  const seenCase = new Set();
  let dctDone = false;
  const quote = whyQuote(rows.filter((row) => !row.raw));
  const bySec = new Map();
  for (const row of rows) {
    if (row.kind !== "eq") continue;
    if (!bySec.has(row.section)) bySec.set(row.section, []);
    bySec.get(row.section).push(row);
  }
  const scaleHost = new Map();
  for (const [section, group] of bySec) {
    if (group.length > 6 || group.some((row) => escalaKind(row.latex))) continue;
    const blob = group.map((row) => squash(row.latex)).join("");
    const low = blob.toLowerCase();
    if ((low.includes("softmax") || (blob.includes("\\exp") && blob.includes("\\sum"))) && blob.includes("\\sqrt") && /d[_z}]/.test(blob)) {
      const host = group.find((row) => squash(row.latex).includes("\\sqrt"));
      if (host) scaleHost.set(host.id, host);
    }
  }
  let eqRun = [];
  const flushRun = () => {
    if (!eqRun.length) return;
    const joined = eqRun.map((row) => row.latex).join(" \\\\ ");
    const section = eqRun[0].section;
    if (!seenGrid.has(section) && (gridKind(joined) === "pe" || matrixOf(joined))) {
      const drawn = matrixOf(joined);
      if (drawn) {
        seenGrid.add(section);
        artifacts.push({ block_id: eqRun[0].id, type: "matriz", tex: joined, tag: "ilustrativo" });
      }
    }
    eqRun = [];
  };
  for (const row of rows) {
    if (row.kind === "eq") eqRun.push(row);
    else if (row.kind === "p") flushRun();
  }
  flushRun();
  let pastAppendix = false;
  for (const row of rows) {
    const blob = `${row.latex}\n${row.text}`;
    if (appendixSection(row.section) || /\\begin\{appendices\}|\\appendix\b/.test(blob)) pastAppendix = true;
    const shape = SHAPE.exec(row.latex) || SHAPE.exec(row.text);
    if (!row.raw && !pastAppendix && shape && !seenShape.has(row.section)) {
      const label = shapeLabel(shape[1]);
      if (label) {
        seenShape.add(row.section);
        artifacts.push({ block_id: row.id, type: "forma", kind: "forma", label, body: !appendixSection(row.section) });
      }
    }
    if (row.kind === "eq" && !seenScale.has(row.section)) {
      const kind = escalaKind(row.latex) || (scaleHost.has(row.id) ? "softmax" : "");
      if (kind === "ln") {
        const drawn = layerOf(row.latex);
        if (drawn) {
          seenScale.add(row.section);
          artifacts.push({ block_id: row.id, type: "con_sin", tex: row.latex, scale: drawn, preferScale: true, quote });
        }
      } else if (kind === "softmax") {
        const drawn = scaleOf(row.latex);
        if (drawn) {
          seenScale.add(row.section);
          const same = drawn.legend === "d_k = 64, ilustrativo" && drawn.withLabel === "dividiendo entre √d_k";
          artifacts.push({ block_id: row.id, type: "con_sin", tex: row.latex, tag: "ilustrativo", scale: same ? null : drawn, quote });
        }
      }
    }
    if (row.kind === "eq" && !dctDone && !seenGrid.has(row.section) && gridKind(row.latex) === "dct") {
      const drawn = gridOf(row.latex);
      if (drawn) {
        dctDone = true;
        seenGrid.add(row.section);
        artifacts.push({ block_id: row.id, type: "matriz", tex: row.latex, grid: drawn });
      }
    }
    if (row.kind === "eq" && !seenCase.has(row.section)) {
      const branches = casesOf(row.latex);
      if (branches && branches.length >= 2) {
        seenCase.add(row.section);
        artifacts.push({ block_id: row.id, type: "casos", kind: "casos", branches });
      }
    }
    if (!row.text.includes("\\begin{algorithm}") && !row.latex.includes("\\begin{algorithm}")) continue;
    const parsed = stepsOf(blob);
    if (!parsed) continue;
    let host = row.id;
    const buried = parsed.appendix || appendixSection(row.section);
    if (buried) {
      host = "";
      if (parsed.label) {
        const hit = rows.find((other) => other.id !== row.id && !appendixSection(other.section) && other.text.includes(parsed.label));
        if (hit) host = hit.id;
      }
    }
    if (!host) continue;
    const hostRow = rows.find((other) => other.id === host) || row;
    artifacts.push({
      block_id: host,
      type: "pasos",
      kind: "pasos",
      title: parsed.title,
      inputs: parsed.inputs,
      steps: parsed.steps,
      body: !appendixSection(hostRow.section),
    });
  }
  const notes = [];
  const assumed = new Map();
  const strong = /\b(?:assume|assuming|suppose|supposing|without loss of generality|w\.l\.o\.g\.|given that)\b/i;
  for (const row of rows) {
    if (row.raw || row.kind === "eq" || row.kind === "h") continue;
    const sentence = assumption(row.text);
    if (!sentence || !ASSUME.test(sentence)) continue;
    const note = {
      block_id: row.id,
      sent_index: 0,
      note: sentence,
      cite: "",
      generated: false,
      section: row.section,
      kind: "supuesto",
      body: !appendixSection(row.section) && !/\\begin\{appendices\}|\\appendix\b/.test(row.text),
    };
    const prev = assumed.get(row.section);
    if (!prev) { assumed.set(row.section, note); notes.push(note); continue; }
    if (!strong.test(prev.note) && strong.test(sentence)) {
      notes[notes.indexOf(prev)] = note;
      assumed.set(row.section, note);
    }
  }
  return { notes: capNotes(notes), artifacts: capPaper(artifacts) };
}

function capNotes(list) {
  const strong = /\b(?:assume|assuming|suppose|supposing|without loss of generality|w\.l\.o\.g\.|given that)\b/i;
  const hits = list.filter((item) => item.kind === "supuesto");
  const ranked = hits
    .map((item, i) => ({ item, i, s: (item.body === false ? 2 : 0) + (strong.test(item.note) ? 0 : 1) }))
    .sort((a, b) => a.s - b.s || a.i - b.i)
    .map((row) => row.item);
  const keep = new Set(ranked.slice(0, 3));
  return list.filter((item) => item.kind !== "supuesto" || keep.has(item));
}

function capPaper(list) {
  const keep = new Set();
  for (const [type, limit] of [["forma", 3], ["pasos", 4]]) {
    const hits = list.filter((item) => item.type === type);
    const ranked = hits.filter((item) => item.body !== false).concat(hits.filter((item) => item.body === false));
    ranked.slice(0, limit).forEach((item) => keep.add(item));
  }
  return list.filter((item) => (item.type !== "forma" && item.type !== "pasos") || keep.has(item));
}
