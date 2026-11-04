// Static shape, allowlist, and a structural slop check.
// Semantic "does this teach the equation" stays with the model verifier.
import { HOST, KEYS_04, LIMITS, LIMITS_04, bannedIn, isV04, networkIn } from "./spec.js";
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

const CONTROL_CORE = ["id", "label", "max", "min", "step", "value"];
const CONTROL_EXTRA = new Set(["kind", "options", "prompt", "answer"]);
// 0.4 only (RRM-90): symbol and color of the variable, a hidden row (drag-only), toggle words, host reveal of a bet.
const CONTROL_EXTRA_04 = new Set(["tex", "color", "hidden", "on", "off", "reveal", "reveal_label"]);
const SERIES = new Set(["c1", "c2", "c3", "c4", "ref", "ink", "ink3"]);
const KINDS = new Set(["slider", "toggle", "select", "button", "play", "drag", "pick", "predict"]);
const DISCRETE = new Set(["toggle", "select", "button", "pick", "predict"]);

function controlShape(item, seen, v04) {
  if (!item || typeof item !== "object" || Array.isArray(item)) return true;
  const keys = Object.keys(item);
  if (!CONTROL_CORE.every((key) => keys.includes(key))) return true;
  if (keys.some((key) => !CONTROL_CORE.includes(key) && !CONTROL_EXTRA.has(key) && !(v04 && CONTROL_EXTRA_04.has(key)))) return true;
  if (v04 && item.color != null && !SERIES.has(item.color)) return true;
  if (v04 && item.tex != null && (typeof item.tex !== "string" || item.tex.length > 40)) return true;
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
  if (DISCRETE.has(kind) && aligned && steps >= 1 && steps <= 8) {
    const values = [];
    for (let i = 0; i <= steps; i += 1) values.push(control.min + i * control.step);
    return values;
  }
  if (kind === "drag") return [control.min, (control.min + control.max) / 2, control.max];
  return [control.min, control.max];
}

function text(value, hard) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= hard;
}

function setOk(widget, set) {
  if (!set || typeof set !== "object" || Array.isArray(set)) return false;
  const byId = new Map((widget.controls || []).map((c) => [c && c.id, c]));
  return Object.keys(set).length > 0 && Object.keys(set).every((id) => {
    const c = byId.get(id);
    return c && num(set[id]) && set[id] >= c.min && set[id] <= c.max;
  });
}

// 0.4 blocks (contract §3.1). Hard limits reject; the soft limits are the host's business.
function shape04(widget) {
  const errors = [];
  const L = LIMITS_04;
  const ids = new Set((widget.controls || []).map((c) => c && c.id));
  if (widget.hook != null && !(text(widget.hook, L.hook[1]) && widget.hook.trim().endsWith("?"))) errors.push("hook");
  if (widget.subtitle != null && !text(widget.subtitle, L.subtitle[1])) errors.push("subtitle");
  if (widget.aspect != null && !(num(widget.aspect) && widget.aspect >= 1 && widget.aspect <= 2.4)) errors.push("aspect");
  const readouts = widget.readouts || [];
  const rids = new Set();
  if (!Array.isArray(readouts) || readouts.length > L.readouts_max) errors.push("readouts");
  else for (const r of readouts) {
    if (!r || !ID_RE.test(r.id || "") || rids.has(r.id) || !text(r.label, L.readout[1])) { errors.push("readouts"); break; }
    if (r.color != null && !SERIES.has(r.color)) { errors.push("readouts"); break; }
    rids.add(r.id);
  }
  const legend = widget.legend || [];
  if (!Array.isArray(legend) || legend.length > L.legend_max || legend.some((g) => !g || !SERIES.has(g.color) || !text(g.text, L.legend[1]))) errors.push("legend");
  const areas = widget.areas || [];
  const aids = new Set();
  if (!Array.isArray(areas) || areas.length > L.areas_max) errors.push("areas");
  else for (const a of areas) {
    if (!a || !ID_RE.test(a.id || "") || aids.has(a.id)) { errors.push("areas"); break; }
    aids.add(a.id);
    // rect is [x, y, w, h] in fractions of the canvas (contract 0.4). Pixels put the area off the canvas: nothing shows.
    const frac = (r) => Array.isArray(r) && r.length === 4 && r.every((v) => num(v) && v >= 0 && v <= 1)
      && r[2] > 0 && r[3] > 0 && r[0] + r[2] <= 1.001 && r[1] + r[3] <= 1.001;
    const rectOk = (r) => r == null || frac(r) || (typeof r === "object" && !Array.isArray(r) && Object.values(r).length > 0 && Object.values(r).every(frac));
    if (!rectOk(a.rect)) { errors.push("areas"); break; }
    const axes = [a.x, a.y].filter(Boolean);
    if (axes.some((ax) => !(Array.isArray(ax.cats) ? ax.cats.length >= 2 && ax.cats.length <= 12 : num(ax.min) && num(ax.max) && ax.min < ax.max && (!ax.log || ax.min > 0)))) { errors.push("areas"); break; }
    if (axes.some((ax) => ax.label != null && !text(ax.label, L.label[1]))) { errors.push("areas"); break; }
  }
  const marks = widget.marks || [];
  if (!Array.isArray(marks) || marks.length > L.marks_max) errors.push("marks");
  else for (const m of marks) {
    const onControl = m && m.control != null;
    if (!m || !ID_RE.test(m.id || "") || (onControl ? !ids.has(m.control) : !aids.has(m.area || "main") && aids.size > 0) || (m.label != null && !text(m.label, L.label[1]))) { errors.push("marks"); break; }
  }
  const take = widget.takeaway;
  if (take != null) {
    const variants = typeof take === "string" ? [take] : take && typeof take === "object" && !Array.isArray(take) ? Object.values(take) : null;
    const known = new Set([...rids, ...ids]);
    if (!variants || !variants.length || variants.some((v) => !text(v, L.takeaway[1]) || (v.match(/\{(\w+)\}/g) || []).some((k) => !known.has(k.slice(1, -1))))) errors.push("takeaway");
  }
  const anchor = widget.anchor;
  if (anchor != null && typeof anchor === "object") {
    if (Array.isArray(anchor) || (anchor.latex != null && !text(anchor.latex, 500)) || (anchor.quote != null && !text(anchor.quote, L.quote[1])) || (anchor.abstract_quote != null && !text(anchor.abstract_quote, L.quote[1]))) errors.push("anchor");
    else if ((anchor.vars || []).some((v) => !v || typeof v.tex !== "string" || !(ids.has(v.control) || rids.has(v.readout)))) errors.push("anchor");
  }
  return errors;
}

export function shapeErrors(widget, opts = {}) {
  if (!widget || typeof widget !== "object" || Array.isArray(widget)) return ["not_object"];
  const errors = [];
  const v04 = isV04(widget);
  if (v04 && !opts.v04) return ["version"];
  if (widget.version != null && !v04) return ["version"];
  const allowed = ["id", "topic", "title", "explain", "questions", "controls", "draw", "equation", "anchor", "cite"].concat(v04 ? KEYS_04 : []);
  const extra = Object.keys(widget).filter((key) => !allowed.includes(key));
  if (extra.length) errors.push("extra_keys");
  if (v04) errors.push(...shape04(widget));
  if (widget.equation != null && (typeof widget.equation !== "string" || !widget.equation.trim() || widget.equation.length > 500)) errors.push("equation");
  if (widget.anchor != null && !(v04 && typeof widget.anchor === "object") && (typeof widget.anchor !== "string" || widget.anchor.length < 12 || widget.anchor.length > 400)) errors.push("anchor");
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
      if (!item || typeof item !== "object" || Object.keys(item).some((key) => key !== "q" && key !== "why" && !(v04 && key === "set"))) { errors.push("question"); break; }
      if (v04 && item.set != null && !setOk(widget, item.set)) { errors.push("question"); break; }
      if (typeof item.q !== "string" || item.q.length < 12 || item.q.length > LIMITS.question || !item.q.endsWith("?")) { errors.push("question"); break; }
      if (typeof item.why !== "string" || !item.why.trim() || item.why.length > LIMITS.why) { errors.push("question"); break; }
    }
  }
  const controls = widget.controls;
  if (!Array.isArray(controls) || controls.length < LIMITS.controls_min || controls.length > LIMITS.controls_max) errors.push("controls");
  else {
    const seen = new Set();
    for (const item of controls) {
      if (controlShape(item, seen, v04)) { errors.push("control"); break; }
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

function baseState(widget, patch, size) {
  const state = { w: size ? size[0] : HOST.canvas_w, h: size ? size[1] : HOST.canvas_h };
  for (const control of widget.controls) state[control.id] = control.value;
  return Object.assign(state, patch);
}

function reasonOf(err) {
  const msg = String(err && err.message || "");
  if (msg === "step_cap" || msg.startsWith("step_cap")) return "step_cap";
  if (msg.startsWith("banned") || msg.startsWith("math:") || msg.startsWith("ctx:") || msg.startsWith("ui:") || msg.startsWith("undeclared:")) return "banned";
  if (msg.startsWith("syntax")) return "syntax";
  return "throw";
}

function noted(err) {
  return String(err && err.message || "throw");
}

export function verifyWidget(widget, opts = {}) {
  const reasons = [];
  const detail = [];
  const v04 = !!opts.v04 && isV04(widget);
  const shape = shapeErrors(widget, opts);
  reasons.push(...shape);
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
  if (reasons.length) return finish(reasons, false, detail);

  let ast;
  try { ast = parseDraw(draw); }
  catch (err) { return finish([reasonOf(err)], false, [noted(err)]); }
  if ((ast.params.length === 4) !== v04) return finish(["version"], false, ["params:" + ast.params.join(",")]);
  const run = (state) => execute(ast, state, 0, HOST.step_cap, v04 ? { v04: true, widget } : undefined);

  let base;
  try { base = run(baseState(widget)); }
  catch (err) { return finish([reasonOf(err)], false, [noted(err)]); }
  if (!painted(base.calls)) reasons.push("blank");
  if (v04) frame04(widget, base.frame, reasons, detail);
  if (v04) {
    // R4: the same draw must hold on a phone-sized canvas.
    try { const small = run(baseState(widget, null, [358, 201])); frame04(widget, small.frame, [], detail, "small:"); }
    catch (err) { reasons.push(reasonOf(err)); detail.push("small:" + noted(err)); }
  }

  const controls = widget.controls || [];
  const readAny = controls.some((control) => base.reads.has(control.id));
  if (!readAny) reasons.push("dead_control");
  else {
    for (const control of controls) {
      if (!base.reads.has(control.id)) {
        if (control.kind === "play" && base.usesT) continue;
        if (v04 && control.kind === "predict" && control.reveal) {
          try {
            const shown = run(baseState(widget, control.reveal));
            if (!geometryChanged(base.calls, shown.calls, HOST.pixel_floor)) reasons.push("slop_inert:" + control.id);
          } catch (err) { reasons.push(reasonOf(err)); detail.push(noted(err)); }
          continue;
        }
        reasons.push("slop_inert:" + control.id);
        continue;
      }
      let prev = null;
      for (const value of sampleControl(control)) {
        try {
          const one = run(baseState(widget, { [control.id]: value }));
          if (!painted(one.calls)) reasons.push("blank");
          if (prev && !geometryChanged(prev, one.calls, HOST.pixel_floor)) reasons.push("slop_inert:" + control.id);
          if (v04) frame04(widget, one.frame, reasons, detail);
          prev = one.calls;
        } catch (err) {
          reasons.push(reasonOf(err));
          detail.push(noted(err));
          break;
        }
      }
    }
  }
  if (!claimLinked(widget, opts.claim || "")) reasons.push("slop_unrelated");
  return finish(reasons, base.usesT, detail);
}

// What a 0.4 frame reports back: no free text (R1), only declared readouts and takeaway variants.
// Dropped labels, marks out of range and cut text are notes, not rejections.
function frame04(widget, frame, reasons, detail, tag = "") {
  if (!frame) return;
  const rep = frame.report || {};
  if (rep.free_text) { reasons.push("free_text"); detail.push(tag + "free_text:" + rep.free_text); }
  const declared = new Set((widget.readouts || []).map((r) => r.id));
  for (const id of Object.keys(frame.readouts || {})) {
    if (!declared.has(id)) { reasons.push("readout"); detail.push(tag + "readout:" + id); }
    else if (!Number.isFinite(frame.readouts[id])) { reasons.push("readout"); detail.push(tag + "readout_nan:" + id); }
  }
  const take = widget.takeaway;
  if (frame.say != null && take && typeof take === "object" && !(frame.say in take)) { reasons.push("takeaway"); detail.push(tag + "say:" + frame.say); }
  for (const d of rep.dropped || []) detail.push(tag + "dropped:" + d.text);
  for (const m of rep.marks_out || []) detail.push(tag + "mark_out:" + m);
  for (const c of rep.cut || []) detail.push(tag + "cut:" + c.field);
  if (rep.over_budget) detail.push(tag + "over_budget:" + rep.over_budget);
}

function finish(reasons, usesT, detail) {
  const unique = [];
  for (const reason of reasons) if (!unique.includes(reason)) unique.push(reason);
  const notes = [];
  for (const item of detail || []) if (item && !notes.includes(item)) notes.push(item);
  return { accept: unique.length === 0, reasons: unique, usesT: Boolean(usesT), detail: notes };
}
