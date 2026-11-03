// Shape check for rrm-widget/0.4. 0.3 stays in verify.js and does not call this.
import { VERSION_04, v04On } from "./spec.js";

const ID_RE = /^[a-z][a-z0-9_]{0,15}$/;
const TOPIC_RE = /^[a-z][a-z0-9_]{0,31}$/;
const WIDGET_ID_RE = /^[a-z0-9-]{1,40}$/;
const DRAW_RE = /^function draw\s*\(/;
const RESERVED = new Set(["w", "h", "t"]);
const KEYS = new Set([
  "id", "topic", "title", "explain", "questions", "controls", "draw",
  "equation", "anchor", "cite", "version", "hook", "aspect", "predict",
  "areas", "readouts", "marks", "legend", "takeaway",
]);
const CONTROL_KEYS = new Set([
  "id", "label", "min", "max", "step", "value", "kind", "type", "options",
  "prompt", "answer", "tex", "color", "hidden", "on", "off", "steps", "play",
]);
const KINDS = new Set(["slider", "toggle", "select", "button", "stepper", "play", "drag", "pick", "predict"]);
const COLORS = new Set(["c1", "c2", "c3", "c4", "ref"]);
const QUESTION_KEYS = new Set(["q", "why", "set"]);

function num(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function note(notes, field, text, soft, hard) {
  const len = String(text || "").length;
  if (len > hard) return field;
  if (len > soft) notes.push("shrink:" + field);
  return "";
}

function controlError(item, seen) {
  if (!item || typeof item !== "object" || Array.isArray(item)) return true;
  const keys = Object.keys(item);
  if (!["id", "label", "min", "max", "step", "value"].every((key) => keys.includes(key))) return true;
  if (keys.some((key) => !CONTROL_KEYS.has(key))) return true;
  if (typeof item.id !== "string" || !ID_RE.test(item.id) || RESERVED.has(item.id) || seen.has(item.id)) return true;
  seen.add(item.id);
  if (typeof item.label !== "string" || !item.label.trim() || item.label.length > 28) return true;
  if (![item.min, item.max, item.value, item.step].every(num) || !(item.min < item.max) || !(item.step > 0)) return true;
  if (item.value < item.min || item.value > item.max) return true;
  const kind = item.kind || item.type || "slider";
  if (!KINDS.has(kind)) return true;
  if (item.color != null && !COLORS.has(item.color)) return true;
  if (item.hidden != null && typeof item.hidden !== "boolean") return true;
  if (item.tex != null && (typeof item.tex !== "string" || item.tex.length > 40)) return true;
  const steps = Math.round((item.max - item.min) / item.step);
  if (kind === "toggle" || kind === "play") {
    if (item.min !== 0 || item.max !== 1 || item.step !== 1) return true;
  }
  if (kind === "select" || kind === "predict") {
    if (!Array.isArray(item.options) || item.options.length < 2 || item.options.length > 4) return true;
    if (item.options.some((option) => typeof option !== "string" || !option.trim() || option.length > 24)) return true;
  }
  if (kind === "select" && (item.step !== 1 || steps + 1 !== item.options.length || steps > 8)) return true;
  if (kind === "stepper" && (item.step !== 1 || steps > 16)) return true;
  if ((kind === "button" || kind === "pick") && (item.step !== 1 || steps > 16)) return true;
  return false;
}

function anchorError(anchor, notes) {
  if (typeof anchor === "string") return anchor.length < 12 || anchor.length > 400;
  if (!anchor || typeof anchor !== "object" || Array.isArray(anchor)) return true;
  if (typeof anchor.latex !== "string" || !anchor.latex.trim() || anchor.latex.length > 800) return true;
  if (typeof anchor.quote !== "string" || !anchor.quote.trim()) return true;
  const over = note(notes, "quote", anchor.quote, 240, 360);
  if (over) return true;
  if (anchor.vars != null) {
    if (!Array.isArray(anchor.vars) || anchor.vars.length > 8) return true;
    for (const item of anchor.vars) {
      if (!item || typeof item.tex !== "string" || !item.tex.trim()) return true;
      if (item.control != null && typeof item.control !== "string") return true;
      if (item.readout != null && typeof item.readout !== "string") return true;
    }
  }
  for (const key of ["passage_id", "arxiv", "section", "eq", "abstract_quote"]) {
    if (anchor[key] != null && typeof anchor[key] !== "string") return true;
  }
  notes.push(anchor.passage_id ? "anchor_unchecked" : "anchor_unchecked");
  return false;
}

function takeawayError(value, ids, notes) {
  const texts = typeof value === "string"
    ? [["takeaway", value]]
    : value && typeof value === "object" && !Array.isArray(value)
      ? Object.entries(value).filter(([, text]) => typeof text === "string")
      : null;
  if (!texts || !texts.length) return true;
  for (const [name, text] of texts) {
    if (note(notes, "takeaway", text, 100, 150)) return true;
    const holes = String(text).match(/\{([^{}]+)\}/g) || [];
    for (const hole of holes) {
      const id = hole.slice(1, -1);
      if (!ids.has(id)) return true;
    }
    if (name !== "takeaway" && typeof name !== "string") return true;
  }
  return false;
}

export function v04Shape(widget) {
  if (!v04On()) return { errors: ["v04_off"], notes: [] };
  const notes = [];
  const errors = [];
  if (!widget || typeof widget !== "object" || Array.isArray(widget)) return { errors: ["not_object"], notes };
  if (widget.version !== VERSION_04) errors.push("version");
  if (Object.keys(widget).some((key) => !KEYS.has(key))) errors.push("extra_keys");
  if (typeof widget.topic !== "string" || !TOPIC_RE.test(widget.topic)) errors.push("topic");
  if (typeof widget.title !== "string" || !widget.title.trim() || note(notes, "title", widget.title, 60, 90)) errors.push("title");
  if (typeof widget.explain !== "string" || !widget.explain.trim() || note(notes, "explain", widget.explain, 240, 420)) errors.push("explain");
  if (typeof widget.draw !== "string" || !DRAW_RE.test(widget.draw.trim()) || widget.draw.length > 8000) errors.push("draw");
  if (widget.id != null && (typeof widget.id !== "string" || !WIDGET_ID_RE.test(widget.id))) errors.push("id");
  if (widget.hook != null && (typeof widget.hook !== "string" || note(notes, "hook", widget.hook, 60, 90))) errors.push("hook");
  if (widget.aspect != null && (!num(widget.aspect) || widget.aspect < 0.5 || widget.aspect > 3)) errors.push("aspect");
  if (widget.equation != null && (typeof widget.equation !== "string" || !widget.equation.trim() || widget.equation.length > 500)) errors.push("equation");
  if (widget.cite != null && (typeof widget.cite !== "string" || widget.cite.length < 4 || widget.cite.length > 80)) errors.push("cite");
  if (widget.anchor != null && anchorError(widget.anchor, notes)) errors.push("anchor");

  const questions = widget.questions;
  if (!Array.isArray(questions) || questions.length < 2 || questions.length > 4) errors.push("questions");
  else {
    for (const item of questions) {
      if (!item || typeof item !== "object" || Object.keys(item).some((key) => !QUESTION_KEYS.has(key))) {
        errors.push("question");
        break;
      }
      if (typeof item.q !== "string" || item.q.length < 12 || note(notes, "question", item.q, 90, 135) || !item.q.endsWith("?")) {
        errors.push("question");
        break;
      }
      if (typeof item.why !== "string" || !item.why.trim() || note(notes, "why", item.why, 140, 180)) {
        errors.push("question");
        break;
      }
    }
  }

  const ids = new Set();
  const controls = widget.controls;
  if (!Array.isArray(controls) || controls.length < 1 || controls.length > 6) errors.push("controls");
  else {
    const seen = new Set();
    for (const item of controls) {
      if (controlError(item, seen)) {
        errors.push("control");
        break;
      }
      ids.add(item.id);
    }
  }

  if (widget.predict != null) {
    const predict = widget.predict;
    const options = predict && predict.options;
    if (!predict || typeof predict !== "object" || !Array.isArray(options) || options.length < 2 || options.length > 4) errors.push("predict");
    else if (!num(predict.answer) || predict.answer < 0 || predict.answer >= options.length) errors.push("predict");
    else if (predict.check && (typeof predict.check.readout !== "string" || !["up", "down", "flat"].includes(predict.check.expect))) errors.push("predict");
    if (predict && predict.reveal && typeof predict.reveal === "object") {
      for (const key of Object.keys(predict.reveal)) ids.add(key);
    }
  }

  if (widget.areas != null) {
    if (!Array.isArray(widget.areas) || widget.areas.length < 1 || widget.areas.length > 3) errors.push("areas");
    else if (widget.areas.some((area) => !area || typeof area.id !== "string" || !ID_RE.test(area.id))) errors.push("areas");
  }
  if (widget.readouts != null) {
    if (!Array.isArray(widget.readouts) || widget.readouts.length > 6) errors.push("readouts");
    else {
      for (const item of widget.readouts) {
        if (!item || typeof item.id !== "string" || !ID_RE.test(item.id)) {
          errors.push("readouts");
          break;
        }
        ids.add(item.id);
        if (typeof item.label === "string" && note(notes, "readout", item.label, 16, 24)) {
          errors.push("readouts");
          break;
        }
      }
    }
  }
  if (widget.marks != null && (!Array.isArray(widget.marks) || widget.marks.length > 8)) errors.push("marks");
  if (widget.legend != null) {
    if (!Array.isArray(widget.legend) || widget.legend.length > 6) errors.push("legend");
    else if (widget.legend.some((item) => !item || typeof item.text !== "string" || item.text.length > 24)) errors.push("legend");
  }
  if (widget.takeaway != null && takeawayError(widget.takeaway, ids, notes)) errors.push("takeaway");
  return { errors, notes };
}
