import { knob, widget } from "./banks.js";

const GOLD_PE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base, i = state.dim;
  var freq = 1 / Math.pow(base, (2 * i) / 64);
  var x, pos, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.beginPath();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#1f4b99";
  for (x = 0; x < w; x++) {
    pos = (x / (w - 1)) * 64;
    y = h * 0.55 - Math.sin(pos * freq + t * 0.6) * (h * 0.32);
    if (x === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`;

const GOLD_TEMP = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, temp = state.temp;
  var logits = [1.2, 0.4, -0.2, -0.8];
  var name = ["sí", "no", "eh", "ya"];
  var i, m = logits[0], exps = [], s = 0, p, bw, bh, gap;
  if (temp < 0.05) temp = 0.05;
  for (i = 1; i < logits.length; i++) if (logits[i] > m) m = logits[i];
  for (i = 0; i < logits.length; i++) {
    exps[i] = Math.exp((logits[i] - m) / temp);
    s += exps[i];
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  gap = 12;
  bw = (w - gap * (logits.length + 1)) / logits.length;
  for (i = 0; i < logits.length; i++) {
    p = exps[i] / s;
    bh = p * (h - 36);
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(gap + i * (bw + gap), h - 22 - bh, bw, bh);
    ctx.fillStyle = "#1d1a16";
    ctx.font = "13px sans-serif";
    ctx.fillText(name[i], gap + i * (bw + gap) + 8, h - 6);
  }
}
`;

const GOLD_SCALE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, d = state.d;
  var raw = [1, 0.4, 0, -0.3];
  var s = Math.sqrt(d < 1 ? 1 : d);
  var grown = [], flat = [], i, gap, bw, x;
  function probs(xs) {
    var m = xs[0], k, out = [], acc = 0;
    for (k = 1; k < xs.length; k++) if (xs[k] > m) m = xs[k];
    for (k = 0; k < xs.length; k++) { out[k] = Math.exp(xs[k] - m); acc += out[k]; }
    for (k = 0; k < xs.length; k++) out[k] = out[k] / acc;
    return out;
  }
  for (i = 0; i < raw.length; i++) { grown[i] = raw[i] * s; flat[i] = raw[i]; }
  var top = probs(grown), bot = probs(flat);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#c4512c";
  ctx.fillText("sin raíz", 8, 16);
  ctx.fillStyle = "#1f4b99";
  ctx.fillText("con raíz", 8, h * 0.5);
  gap = 8;
  bw = (w - gap * (raw.length + 1)) / raw.length;
  for (i = 0; i < raw.length; i++) {
    x = gap + i * (bw + gap);
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(x, h * 0.42 - top[i] * (h * 0.30), bw, top[i] * (h * 0.30));
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(x, h * 0.92 - bot[i] * (h * 0.30), bw, bot[i] * (h * 0.30));
  }
}
`;

const GOLD_STD = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sigma = state.sigma;
  var pts = [-1.2, -0.4, 0.1, 0.8, 1.5];
  var mid = h * 0.55, band = sigma * 22, i, x, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9e3f5";
  ctx.fillRect(0, mid - band, w, band * 2);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(w, mid);
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  for (i = 0; i < pts.length; i++) {
    x = (i + 1) * w / (pts.length + 1);
    y = mid - pts[i] * sigma * 22;
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  }
}
`;

export const PRIMARY = [
  widget("positional_encoding", "positional-encoding", "La base cambia el ritmo de la onda", [
    knob("base", "base", 10, 100000, 10000, 10),
    knob("dim", "par i", 0, 8, 4, 1),
  ], GOLD_PE),
  widget("softmax_temperature", "softmax-temperature", "La temperatura afila el softmax", [
    knob("temp", "temperatura", 0.05, 5, 1, 0.05),
  ], GOLD_TEMP),
  widget("attention_scale", "attention-scale", "Dividir entre la raíz aplana el peso", [
    knob("d", "d_k", 4, 256, 64, 4),
  ], GOLD_SCALE),
  widget("stddev", "stddev", "Sigma es el ancho de la nube", [
    knob("sigma", "sigma", 0.25, 4, 1, 0.05),
  ], GOLD_STD),
  widget("rope", "rope", "La posición es un giro", [
    knob("theta", "paso", 0.05, 1.2, 0.35, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, th = state.theta;
  var ang = 4 * th, cx = w * 0.38, cy = h * 0.55;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#d9cbb8";
  ctx.beginPath();
  ctx.moveTo(cx - 70, cy); ctx.lineTo(cx + 70, cy);
  ctx.moveTo(cx, cy - 60); ctx.lineTo(cx, cy + 60);
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy); ctx.lineTo(cx + 64, cy);
  ctx.stroke();
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(ang) * 64, cy - Math.sin(ang) * 64);
  ctx.stroke();
}
`),
  widget("dpo_beta", "dpo-beta", "Beta empina el freno", [
    knob("beta", "beta", 0.2, 6, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, beta = state.beta;
  var i, gap, loss, x, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 80; i++) {
    gap = -2 + (i / 80) * 4;
    loss = -Math.log(1 / (1 + Math.exp(-beta * gap)) + 1e-6);
    x = 16 + (i / 80) * (w - 32);
    y = 16 + Math.min(h - 28, loss * 36);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`),
  widget("yarn_scale", "yarn-scale", "La escala estira las vueltas", [
    knob("scale", "escala", 1, 8, 2, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale;
  var i, x, y, pos;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 80; i++) {
    pos = (i / 80) * 32;
    x = 12 + (i / 80) * (w - 24);
    y = h * 0.55 - Math.sin(pos / s) * (h * 0.28);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`),
  widget("speculative", "speculative", "El borrador se acepta en racha", [
    knob("agree", "acuerdo", 0.05, 1, 0.55, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, a = state.agree;
  var n = 8, kept = Math.round(n * Math.min(1, a)), i, bw;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 40) / n;
  for (i = 0; i < n; i++) {
    var bh = i < kept ? 36 : 12;
    ctx.fillStyle = i < kept ? "#1f4b99" : "#c4512c";
    ctx.fillRect(16 + i * bw, h * 0.4 + (36 - bh), bw - 8, bh);
  }
}
`),
  widget("noise_schedule", "noise-schedule", "Beta decide cuánto ruido entra", [
    knob("beta", "beta", 0, 1, 0.25, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, b = state.beta;
  var signal = 1 - b, noise = b;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(w * 0.18, h * 0.8 - signal * (h * 0.55), 54, signal * (h * 0.55));
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.55, h * 0.8 - noise * (h * 0.55), 54, Math.max(2, noise * (h * 0.55)));
}
`),
  widget("guidance", "guidance", "La guía empuja hacia el texto", [
    knob("scale", "escala", 0, 3, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale;
  var x0 = w * 0.22, x1 = w * 0.58, y = h * 0.55;
  var x = x0 + s * (x1 - x0);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9cbb8";
  ctx.fillRect(x0 - 8, y - 8, 16, 16);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(x1 - 8, y - 8, 16, 16);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(Math.max(8, Math.min(w - 16, x)) - 7, y - 18, 14, 14);
}
`),
  widget("detr_match", "detr-match", "El peso de clase mueve el emparejamiento", [
    knob("class_w", "peso clase", 0, 1, 0.3, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, cw = state.class_w;
  var byClass = cw >= 0.5;
  var x1 = w * 0.22, x2 = w * 0.72, yb = h * 0.28, yq = h * 0.72;
  var target = byClass ? x2 : x1;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.strokeRect(x1, yb, 46, 32);
  ctx.strokeStyle = "#c4512c";
  ctx.strokeRect(x2, yb, 46, 32);
  ctx.fillStyle = "#1d1a16";
  ctx.fillRect(x1 + 12, yq, 18, 18);
  ctx.strokeStyle = "#1d1a16";
  ctx.beginPath();
  ctx.moveTo(x1 + 20, yq);
  ctx.lineTo(target + 23, yb + 32);
  ctx.stroke();
}
`),
  widget("residual", "residual", "El atajo deja pasar la entrada", [
    knob("skip", "atajo", 0, 1, 0.7, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, skip = state.skip;
  var x = [0.3, 0.8, 0.4, 0.6];
  var f = [0.9, 0.2, 0.7, 0.15];
  var i, mix, left;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  left = 28;
  for (i = 0; i < 4; i++) {
    mix = skip * x[i] + (1 - skip) * f[i];
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(left + i * (w / 5), h * 0.78 - mix * 90, 28, mix * 90);
  }
}
`),
  widget("nucleus", "nucleus", "p corta la masa, no un conteo fijo", [
    knob("p", "masa p", 0.2, 1, 0.8, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, p = state.p;
  var probs = [0.4, 0.22, 0.14, 0.09, 0.07, 0.05, 0.03];
  var i, mass = 0, keep = probs.length, bw;
  for (i = 0; i < probs.length; i++) {
    mass += probs[i];
    if (mass >= p) { keep = i + 1; break; }
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 30) / probs.length;
  for (i = 0; i < probs.length; i++) {
    var bh = i < keep ? probs[i] * (h * 0.9) : 4;
    ctx.fillStyle = i < keep ? "#1f4b99" : "#e4d8c8";
    ctx.fillRect(12 + i * bw, h * 0.82 - bh, bw - 8, bh);
  }
}
`),
  widget("contrastive_temp", "contrastive-temp", "Tau separa al positivo del lote", [
    knob("tau", "tau", 0.1, 2.5, 0.5, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau < 0.1 ? 0.1 : state.tau;
  var sims = [1.5, 0.35, 0.1, -0.2];
  var i, m = sims[0] / tau, exps = [], s = 0, bw;
  for (i = 1; i < sims.length; i++) if (sims[i] / tau > m) m = sims[i] / tau;
  for (i = 0; i < sims.length; i++) { exps[i] = Math.exp(sims[i] / tau - m); s += exps[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 40) / sims.length;
  for (i = 0; i < sims.length; i++) {
    var p = exps[i] / s;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(16 + i * bw, h * 0.84 - p * (h * 0.62), bw - 12, p * (h * 0.62));
  }
}
`),
];
