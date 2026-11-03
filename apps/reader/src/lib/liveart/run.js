// Interpreter for the draw subset. The parent page never evals widget source.
import { CANVAS_METHODS, CANVAS_PROPS, MATH_NAMES } from "./spec.js";
import { parseDraw } from "./parse.js";

const MATH_SET = new Set(MATH_NAMES);
const METHOD_SET = new Set(CANVAS_METHODS);
const PROP_SET = new Set(CANVAS_PROPS);
const GEOM = new Set([
  "fillRect", "strokeRect", "moveTo", "lineTo", "arc", "ellipse", "rect",
  "translate", "rotate", "scale", "stroke", "fill",
]);
const PAINT = new Set(["fillRect", "strokeRect", "lineTo", "arc", "ellipse", "rect"]);

const MATH_FN = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos,
  atan: Math.atan, atan2: Math.atan2, exp: Math.exp, log: Math.log, sqrt: Math.sqrt,
  abs: Math.abs, hypot: Math.hypot, sign: Math.sign, min: Math.min, max: Math.max,
  pow: Math.pow, floor: Math.floor, ceil: Math.ceil, round: Math.round,
};

function Env(parent) {
  this.parent = parent;
  this.vars = Object.create(null);
}
Env.prototype.def = function def(name, value) { this.vars[name] = value; };
Env.prototype.find = function find(name) {
  if (name in this.vars) return this;
  return this.parent ? this.parent.find(name) : null;
};
Env.prototype.get = function get(name) {
  const slot = this.find(name);
  if (!slot) throw new Error("undeclared:" + name);
  return slot.vars[name];
};
Env.prototype.set = function set(name, value) {
  const slot = this.find(name);
  if (!slot) throw new Error("undeclared:" + name);
  slot.vars[name] = value;
};

function Ret(value) { this.value = value; }
function Brk() {}
function Cont() {}

export function makeStage() {
  const calls = [];
  const style = {
    fillStyle: "#000", strokeStyle: "#000", lineWidth: 1, globalAlpha: 1,
    font: "12px sans-serif", lineCap: "butt", lineJoin: "miter",
    textAlign: "left", textBaseline: "alphabetic",
  };
  const stack = [];
  const api = {};
  for (const name of CANVAS_METHODS) {
    api[name] = (...args) => {
      if (name === "save") stack.push({ ...style });
      else if (name === "restore") {
        const prev = stack.pop();
        if (prev) Object.assign(style, prev);
      } else {
        calls.push({
          m: name,
          a: args.slice(),
          fill: style.fillStyle,
          stroke: style.strokeStyle,
          lw: style.lineWidth,
        });
      }
    };
  }
  for (const name of CANVAS_PROPS) {
    Object.defineProperty(api, name, {
      enumerable: true,
      get() { return style[name]; },
      set(value) { style[name] = value; },
    });
  }
  return { api, calls };
}

export function geometryChanged(left, right, floor) {
  const a = left.filter((call) => GEOM.has(call.m));
  const b = right.filter((call) => GEOM.has(call.m));
  if (a.length !== b.length) return true;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i].m !== b[i].m) return true;
    if (moved(a[i].lw, b[i].lw, floor)) return true;
    const n = Math.max(a[i].a.length, b[i].a.length);
    for (let k = 0; k < n; k += 1) if (moved(a[i].a[k], b[i].a[k], floor)) return true;
  }
  return false;
}

function moved(x, y, floor) {
  if (typeof x === "number" && typeof y === "number") {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return x !== y;
    return Math.abs(x - y) >= floor;
  }
  return x !== y;
}

export function painted(calls) {
  return calls.some((call) => PAINT.has(call.m));
}

export function execute(ast, state, t, cap) {
  const reads = new Set();
  const stage = makeStage();
  const clock = { n: 0, usesT: false };
  const math = { __kind: "math" };
  const ctx = { __kind: "ctx", api: stage.api };
  const env = new Env(null);
  env.def("ctx", ctx);
  env.def("state", state);
  env.def("t", t);
  env.def("Math", math);

  function step() {
    clock.n += 1;
    if (clock.n > cap) throw new Error("step_cap");
  }

  function callUser(fn, args) {
    const local = new Env(fn.closure);
    fn.params.forEach((name, i) => local.def(name, args[i]));
    try { exec(fn.body, local); }
    catch (err) {
      if (err instanceof Ret) return err.value;
      throw err;
    }
    return undefined;
  }

  function evalExpr(node, envNow) {
    step();
    switch (node.t) {
      case "num": return node.v;
      case "str": return node.v;
      case "bool": return node.v;
      case "ident":
        if (node.name === "t") clock.usesT = true;
        if (node.name === "undefined" && !envNow.find(node.name)) return undefined;
        return envNow.get(node.name);
      case "arr": return node.items.map((item) => evalExpr(item, envNow));
      case "unary": return evalUnary(node, envNow);
      case "bin": return evalBin(node, envNow);
      case "tern": return evalExpr(node.test, envNow) ? evalExpr(node.then, envNow) : evalExpr(node.els, envNow);
      case "assign": {
        const value = applyAssign(node.op, readLValue(node.left, envNow), evalExpr(node.right, envNow));
        writeLValue(node.left, value, envNow);
        return value;
      }
      case "member": return readMember(node, envNow);
      case "call": return evalCall(node, envNow);
      default: throw new Error("syntax:expr");
    }
  }

  function evalUnary(node, envNow) {
    if ((node.op === "++" || node.op === "--") && node.post) {
      const cur = readLValue(node.arg, envNow);
      writeLValue(node.arg, node.op === "++" ? cur + 1 : cur - 1, envNow);
      return cur;
    }
    if (node.op === "++" || node.op === "--") {
      const cur = readLValue(node.arg, envNow);
      const next = node.op === "++" ? cur + 1 : cur - 1;
      writeLValue(node.arg, next, envNow);
      return next;
    }
    const value = evalExpr(node.arg, envNow);
    if (node.op === "!") return !value;
    if (node.op === "-") return -value;
    if (node.op === "+") return +value;
    throw new Error("syntax:unary");
  }

  function evalBin(node, envNow) {
    const left = evalExpr(node.left, envNow);
    if (node.op === "&&") return left && evalExpr(node.right, envNow);
    if (node.op === "||") return left || evalExpr(node.right, envNow);
    const right = evalExpr(node.right, envNow);
    switch (node.op) {
      case "+": return left + right;
      case "-": return left - right;
      case "*": return left * right;
      case "/": return left / right;
      case "%": return left % right;
      case "===": return left === right;
      case "!==": return left !== right;
      case "<": return left < right;
      case ">": return left > right;
      case "<=": return left <= right;
      case ">=": return left >= right;
      default: throw new Error("syntax:op");
    }
  }

  function readMember(node, envNow) {
    const obj = evalExpr(node.object, envNow);
    const prop = node.computed ? evalExpr(node.prop, envNow) : node.prop;
    if (typeof prop === "string" && (prop === "constructor" || prop === "prototype" || prop === "__proto__")) {
      throw new Error("banned:member");
    }
    if (node.computed && typeof prop === "string") throw new Error("banned:computed");
    if (obj && obj.__kind === "math") {
      if (prop === "PI") return Math.PI;
      if (prop === "E") return Math.E;
      throw new Error("math:" + prop);
    }
    if (obj && obj.__kind === "ctx") {
      if (!PROP_SET.has(prop)) throw new Error("ctx:" + prop);
      return obj.api[prop];
    }
    if (Array.isArray(obj)) {
      if (prop === "length") return obj.length;
      if (prop === "push" || prop === "pop") return { __kind: "array-method", obj, prop };
      return obj[prop];
    }
    if (typeof obj === "string") {
      if (prop === "length") return obj.length;
      throw new Error("member");
    }
    if (obj === state) {
      reads.add(String(prop));
      return state[prop];
    }
    if (obj && obj.__kind === "fn") throw new Error("banned:member");
    throw new Error("member");
  }

  function evalCall(node, envNow) {
    if (node.callee.t === "member") {
      const obj = evalExpr(node.callee.object, envNow);
      const prop = node.callee.computed ? evalExpr(node.callee.prop, envNow) : node.callee.prop;
      const args = node.args.map((arg) => evalExpr(arg, envNow));
      if (typeof prop === "string" && (prop === "constructor" || prop === "prototype" || prop === "__proto__")) {
        throw new Error("banned:member");
      }
      if (node.callee.computed && typeof prop === "string") throw new Error("banned:computed");
      if (obj && obj.__kind === "math") {
        const fn = MATH_FN[prop];
        if (!fn || !MATH_SET.has(prop)) throw new Error("math:" + prop);
        return fn(...args);
      }
      if (obj && obj.__kind === "ctx") {
        if (!METHOD_SET.has(prop)) throw new Error("ctx:" + prop);
        return obj.api[prop](...args);
      }
      if (Array.isArray(obj) && prop === "push") return obj.push(...args);
      if (Array.isArray(obj) && prop === "pop") return obj.pop();
      if (typeof obj === "number" && prop === "toFixed") {
        const digits = args.length ? Math.max(0, Math.min(6, args[0] | 0)) : 0;
        return obj.toFixed(digits);
      }
      throw new Error("call");
    }
    const fn = evalExpr(node.callee, envNow);
    const args = node.args.map((arg) => evalExpr(arg, envNow));
    if (fn && fn.__kind === "fn") return callUser(fn, args);
    if (fn && fn.__kind === "array-method") {
      if (fn.prop === "push") return fn.obj.push(...args);
      return fn.obj.pop();
    }
    throw new Error("call");
  }

  function readLValue(node, envNow) {
    if (node.t === "ident") return envNow.get(node.name);
    if (node.t === "member") return readMember(node, envNow);
    throw new Error("syntax:lvalue");
  }

  function writeLValue(node, value, envNow) {
    if (node.t === "ident") { envNow.set(node.name, value); return; }
    if (node.t !== "member") throw new Error("syntax:lvalue");
    const obj = evalExpr(node.object, envNow);
    if (!node.computed) {
      if (obj && obj.__kind === "ctx" && PROP_SET.has(node.prop)) { obj.api[node.prop] = value; return; }
      throw new Error("assign");
    }
    const key = evalExpr(node.prop, envNow);
    if (typeof key === "string") throw new Error("banned:computed");
    if (!Array.isArray(obj)) throw new Error("assign");
    obj[key] = value;
  }

  function applyAssign(op, cur, value) {
    if (op === "=") return value;
    if (op === "+=") return cur + value;
    if (op === "-=") return cur - value;
    if (op === "*=") return cur * value;
    if (op === "/=") return cur / value;
    throw new Error("syntax:assign");
  }

  function exec(node, envNow) {
    step();
    switch (node.t) {
      case "block":
        for (const stmt of node.body) exec(stmt, envNow);
        return;
      case "var":
        for (const decl of node.decls) envNow.def(decl.name, decl.init ? evalExpr(decl.init, envNow) : undefined);
        return;
      case "fn":
        envNow.def(node.name, { __kind: "fn", params: node.params, body: node.body, closure: envNow });
        return;
      case "expr":
        evalExpr(node.value, envNow);
        return;
      case "empty":
        return;
      case "ret":
        throw new Ret(node.value ? evalExpr(node.value, envNow) : undefined);
      case "break":
        throw new Brk();
      case "continue":
        throw new Cont();
      case "if":
        if (evalExpr(node.test, envNow)) exec(node.then, envNow);
        else if (node.els) exec(node.els, envNow);
        return;
      case "while":
        while (evalExpr(node.test, envNow)) {
          try { exec(node.body, envNow); }
          catch (err) {
            if (err instanceof Brk) return;
            if (err instanceof Cont) continue;
            throw err;
          }
        }
        return;
      case "for":
        if (node.init) {
          if (node.init.t === "var") exec(node.init, envNow);
          else evalExpr(node.init, envNow);
        }
        while (!node.test || evalExpr(node.test, envNow)) {
          try { exec(node.body, envNow); }
          catch (err) {
            if (err instanceof Brk) return;
            if (!(err instanceof Cont)) throw err;
          }
          if (node.update) evalExpr(node.update, envNow);
        }
        return;
      default:
        throw new Error("syntax:stmt");
    }
  }

  try { callUser({ __kind: "fn", params: ast.params, body: ast.body, closure: env }, [ctx, state, t]); }
  catch (err) {
    if (err instanceof Ret) return { calls: stage.calls, reads, usesT: clock.usesT, steps: clock.n };
    throw err;
  }
  return { calls: stage.calls, reads, usesT: clock.usesT, steps: clock.n };
}

export function runDraw(source, state, t, cap) {
  return execute(parseDraw(source), state, Number(t) || 0, cap);
}
