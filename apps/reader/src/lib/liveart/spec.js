// Mirror of rrm/liveart/contract.py. The sandbox test fails if they drift.

export const VERSION = "rrm-widget/0.3";

// rrm-widget/0.4 (RRM-90). Off unless RRM_LIVEART_V04 is on. A widget without "version"
// stays 0.3: same keys, same 640x360 canvas, fillText allowed.
export const VERSION_04 = "rrm-widget/0.4";

// Optional 0.4 keys (all host HTML except draw). anchor may be an object (0.4) or the
// RRM-88 flat string; equation and cite are the RRM-88 aliases.
export const KEYS_04 = ["version", "hook", "subtitle", "aspect", "areas", "readouts", "marks", "legend", "takeaway", "anchor", "equation", "cite"];

// Soft / hard text limits (contract R6). Past soft the host shrinks a step; past hard it cuts.
export const LIMITS_04 = {
  hook: [60, 90],
  subtitle: [90, 135],
  takeaway: [100, 150],
  readout: [16, 24],
  legend: [16, 24],
  option: [14, 40],
  quote: [240, 400],
  label: [18, 28],
  readouts_max: 6,
  legend_max: 4,
  marks_max: 4,
  areas_max: 3,
  labels_per_frame: 3,
};

export const LIMITS = {
  draw: 8000,
  title: 80,
  explain: 420,
  question: 180,
  why: 160,
  label: 28,
  questions_min: 2,
  questions_max: 4,
  controls_min: 1,
  controls_max: 6,
};

export const HOST = {
  canvas_w: 640,
  canvas_h: 360,
  frame_ms: 1000,
  step_cap: 200000,
  json_chars: 20000,
  pixel_floor: 2,
};

export const CANVAS_METHODS = [
  "clearRect", "fillRect", "strokeRect", "beginPath", "closePath",
  "moveTo", "lineTo", "arc", "ellipse", "rect", "fill", "stroke",
  "fillText", "save", "restore", "translate", "rotate", "scale",
];

export const CANVAS_PROPS = [
  "fillStyle", "strokeStyle", "lineWidth", "font", "globalAlpha",
  "lineCap", "lineJoin", "textAlign", "textBaseline",
];

export const MATH_NAMES = [
  "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
  "exp", "log", "sqrt", "abs", "hypot", "sign",
  "min", "max", "pow", "floor", "ceil", "round",
  "PI", "E",
];

export const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'";

// Scripts run. The origin stays opaque, so the iframe cannot read the parent.
export const SANDBOX = "allow-scripts";

const BANNED = [
  ["fetch", /\bfetch\s*\(/],
  ["eval", /\beval\s*\(/],
  ["Function", /\bFunction\s*\(/],
  ["import", /\bimport\s*\(|\bimport\s+/],
  ["require", /\brequire\s*\(/],
  ["document", /\bdocument\b/],
  ["window", /\bwindow\b/],
  ["globalThis", /\bglobalThis\b/],
  ["localStorage", /\blocalStorage\b/],
  ["sessionStorage", /\bsessionStorage\b/],
  ["indexedDB", /\bindexedDB\b/],
  ["postMessage", /\bpostMessage\s*\(/],
  ["navigator", /\bnavigator\b/],
  ["location", /\blocation\b/],
  ["innerHTML", /\binnerHTML\b/],
  ["outerHTML", /\bouterHTML\b/],
  ["setTimeout", /\bsetTimeout\s*\(/],
  ["setInterval", /\bsetInterval\s*\(/],
  ["requestAnimationFrame", /\brequestAnimationFrame\s*\(/],
  ["Math.random", /Math\.random\s*\(/],
  ["Date", /\bDate\b/],
  ["performance", /\bperformance\b/],
  ["WebSocket", /\bWebSocket\b/],
  ["XMLHttpRequest", /\bXMLHttpRequest\b/],
  ["WebAssembly", /\bWebAssembly\b/],
  ["Worker", /\bWorker\b/],
  ["SharedArrayBuffer", /\bSharedArrayBuffer\b/],
  ["atob", /\batob\s*\(/],
  ["btoa", /\bbtoa\s*\(/],
  ["cookie", /\bcookie\b/],
  ["http", /https?:\/\//],
  ["ws", /\bwss?:\/\//],
  ["__proto__", /__proto__/],
  ["constructor", /\bconstructor\b/],
  ["process", /\bprocess\./],
  ["child_process", /child_process/],
];

const NETWORK = /https?:\/\/|\bwss?:\/\/|\bfetch\s*\(|\beval\s*\(/i;

function flagOn(raw) {
  const text = String(raw || "").trim().toLowerCase();
  return text === "1" || text === "true" || text === "yes" || text === "on";
}

export function v04On(env) {
  if (env) return flagOn(env.RRM_LIVEART_V04) || flagOn(env.NEXT_PUBLIC_RRM_LIVEART_V04);
  return flagOn(process.env.RRM_LIVEART_V04) || flagOn(process.env.NEXT_PUBLIC_RRM_LIVEART_V04);
}

export function isV04(widget) {
  return !!widget && widget.version === VERSION_04;
}

export function liveOn(env) {
  // Static names so the client bundle inlines NEXT_PUBLIC_*. A dynamic key stays empty in the browser.
  if (env) return flagOn(env.RRM_LIVE_ARTIFACTS) || flagOn(env.NEXT_PUBLIC_RRM_LIVE_ARTIFACTS);
  return flagOn(process.env.RRM_LIVE_ARTIFACTS) || flagOn(process.env.NEXT_PUBLIC_RRM_LIVE_ARTIFACTS);
}

// Identifiers are banned in code. Words inside a string, a comment, or a text field are not code.
export function codeSurface(src) {
  const text = src || "";
  let out = "";
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (c === "/" && text[i + 1] === "/") {
      const start = i;
      i += 2;
      while (i < n && text[i] !== "\n") i += 1;
      out += " ".repeat(i - start);
      continue;
    }
    if (c === "/" && text[i + 1] === "*") {
      const start = i;
      i += 2;
      let closed = false;
      while (i < n) {
        if (text[i] === "*" && text[i + 1] === "/") { i += 2; closed = true; break; }
        i += 1;
      }
      if (!closed) { out += text.slice(start); break; }
      out += " ".repeat(i - start);
      continue;
    }
    if (c === '"' || c === "'") {
      const q = c;
      let j = i + 1;
      let closed = false;
      while (j < n) {
        if (text[j] === "\\") { j += 2; continue; }
        if (text[j] === "\n") break;
        if (text[j] === q) { j += 1; closed = true; break; }
        j += 1;
      }
      if (!closed) { out += text[i]; i += 1; continue; }
      out += " ".repeat(j - i);
      i = j;
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

export function bannedIn(draw) {
  const text = codeSurface(draw);
  return BANNED.filter(([, cre]) => cre.test(text)).map(([name]) => name);
}

export function networkIn(value) {
  if (typeof value === "string") return NETWORK.test(value);
  if (Array.isArray(value)) return value.some(networkIn);
  if (value && typeof value === "object") return Object.values(value).some(networkIn);
  return false;
}
