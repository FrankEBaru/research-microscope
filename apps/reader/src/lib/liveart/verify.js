// Static shape, allowlist, and a structural slop check.
// Semantic "does this teach the equation" stays with the model verifier.
import { HOST, LIMITS, VERSION_04, bannedIn, codeSurface, networkIn } from "./spec.js";
import { parseDraw } from "./parse.js";
import { execute, geometryChanged, painted } from "./run.js";
import { v04Shape } from "./v04.js";

const ID_RE = /^[a-z][a-z0-9_]{0,15}$/;
const TOPIC_RE = /^[a-z][a-z0-9_]{0,31}$/;
const WIDGET_ID_RE = /^[a-z0-9-]{1,40}$/;
const DRAW_RE = /^function draw\s*\(/;
const RESERVED = new Set(["w", "h", "t"]);
const STOP = new Set([
  "about", "after", "again", "their", "there", "which", "would", "could", "should",
  "where", "while", "these", "those", "using", "from", "with", "this", "that", "have",
  "into", "your", "they", "what", "when", "does", "each", "than", "then", "only", "also",
  "porque", "entre", "para", "como", "donde", "cuando",
]);

function num(value) {
  return typeof value === "number" && Number.isFinite(value);
}

const CONTROL_CORE = ["id", "label", "max", "min", "step", "value"];
const CONTROL_EXTRA = new Set(["kind", "options", "prompt", "answer"]);
const KINDS = new Set(["slider", "toggle", "select", "button", "play", "drag", "pick", "predict"]);
const DISCRETE = new Set(["toggle", "select", "button", "pick", "predict"]);

function controlShape(item, seen) {
  if (!item || typeof item !== "object" || Array.isArray(item)) return true;
  const keys = Object.keys(item);
  if (!CONTROL_CORE.every((key) => keys.includes(key))) return true;
  if (keys.some((key) => !CONTROL_CORE.includes(key) && !CONTROL_EXTRA.has(key))) return true;
  if (typeof item.id !== "string" || !ID_RE.test(item.id) || RESERVED.has(item.id) || seen.has(item.id)) return true;
  seen.add(item.id);
  if (typeof item.label !== "string" || !item.label.trim() || item.label.length > LIMITS.label) return true;
  if (![item.min, item.max, item.value, item.step].every(num) || !(item.min < item.max) || !(item.step > 0) || item.value < item.min || item.value > item.max) return true;
  const kind = item.kind == null ? "slider" : item.kind;
  if (!KINDS.has(kind)) return true;
  const steps = Math.round((item.max - item.min) / item.step);
  if (kind === "toggle" || kind === "play") {
    if (item.min !== 0 || item.max !== 1 || item.step !== 1) return true;
  }
  if (kind === "select" || kind === "predict") {
    if (!Array.isArray(item.options) || item.options.length < 2 || item.options.length > 4) return true;
    if (item.options.some((option) => typeof option !== "string" || !option.trim() || option.length > 40)) return true;
  }
  if (kind === "select" && (item.step !== 1 || steps + 1 !== item.options.length || steps > 8)) return true;
  if (kind === "predict") {
    if (item.min !== 0 || item.step !== 1 || item.max !== item.options.length || steps > 8) return true;
    if (item.prompt != null && (typeof item.prompt !== "string" || !item.prompt.trim() || item.prompt.length > 90)) return true;
    if (!num(item.answer) || item.answer < 1 || item.answer > item.max) return true;
  }
  if ((kind === "button" || kind === "pick") && (item.step !== 1 || steps > 8)) return true;
  return false;
}

function sampleControl(control) {
  const kind = control.kind || "slider";
  const steps = Math.round((control.max - control.min) / control.step);
  const aligned = Math.abs((control.max - control.min) / control.step - steps) < 1e-6;
  if ((DISCRETE.has(kind) || kind === "stepper") && aligned && steps >= 1 && steps <= 8) {
    const values = [];
    for (let i = 0; i <= steps; i += 1) values.push(control.min + i * control.step);
    return values;
  }
  if (kind === "drag") return [control.min, (control.min + control.max) / 2, control.max];
  return [control.min, control.max];
}

export function shapeErrors(widget) {
  if (!widget || typeof widget !== "object" || Array.isArray(widget)) return ["not_object"];
  const errors = [];
  const extra = Object.keys(widget).filter((key) => !["id", "topic", "title", "explain", "questions", "controls", "draw", "equation", "anchor", "cite"].includes(key));
  if (extra.length) errors.push("extra_keys");
  if (widget.equation != null && (typeof widget.equation !== "string" || !widget.equation.trim() || widget.equation.length > 500)) errors.push("equation");
  if (widget.anchor != null && (typeof widget.anchor !== "string" || widget.anchor.length < 12 || widget.anchor.length > 400)) errors.push("anchor");
  if (widget.cite != null && (typeof widget.cite !== "string" || widget.cite.length < 4 || widget.cite.length > 80)) errors.push("cite");
  if (typeof widget.topic !== "string" || !TOPIC_RE.test(widget.topic)) errors.push("topic");
  if (typeof widget.title !== "string" || !widget.title.trim() || widget.title.length > LIMITS.title) errors.push("title");
  if (typeof widget.explain !== "string" || !widget.explain.trim() || widget.explain.length > LIMITS.explain) errors.push("explain");
  if (typeof widget.draw !== "string" || !DRAW_RE.test(widget.draw.trim()) || widget.draw.length > LIMITS.draw) errors.push("draw");
  if (widget.id != null && (typeof widget.id !== "string" || !WIDGET_ID_RE.test(widget.id))) errors.push("id");
  const questions = widget.questions;
  if (!Array.isArray(questions) || questions.length < LIMITS.questions_min || questions.length > LIMITS.questions_max) errors.push("questions");
  else {
    for (const item of questions) {
      if (!item || typeof item !== "object" || Object.keys(item).some((key) => key !== "q" && key !== "why")) { errors.push("question"); break; }
      if (typeof item.q !== "string" || item.q.length < 12 || item.q.length > LIMITS.question || !item.q.endsWith("?")) { errors.push("question"); break; }
      if (typeof item.why !== "string" || !item.why.trim() || item.why.length > LIMITS.why) { errors.push("question"); break; }
    }
  }
  const controls = widget.controls;
  if (!Array.isArray(controls) || controls.length < LIMITS.controls_min || controls.length > LIMITS.controls_max) errors.push("controls");
  else {
    const seen = new Set();
    for (const item of controls) {
      if (controlShape(item, seen)) { errors.push("control"); break; }
    }
  }
  return errors;
}

function fold(text) {
  return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

// English cue in the claim, Spanish mark in the copy. Topic-gated so a reef claim still fails.
const LINKS = {
  positional_encoding: [["positional", "sinusoid", "10000", "cosine"], ["base", "onda"]],
  noise_schedule: [["noise", "gaussian", "beta"], ["ruido", "beta"]],
  guidance: [["guidance", "classifier-free", "unconditional"], ["guia"]],
  detr_match: [["hungarian", "bipartite", "matching"], ["emparej"]],
  residual: [["residual", "identity"], ["atajo"]],
  nucleus: [["nucleus", "top-p", "cumulative"], ["masa"]],
  gqa: [["grouped", "gqa"], ["grupo"]],
  label_smoothing: [["smoothing", "label"], ["suavizado"]],
  warmup: [["warmup", "learning rate"], ["calentamiento"]],
  alibi: [["alibi", "slope"], ["pendiente"]],
  adam: [["adam", "moment", "valley"], ["momento", "valle"]],
  batchnorm: [["batch", "normalization"], ["lote"]],
  distill_temp: [["distillation", "teacher", "temperature"], ["maestro", "temperatura"]],
  quant: [["absmax", "int8", "magnitude"], ["error", "paso"]],
};

function linkedPair(topic, claimFold, copy) {
  const pair = LINKS[topic];
  if (!pair) return false;
  const claimHit = pair[0].some((stem) => claimFold.includes(fold(stem)));
  const copyHit = pair[1].some((stem) => copy.includes(fold(stem)));
  return claimHit && copyHit;
}

function hasWord(hay, word) {
  if (!word || word.length < 3) return false;
  let from = 0;
  while (from <= hay.length - word.length) {
    const at = hay.indexOf(word, from);
    if (at < 0) return false;
    const before = at === 0 || !/[a-z0-9]/.test(hay[at - 1]);
    const after = at + word.length === hay.length || !/[a-z0-9]/.test(hay[at + word.length]);
    if (before && after) return true;
    from = at + 1;
  }
  return false;
}

export function claimLinked(widget, claim) {
  const raw = String(claim || "").trim();
  if (!raw) return true;
  const claimFold = fold(raw);
  const parts = String(widget.topic || "").split("_");
  const topicWords = parts.filter((word) => word.length >= 4);
  const shortTopic = parts.filter((word) => word.length === 3);
  const copy = fold([
    widget.title,
    widget.explain,
    ...(widget.questions || []).map((item) => `${item.q || ""} ${item.why || ""}`),
  ].join(" "));
  const topicInClaim = topicWords.some((word) => claimFold.includes(fold(word)))
    || shortTopic.some((word) => hasWord(claimFold, fold(word)));
  const topicInCopy = topicWords.some((word) => copy.includes(fold(word)))
    || shortTopic.some((word) => hasWord(copy, fold(word)));
  // Keep underscores so p_drop is one token in both languages.
  const tokens = claimFold.split(/[^a-z0-9_]+/).filter((token) => token.length >= 5 && !STOP.has(token));
  const tokenHit = tokens.some((token) => copy.includes(token));
  const nums = raw.match(/\d{3,}/g) || [];
  const hay = `${widget.title || ""}\n${widget.explain || ""}\n${widget.draw || ""}`;
  const numberHit = nums.some((n) => hay.includes(n));
  return (topicInClaim && topicInCopy) || tokenHit || numberHit || linkedPair(widget.topic, claimFold, copy);
}

const SEAL_RE = /verified|from the paper|✓|✔/i;

// Same instruction shapes as the prompt verifier. A linked formula does not excuse them.
const INJECT_RE = /ignore (?:all |any |the )?(?:previous|prior|above) instructions|olvida (?:las |tus )?instrucciones|ignora (?:las |tus )?instrucciones|system prompt|leak (?:the |your )?prompt|print (?:your |the )?(?:system )?prompt|you are now|<<<\s*system|\[system\]|verdict must be|responde(?:r)?\s+['"]?coincide|answer(?: with)?\s+['"]?coincide|fake system|merit must be|m[eé]rito debe ser|emit(?:e|ir)?\s+fetch|call fetch|<\s*script|javascript:|disregard (?:all |any |the )?(?:above|previous)|new instructions\s*:/i;

function injectionIn(text) {
  return INJECT_RE.test(String(text || ""));
}

function copyText(widget) {
  const parts = [widget && widget.title, widget && widget.explain, widget && widget.draw];
  for (const item of (widget && widget.questions) || []) {
    if (item && typeof item === "object") parts.push(item.q, item.why);
  }
  return parts.filter((part) => typeof part === "string").join("\n");
}

function sealIn(draw) {
  const re = /fillText\s*\(\s*(["'])([\s\S]*?)\1/g;
  let match;
  while ((match = re.exec(draw))) {
    if (SEAL_RE.test(match[2])) return true;
  }
  return false;
}

function baseState(widget, patch) {
  const state = { w: HOST.canvas_w, h: HOST.canvas_h };
  for (const control of widget.controls) state[control.id] = control.value;
  return Object.assign(state, patch);
}

function reasonOf(err) {
  const msg = String(err && err.message || "");
  if (msg === "step_cap" || msg.startsWith("step_cap")) return "step_cap";
  if (msg.startsWith("banned") || msg.startsWith("math:") || msg.startsWith("ctx:") || msg.startsWith("undeclared:")) return "banned";
  if (msg.startsWith("syntax")) return "syntax";
  return "throw";
}

function noted(err) {
  return String(err && err.message || "throw");
}

export function verifyWidget(widget, opts = {}) {
  const reasons = [];
  const detail = [];
  const notes = [];
  const v04 = Boolean(widget && widget.version === VERSION_04);
  if (v04) {
    const shaped = v04Shape(widget);
    reasons.push(...shaped.errors);
    notes.push(...shaped.notes);
  } else {
    reasons.push(...shapeErrors(widget));
  }
  let encoded = "";
  try { encoded = JSON.stringify(widget); } catch { reasons.push("size"); }
  if (encoded.length > HOST.json_chars) reasons.push("size");
  const draw = widget && typeof widget.draw === "string" ? widget.draw : "";
  if (bannedIn(draw).length || networkIn(widget)) {
    reasons.push("banned");
    for (const name of bannedIn(draw)) detail.push("banned:" + name);
    if (networkIn(widget)) detail.push("network");
  }
  if (sealIn(draw)) reasons.push("slop_seal");
  if (injectionIn(opts.claim) || injectionIn(copyText(widget))) reasons.push("injection");
  if (reasons.length) return finish(reasons, false, detail, notes);
  if (v04 && /\bfillText\s*\(/.test(codeSurface(draw))) notes.push("free_text");

  let ast;
  try { ast = parseDraw(draw); }
  catch (err) { return finish([reasonOf(err)], false, [noted(err)], notes); }

  let base;
  try { base = execute(ast, baseState(widget), 0, HOST.step_cap, widget); }
  catch (err) { return finish([reasonOf(err)], false, [noted(err)], notes); }
  if (!painted(base.calls)) reasons.push("blank");

  const controls = widget.controls || [];
  const readAny = controls.some((control) => base.reads.has(control.id));
  if (!readAny) reasons.push("dead_control");
  else {
    for (const control of controls) {
      if (!base.reads.has(control.id)) {
        if (control.kind === "play" && base.usesT) continue;
        reasons.push("slop_inert:" + control.id);
        continue;
      }
      let prev = null;
      for (const value of sampleControl(control)) {
        try {
          const run = execute(ast, baseState(widget, { [control.id]: value }), 0, HOST.step_cap, widget);
          if (!painted(run.calls)) reasons.push("blank");
          if (prev && !geometryChanged(prev, run.calls, HOST.pixel_floor)) reasons.push("slop_inert:" + control.id);
          prev = run.calls;
        } catch (err) {
          reasons.push(reasonOf(err));
          detail.push(noted(err));
          break;
        }
      }
    }
  }
  if (!claimLinked(widget, opts.claim || "")) reasons.push("slop_unrelated");
  const check = v04 && widget.predict && widget.predict.check;
  if (check && base.report) {
    let revealed;
    try {
      revealed = execute(ast, baseState(widget, widget.predict.reveal || {}), 0, HOST.step_cap, widget);
    } catch (err) {
      reasons.push(reasonOf(err));
      detail.push(noted(err));
    }
    const before = base.report.readouts[check.readout];
    const after = revealed && revealed.report ? revealed.report.readouts[check.readout] : undefined;
    const moved = check.expect === "down" ? after < before : check.expect === "up" ? after > before : after === before;
    if (typeof before !== "number" || typeof after !== "number" || !moved) reasons.push("predict");
  }
  return finish(reasons, base.usesT, detail, notes);
}

function finish(reasons, usesT, detail, notes) {
  const unique = [];
  for (const reason of reasons) if (!unique.includes(reason)) unique.push(reason);
  const seen = [];
  for (const item of detail || []) if (item && !seen.includes(item)) seen.push(item);
  const extra = [];
  for (const item of notes || []) if (item && !extra.includes(item)) extra.push(item);
  return { accept: unique.length === 0, reasons: unique, usesT: Boolean(usesT), detail: seen, notes: extra };
}
