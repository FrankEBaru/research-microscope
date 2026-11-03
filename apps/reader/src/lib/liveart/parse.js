// Subset parser for `function draw(ctx, state, t)`. No eval.

const BANNED_NAMES = new Set([
  "fetch", "eval", "Function", "import", "require", "document", "window", "globalThis",
  "localStorage", "sessionStorage", "indexedDB", "postMessage", "navigator", "location",
  "innerHTML", "outerHTML", "setTimeout", "setInterval", "requestAnimationFrame",
  "Date", "performance", "WebSocket", "XMLHttpRequest", "WebAssembly", "Worker",
  "SharedArrayBuffer", "atob", "btoa", "cookie", "constructor", "process", "arguments",
  "this", "parent", "self", "frames", "opener", "alert", "open", "close", "print",
]);

function tokenize(src) {
  const tokens = [];
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    if (c === " " || c === "\n" || c === "\r" || c === "\t") { i += 1; continue; }
    if (c === "/" && src[i + 1] === "/") { while (i < n && src[i] !== "\n") i += 1; continue; }
    if (c === "/" && src[i + 1] === "*") {
      i += 2;
      while (i < n && !(src[i] === "*" && src[i + 1] === "/")) i += 1;
      if (i >= n) throw new Error("syntax:comment");
      i += 2;
      continue;
    }
    if (c === '"' || c === "'") {
      const q = c;
      let j = i + 1;
      let out = "";
      while (j < n) {
        const d = src[j];
        if (d === "\\") {
          const e = src[j + 1];
          if (e === "n") out += "\n";
          else if (e === "t") out += "\t";
          else if (e === "\\" || e === "'" || e === '"') out += e;
          else throw new Error("syntax:escape");
          j += 2;
          continue;
        }
        if (d === q) { tokens.push({ k: "str", v: out, i }); i = j + 1; break; }
        if (d === "\n") throw new Error("syntax:string");
        out += d;
        j += 1;
      }
      if (j >= n && (tokens.length === 0 || tokens[tokens.length - 1].i !== i)) throw new Error("syntax:string");
      continue;
    }
    if ((c >= "0" && c <= "9") || (c === "." && src[i + 1] >= "0" && src[i + 1] <= "9")) {
      const m = /^(?:\d+\.\d+|\d+\.|\.\d+|\d+)(?:[eE][+-]?\d+)?/.exec(src.slice(i));
      if (!m) throw new Error("syntax:number");
      tokens.push({ k: "num", v: Number(m[0]), i });
      i += m[0].length;
      continue;
    }
    if ((c >= "A" && c <= "Z") || (c >= "a" && c <= "z") || c === "_" || c === "$") {
      let j = i + 1;
      while (j < n) {
        const d = src[j];
        if ((d >= "A" && d <= "Z") || (d >= "a" && d <= "z") || (d >= "0" && d <= "9") || d === "_" || d === "$") j += 1;
        else break;
      }
      tokens.push({ k: "id", v: src.slice(i, j), i });
      i = j;
      continue;
    }
    const three = src.slice(i, i + 3);
    if (three === "===" || three === "!==") { tokens.push({ k: "op", v: three, i }); i += 3; continue; }
    const two = src.slice(i, i + 2);
    if (["<=", ">=", "+=", "-=", "*=", "/=", "++", "--", "&&", "||"].includes(two)) {
      tokens.push({ k: "op", v: two, i });
      i += 2;
      continue;
    }
    if ("{}()[],.;?:<>+-*/%=!".includes(c)) { tokens.push({ k: "op", v: c, i }); i += 1; continue; }
    throw new Error("syntax:char");
  }
  tokens.push({ k: "eof", v: "eof", i: n });
  return tokens;
}

export function parseDraw(src) {
  const tokens = tokenize(String(src || ""));
  let p = 0;
  const peek = () => tokens[p];
  const at = (v) => peek().v === v;
  function eat(v) {
    if (!at(v)) throw new Error("syntax:" + v);
    return tokens[p++];
  }

  function parseBlock() {
    eat("{");
    const body = [];
    while (!at("}") && !at("eof")) body.push(parseStmt());
    eat("}");
    return { t: "block", body };
  }

  function parseFunction() {
    eat("function");
    const name = eatId();
    eat("(");
    const params = [];
    if (!at(")")) {
      params.push(eatId());
      while (at(",")) { eat(","); params.push(eatId()); }
    }
    eat(")");
    const body = parseBlock();
    return { t: "fn", name, params, body };
  }

  function eatId() {
    const tok = peek();
    if (tok.k !== "id") throw new Error("syntax:ident");
    if (BANNED_NAMES.has(tok.v)) throw new Error("banned:" + tok.v);
    p += 1;
    return tok.v;
  }

  function parseVar() {
    const kind = peek().v;
    eat(kind);
    const decls = [];
    do {
      if (decls.length) eat(",");
      const name = eatId();
      let init = null;
      if (at("=")) { eat("="); init = parseAssign(); }
      decls.push({ name, init });
    } while (at(","));
    return { t: "var", kind, decls };
  }

  function parseStmt() {
    if (at("function")) return parseFunction();
    if (at("var") || at("const")) { const node = parseVar(); eat(";"); return node; }
    if (at("if")) return parseIf();
    if (at("for")) return parseFor();
    if (at("while")) return parseWhile();
    if (at("return")) { eat("return"); const value = at(";") ? null : parseAssign(); eat(";"); return { t: "ret", value }; }
    if (at("break")) { eat("break"); eat(";"); return { t: "break" }; }
    if (at("continue")) { eat("continue"); eat(";"); return { t: "continue" }; }
    if (at("{")) return parseBlock();
    if (at(";")) { eat(";"); return { t: "empty" }; }
    const value = parseAssign();
    eat(";");
    return { t: "expr", value };
  }

  function parseIf() {
    eat("if");
    eat("(");
    const test = parseAssign();
    eat(")");
    const then = parseStmt();
    let els = null;
    if (at("else")) { eat("else"); els = parseStmt(); }
    return { t: "if", test, then, els };
  }

  function parseFor() {
    eat("for");
    eat("(");
    let init = null;
    if (!at(";")) init = (at("var") || at("const")) ? parseVar() : parseAssign();
    eat(";");
    let test = null;
    if (!at(";")) test = parseAssign();
    eat(";");
    let update = null;
    if (!at(")")) update = parseAssign();
    eat(")");
    return { t: "for", init, test, update, body: parseStmt() };
  }

  function parseWhile() {
    eat("while");
    eat("(");
    const test = parseAssign();
    eat(")");
    return { t: "while", test, body: parseStmt() };
  }

  function parseAssign() {
    const left = parseTernary();
    if (at("=") || at("+=") || at("-=") || at("*=") || at("/=")) {
      const op = peek().v;
      eat(op);
      if (left.t !== "ident" && left.t !== "member") throw new Error("syntax:lvalue");
      return { t: "assign", op, left, right: parseAssign() };
    }
    return left;
  }

  function parseTernary() {
    const test = parseOr();
    if (!at("?")) return test;
    eat("?");
    const then = parseAssign();
    eat(":");
    return { t: "tern", test, then, els: parseTernary() };
  }

  function bin(ops, next) {
    let left = next();
    while (ops.includes(peek().v)) {
      const op = peek().v;
      eat(op);
      left = { t: "bin", op, left, right: next() };
    }
    return left;
  }
  function parseOr() { return bin(["||"], parseAnd); }
  function parseAnd() { return bin(["&&"], parseEq); }
  function parseEq() { return bin(["===", "!=="], parseRel); }
  function parseRel() { return bin(["<", ">", "<=", ">="], parseAdd); }
  function parseAdd() { return bin(["+", "-"], parseMul); }
  function parseMul() { return bin(["*", "/", "%"], parseUnary); }

  function parseUnary() {
    if (at("!") || at("-") || at("+") || at("++") || at("--")) {
      const op = peek().v;
      eat(op);
      return { t: "unary", op, arg: parseUnary() };
    }
    return parsePost();
  }

  function parsePost() {
    let expr = parsePrimary();
    while (true) {
      if (at("(")) {
        eat("(");
        const args = [];
        if (!at(")")) {
          args.push(parseAssign());
          while (at(",")) { eat(","); args.push(parseAssign()); }
        }
        eat(")");
        expr = { t: "call", callee: expr, args };
      } else if (at("[")) {
        eat("[");
        const prop = parseAssign();
        eat("]");
        if (prop.t === "str") throw new Error("banned:computed");
        expr = { t: "member", object: expr, prop, computed: true };
      } else if (at(".")) {
        eat(".");
        const name = eatId();
        expr = { t: "member", object: expr, prop: name, computed: false };
      } else if (at("++") || at("--")) {
        const op = peek().v;
        eat(op);
        expr = { t: "unary", op, arg: expr, post: true };
      } else break;
    }
    return expr;
  }

  function parsePrimary() {
    const tok = peek();
    if (tok.k === "num") { p += 1; return { t: "num", v: tok.v }; }
    if (tok.k === "str") { p += 1; return { t: "str", v: tok.v }; }
    if (tok.k === "id" && (tok.v === "true" || tok.v === "false")) { p += 1; return { t: "bool", v: tok.v === "true" }; }
    if (tok.k === "id") return { t: "ident", name: eatId() };
    if (at("(")) { eat("("); const expr = parseAssign(); eat(")"); return expr; }
    if (at("[")) {
      eat("[");
      const items = [];
      if (!at("]")) {
        items.push(parseAssign());
        while (at(",")) { eat(","); items.push(parseAssign()); }
      }
      eat("]");
      return { t: "arr", items };
    }
    throw new Error("syntax:primary");
  }

  const fn = parseFunction();
  if (!at("eof")) throw new Error("syntax:tail");
  if (fn.name !== "draw") throw new Error("syntax:name");
  if (fn.params.join(",") !== "ctx,state,t") throw new Error("syntax:params");
  return fn;
}
