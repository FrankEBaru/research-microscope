// Mirror of rrm/liveart/contract.py. The sandbox test fails if they drift.

export const VERSION = "rrm-widget/0.3";

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

export function liveOn(env) {
  const bag = env || (typeof process !== "undefined" ? process.env : {});
  for (const key of ["RRM_LIVE_ARTIFACTS", "NEXT_PUBLIC_RRM_LIVE_ARTIFACTS"]) {
    const raw = String(bag[key] || "").trim().toLowerCase();
    if (raw === "1" || raw === "true" || raw === "yes" || raw === "on") return true;
  }
  return false;
}

export function bannedIn(draw) {
  const text = draw || "";
  return BANNED.filter(([, cre]) => cre.test(text)).map(([name]) => name);
}

export function networkIn(value) {
  if (typeof value === "string") return NETWORK.test(value);
  if (Array.isArray(value)) return value.some(networkIn);
  if (value && typeof value === "object") return Object.values(value).some(networkIn);
  return false;
}
