// rrm-widget/0.3. Numbers match RRM-79 (apps/reader/src/lib/liveart/spec.js).
// This harness still checks shape and pixels. RRM-79 owns the iframe and the AST.

export const CONTRACT_VERSION = "rrm-widget/0.3";

export const LIMITS = {
  draw: 8000,
  title: 80,
  explain: 420,
  question: 180,
  why: 160,
  label: 28,
  questionsMin: 2,
  questionsMax: 4,
  controlsMin: 1,
  controlsMax: 6,
};

export const RESERVED_IDS = new Set(["w", "h", "t"]);

export const TOPICS = {
  yarn_scale: { controls: ["scale"], mark: "escala" },
  contrastive_temp: { controls: ["tau"], mark: "temperatura" },
  attention_scale: { controls: ["d"], mark: "raíz" },
  dpo_beta: { controls: ["beta"], mark: "beta" },
  positional_encoding: { controls: ["base", "dim"], mark: "base" },
  softmax_temperature: { controls: ["temp"], mark: "temperatura" },
  stddev: { controls: ["sigma"], mark: "desviación" },
  rope: { controls: ["theta", "shift"], mark: "gira" },
  speculative: { controls: ["agree"], mark: "borrador" },
  noise_schedule: { controls: ["beta"], mark: "ruido" },
  guidance: { controls: ["scale"], mark: "guía" },
  detr_match: { controls: ["class_w"], mark: "emparej" },
  residual: { controls: ["skip"], mark: "atajo" },
  nucleus: { controls: ["p"], mark: "masa" },
  // Ids from the 0.2 delta in compass CONTRACT.md. Marks stay local where 0.2
  // names the topic but not the mark word.
  adam: { controls: ["lr"], mark: "momento" },
  lora: { controls: ["rank"], mark: "rango" },
  kl_rlhf: { controls: ["beta"], mark: "kl" },
  beam: { controls: ["width"], mark: "haz" },
  batchnorm: { controls: ["scale"], mark: "lote" },
  chinchilla: { controls: ["logc"], mark: "datos" },
  online_softmax: { controls: ["blocks"], mark: "exacto" },
  spec_cost: { controls: ["cost"], mark: "costo" },
  gqa: { controls: ["kv"], mark: "grupo" },
  moe: { controls: ["k"], mark: "expertos" },
  // No 0.2 id yet. The selector should stay static until one exists.
  quant: { controls: ["mag"], mark: "error" },
};

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

const ID_RE = /^[a-z][a-z0-9_]{0,15}$/;
const DRAW_RE = /^function draw\s*\(/;
const WIDGET_ID_RE = /^[a-z0-9-]{1,40}$/;

function num(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function liveOn(env = process.env.NEXT_PUBLIC_RRM_LIVE_ARTIFACTS) {
  return /^(1|true|yes|on)$/i.test(String(env || "").trim());
}

export function bannedIn(draw) {
  const text = String(draw || "");
  return BANNED.filter(([, re]) => re.test(text)).map(([name]) => name);
}

export function shapeErrors(widget) {
  if (!widget || typeof widget !== "object") return ["not_object"];
  const errors = [];
  const extra = Object.keys(widget).filter((key) => !["id", "topic", "title", "explain", "questions", "controls", "draw"].includes(key));
  if (extra.length) errors.push("extra_keys");
  if (!TOPICS[widget.topic]) errors.push("topic");
  if (typeof widget.title !== "string" || !widget.title.trim() || widget.title.length > LIMITS.title) errors.push("title");
  if (typeof widget.explain !== "string" || !widget.explain.trim() || widget.explain.length > LIMITS.explain) errors.push("explain");
  if (typeof widget.draw !== "string" || !DRAW_RE.test(widget.draw.trim()) || widget.draw.length > LIMITS.draw) errors.push("draw");
  if (widget.id != null && (typeof widget.id !== "string" || !WIDGET_ID_RE.test(widget.id))) errors.push("id");
  const questions = widget.questions;
  if (!Array.isArray(questions) || questions.length < LIMITS.questionsMin || questions.length > LIMITS.questionsMax) errors.push("questions");
  else {
    for (const item of questions) {
      if (!item || typeof item !== "object" || Object.keys(item).some((key) => key !== "q" && key !== "why")) {
        errors.push("question");
        break;
      }
      if (typeof item.q !== "string" || item.q.length < 12 || item.q.length > LIMITS.question || !item.q.endsWith("?")) {
        errors.push("question");
        break;
      }
      if (typeof item.why !== "string" || !item.why.trim() || item.why.length > LIMITS.why) {
        errors.push("question");
        break;
      }
    }
  }
  const controls = widget.controls;
  if (!Array.isArray(controls) || controls.length < LIMITS.controlsMin || controls.length > LIMITS.controlsMax) errors.push("controls");
  else {
    const seen = new Set();
    for (const item of controls) {
      const keys = item && typeof item === "object" ? Object.keys(item).sort().join(",") : "";
      if (keys !== "id,label,max,min,step,value") {
        errors.push("control");
        break;
      }
      if (typeof item.id !== "string" || !ID_RE.test(item.id) || RESERVED_IDS.has(item.id) || seen.has(item.id)) {
        errors.push("control");
        break;
      }
      seen.add(item.id);
      if (typeof item.label !== "string" || !item.label.trim() || item.label.length > LIMITS.label) {
        errors.push("control");
        break;
      }
      if (![item.min, item.max, item.value, item.step].every(num) || !(item.min < item.max) || !(item.step > 0) || item.value < item.min || item.value > item.max) {
        errors.push("control");
        break;
      }
    }
  }
  const spec = TOPICS[widget.topic];
  if (spec) {
    const ids = new Set((controls || []).map((item) => item && item.id));
    if (!spec.controls.some((id) => ids.has(id))) errors.push("off_claim");
    if (typeof widget.explain === "string" && !widget.explain.toLowerCase().includes(spec.mark)) errors.push("off_claim");
  }
  return errors;
}
