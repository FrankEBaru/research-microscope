// Static shape, allowlist, and a structural slop check.
// Semantic "does this teach the equation" stays with the model verifier.
import { HOST, LIMITS, bannedIn, networkIn } from "./spec.js";
import { parseDraw } from "./parse.js";
import { execute, geometryChanged, painted } from "./run.js";

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

export function shapeErrors(widget) {
  if (!widget || typeof widget !== "object" || Array.isArray(widget)) return ["not_object"];
  const errors = [];
  const extra = Object.keys(widget).filter((key) => !["id", "topic", "title", "explain", "questions", "controls", "draw"].includes(key));
  if (extra.length) errors.push("extra_keys");
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
      const keys = item && typeof item === "object" ? Object.keys(item).sort().join(",") : "";
      if (keys !== "id,label,max,min,step,value") { errors.push("control"); break; }
      if (typeof item.id !== "string" || !ID_RE.test(item.id) || RESERVED.has(item.id) || seen.has(item.id)) { errors.push("control"); break; }
      seen.add(item.id);
      if (typeof item.label !== "string" || !item.label.trim() || item.label.length > LIMITS.label) { errors.push("control"); break; }
      if (![item.min, item.max, item.value, item.step].every(num) || !(item.min < item.max) || !(item.step > 0) || item.value < item.min || item.value > item.max) {
        errors.push("control");
        break;
      }
    }
  }
  return errors;
}

function fold(text) {
  return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function claimLinked(widget, claim) {
  const raw = String(claim || "").trim();
  if (!raw) return true;
  const claimFold = fold(raw);
  const topicWords = String(widget.topic || "").split("_").filter((word) => word.length >= 4);
  const copy = fold([
    widget.title,
    widget.explain,
    ...(widget.questions || []).map((item) => `${item.q || ""} ${item.why || ""}`),
  ].join(" "));
  const topicInClaim = topicWords.some((word) => claimFold.includes(fold(word)));
  const topicInCopy = topicWords.some((word) => copy.includes(fold(word)));
  const tokens = claimFold.split(/[^a-z0-9]+/).filter((token) => token.length >= 5 && !STOP.has(token));
  const tokenHit = tokens.some((token) => copy.includes(token));
  const nums = raw.match(/\d{3,}/g) || [];
  const hay = `${widget.title || ""}\n${widget.explain || ""}\n${widget.draw || ""}`;
  const numberHit = nums.some((n) => hay.includes(n));
  return (topicInClaim && topicInCopy) || tokenHit || numberHit;
}

const SEAL_RE = /verified|from the paper|✓|✔/i;

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

export function verifyWidget(widget, opts = {}) {
  const reasons = [];
  const shape = shapeErrors(widget);
  reasons.push(...shape);
  let encoded = "";
  try { encoded = JSON.stringify(widget); } catch { reasons.push("size"); }
  if (encoded.length > HOST.json_chars) reasons.push("size");
  const draw = widget && typeof widget.draw === "string" ? widget.draw : "";
  if (bannedIn(draw).length || networkIn(widget)) reasons.push("banned");
  if (sealIn(draw)) reasons.push("slop_seal");
  if (reasons.length) return finish(reasons, false);

  let ast;
  try { ast = parseDraw(draw); }
  catch (err) { return finish([reasonOf(err)], false); }

  let base;
  try { base = execute(ast, baseState(widget), 0, HOST.step_cap); }
  catch (err) { return finish([reasonOf(err)], false); }
  if (!painted(base.calls)) reasons.push("blank");

  const controls = widget.controls || [];
  const readAny = controls.some((control) => base.reads.has(control.id));
  if (!readAny) reasons.push("dead_control");
  else {
    for (const control of controls) {
      if (!base.reads.has(control.id)) { reasons.push("slop_inert:" + control.id); continue; }
      try {
        const lo = execute(ast, baseState(widget, { [control.id]: control.min }), 0, HOST.step_cap);
        const hi = execute(ast, baseState(widget, { [control.id]: control.max }), 0, HOST.step_cap);
        if (!geometryChanged(lo.calls, hi.calls, HOST.pixel_floor)) reasons.push("slop_inert:" + control.id);
      } catch (err) {
        reasons.push(reasonOf(err));
      }
    }
  }
  if (!claimLinked(widget, opts.claim || "")) reasons.push("slop_unrelated");
  return finish(reasons, base.usesT);
}

function finish(reasons, usesT) {
  const unique = [];
  for (const reason of reasons) if (!unique.includes(reason)) unique.push(reason);
  return { accept: unique.length === 0, reasons: unique, usesT: Boolean(usesT) };
}
