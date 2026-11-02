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
  // Con la fórmula del ticket, i = 0 es la fila rápida. Si no lo es, no se dibuja.
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
    with: softmax(xs.map((x) => x / denom)),
    without: softmax(xs),
  };
}
