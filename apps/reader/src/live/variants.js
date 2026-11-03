import { knob, widget } from "./banks.js";

export const VARIANTS = [
  widget("positional_encoding", "pe-heatmap", "La base abre las ondas lentas", [
    knob("base", "base", 10, 100000, 10000, 10),
    knob("dim", "par i", 0, 8, 2, 1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base;
  var row, col, rows = 8, cols = 24, cellW, cellH, pos, freq, v;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  cellW = (w - 16) / cols;
  cellH = (h - 16) / rows;
  for (row = 0; row < rows; row++) {
    freq = 1 / Math.pow(base, (2 * row) / 64);
    for (col = 0; col < cols; col++) {
      pos = col * 2;
      v = (Math.sin(pos * freq) + 1) / 2;
      ctx.fillStyle = v > 0.5 ? "#1f4b99" : "#eadfce";
      ctx.fillRect(8 + col * cellW, 8 + row * cellH, cellW - 2, cellH - 2);
    }
  }
}
`),
  widget("positional_encoding", "pe-offset", "El desfase se lee en el producto", [
    knob("base", "base", 10, 10000, 1000, 10),
    knob("dim", "par i", 1, 6, 2, 1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base, dim = state.dim;
  var k, s, a, b, i, div, x, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (k = 0; k <= 24; k++) {
    s = 0;
    for (i = 0; i < dim; i++) {
      div = Math.pow(base, (2 * i) / 32);
      a = Math.sin(8 / div); b = Math.sin((8 + k) / div);
      s += a * b + Math.cos(8 / div) * Math.cos((8 + k) / div);
    }
    x = 16 + (k / 24) * (w - 32);
    y = h * 0.75 - (s / dim) * (h * 0.4);
    if (k === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`),
  widget("softmax_temperature", "temp-entropy", "La temperatura sube la entropía", [
    knob("temp", "temperatura", 0.2, 4, 1, 0.05),
  ], `
function draw(ctx, state, t) {
  var temp = state.temp < 0.2 ? 0.2 : state.temp;
  var logits = [2, 0.6, 0, -0.5], i, m = logits[0], exps = [], s = 0, ent = 0, p;
  var w = state.w, h = state.h, bw;
  for (i = 1; i < 4; i++) if (logits[i] > m) m = logits[i];
  for (i = 0; i < 4; i++) { exps[i] = Math.exp((logits[i] - m) / temp); s += exps[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w * 0.5) / 4;
  for (i = 0; i < 4; i++) {
    p = exps[i] / s;
    if (p > 1e-8) ent -= p * Math.log(p);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(16 + i * bw, h * 0.8 - p * (h * 0.55), bw - 8, p * (h * 0.55));
  }
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.72, h * 0.8 - ent * 40, 36, ent * 40);
}
`),
  widget("softmax_temperature", "temp-two", "Dos opciones y una temperatura", [
    knob("temp", "temperatura", 0.15, 3, 0.7, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, temp = state.temp;
  var a = Math.exp(1.1 / temp), b = Math.exp(0.2 / temp), p = a / (a + b);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - p * (h * 0.6), 70, p * (h * 0.6));
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(160, h * 0.8 - (1 - p) * (h * 0.6), 70, (1 - p) * (h * 0.6));
}
`),
  widget("attention_scale", "scale-cloud", "Sin raíz la nube se abre con d", [
    knob("d", "d_k", 1, 36, 4, 1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, d = Math.round(state.d);
  var i, s, x, seed = 7, u;
  function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#d9cbb8";
  ctx.beginPath(); ctx.moveTo(10, h * 0.5); ctx.lineTo(w - 10, h * 0.5); ctx.stroke();
  ctx.fillStyle = "#1f4b99";
  for (s = 0; s < 24; s++) {
    u = 0;
    for (i = 0; i < d; i++) u += rnd() * 2 - 1;
    x = w * 0.5 + u * 6;
    ctx.fillRect(Math.max(4, Math.min(w - 6, x)), h * 0.42, 3, 18);
  }
}
`),
  widget("attention_scale", "scale-peak", "El pico crudo crece con d", [
    knob("d", "d_k", 4, 128, 16, 4),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, d = state.d;
  var raw = [1, 0.2, -0.2], s = Math.sqrt(d), i, m = -1e9, exps = [], acc = 0, p, peak = 0;
  for (i = 0; i < 3; i++) if (raw[i] * s > m) m = raw[i] * s;
  for (i = 0; i < 3; i++) { exps[i] = Math.exp(raw[i] * s - m); acc += exps[i]; }
  for (i = 0; i < 3; i++) { p = exps[i] / acc; if (p > peak) peak = p; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.3, h * 0.8 - peak * (h * 0.6), 80, peak * (h * 0.6));
}
`),
  widget("stddev", "std-z", "Sigma chico agranda el z", [
    knob("sigma", "sigma", 0.4, 3, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sigma = state.sigma, z = 2 / sigma;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - 40, 40, 40);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(140, h * 0.8 - Math.min(z, 5) * 22, 40, Math.min(z, 5) * 22);
}
`),
  widget("stddev", "std-bars", "Dividir entre sigma iguala la escala", [
    knob("sigma", "sigma", 0.5, 3, 1.4, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sigma = state.sigma;
  var xs = [-1.2, -0.3, 0.4, 1.1], i, raw, norm;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 4; i++) {
    raw = Math.abs(xs[i]) * sigma;
    norm = Math.abs(xs[i]);
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(24 + i * (w / 5), h * 0.42 - raw * 18, 16, raw * 18);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(44 + i * (w / 5), h * 0.88 - norm * 28, 16, norm * 28);
  }
}
`),
  widget("rope", "rope-pairs", "Cada par gira a su paso", [
    knob("theta", "paso", 0.1, 2, 0.6, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, th = state.theta, i, ang, cx, cy;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  cy = h * 0.55;
  for (i = 0; i < 5; i++) {
    ang = th / Math.pow(8, i / 4);
    cx = 36 + i * ((w - 40) / 5);
    ctx.strokeStyle = "#1f4b99";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(ang) * 22, cy - Math.sin(ang) * 22);
    ctx.stroke();
  }
}
`),
  widget("rope", "rope-gap", "Tokens lejanos giran más", [
    knob("theta", "paso", 0.05, 0.8, 0.2, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, th = state.theta;
  var a = 2 * th, b = 9 * th, cx = w * 0.4, cy = h * 0.55;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(a) * 60, cy - Math.sin(a) * 60); ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(b) * 60, cy - Math.sin(b) * 60); ctx.stroke();
}
`),
  widget("dpo_beta", "dpo-pull", "Beta grande no se aleja", [
    knob("beta", "beta", 0.2, 5, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, beta = state.beta;
  var pull = Math.min(w * 0.7, 40 + beta * 36);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9cbb8";
  ctx.fillRect(w * 0.2, h * 0.45, 16, 16);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.2 + pull, h * 0.45, 16, 16);
}
`),
  widget("dpo_beta", "dpo-ratio", "El log-ratio se encoge con beta", [
    knob("beta", "beta", 0.3, 4, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, beta = state.beta;
  var gaps = [0.4, 1, 1.6], i, shown;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    shown = gaps[i] / beta;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(30 + i * (w / 4), h * 0.8 - shown * 28, 36, shown * 28);
  }
}
`),
  widget("yarn_scale", "yarn-bands", "La escala mueve a las frecuencias bajas", [
    knob("scale", "escala", 1, 8, 3, 0.2),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale, i, blend, factor;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 6; i++) {
    blend = i < 2 ? 0 : i > 3 ? 1 : 0.5;
    factor = 1 + (s - 1) * blend;
    ctx.fillStyle = blend > 0.5 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(20 + i * (w / 7), h * 0.8 - factor * 8, 24, factor * 8);
  }
}
`),
  widget("yarn_scale", "yarn-range", "El rango entrenado cubre más tokens", [
    knob("scale", "escala", 1, 6, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale;
  var train = (w * 0.7) / s;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(16, h * 0.4, train, 28);
  ctx.fillStyle = "#eadfce";
  ctx.fillRect(16 + train, h * 0.4, w * 0.7 - train, 28);
}
`),
  widget("speculative", "spec-sum", "La racha esperada satura", [
    knob("agree", "acuerdo", 0.2, 0.95, 0.6, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, a = state.agree, g, sum = 0, k;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (g = 1; g <= 6; g++) {
    sum = 0;
    for (k = 1; k <= g; k++) sum += Math.pow(a, k);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(16 + g * (w / 8), h * 0.82 - sum * 22, 18, sum * 22);
  }
}
`),
  widget("speculative", "spec-cut", "Un rechazo tira el resto", [
    knob("agree", "acuerdo", 0.1, 1, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, a = state.agree;
  var cut = Math.max(1, Math.round(a * 7)), i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 7; i++) {
    ctx.fillStyle = i < cut ? "#1f4b99" : "#c4512c";
    ctx.fillRect(20 + i * ((w - 30) / 7), h * 0.42, 24, 24);
  }
}
`),
  widget("noise_schedule", "noise-dots", "El beta abre la nube", [
    knob("beta", "beta", 0, 1, 0.2, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, b = state.beta, i, x, y;
  var pts = [[-1, 0.2], [0.4, -0.8], [1.1, 0.5], [-0.6, -0.4], [0.2, 0.9], [0.8, -0.2]];
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  for (i = 0; i < pts.length; i++) {
    x = w * 0.5 + pts[i][0] * (12 + b * 80);
    y = h * 0.5 + pts[i][1] * (8 + b * 50);
    ctx.fillRect(x, y, 6, 6);
  }
}
`),
  widget("noise_schedule", "noise-line", "El horario lineal acumula ruido", [
    knob("beta", "beta", 0.05, 1, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, b = state.beta;
  var x = 20 + b * (w - 50);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(20, h * 0.75);
  ctx.lineTo(w - 20, h * 0.25);
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(x - 4, h * 0.75 - b * (h * 0.5) - 4, 8, 8);
}
`),
  widget("guidance", "guide-over", "Una guía alta se pasa del texto", [
    knob("scale", "escala", 0, 4, 1.5, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale;
  var x = w * 0.15 + s * (w * 0.22);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(w * 0.45, h * 0.35, 18, h * 0.3);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(Math.min(w - 20, x), h * 0.45, 14, 14);
}
`),
  widget("guidance", "guide-mix", "Se resta la predicción sin texto", [
    knob("scale", "escala", 0, 3, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale;
  var cond = 80, un = 30, diff = (cond - un) * s;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9cbb8";
  ctx.fillRect(30, h * 0.7 - un, 40, un);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(100, h * 0.7 - cond, 40, cond);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(180, h * 0.7 - Math.min(diff, h * 0.6), 40, Math.min(diff, h * 0.6));
}
`),
  widget("detr_match", "detr-cost", "Clase y caja se pesan juntas", [
    knob("class_w", "peso clase", 0, 1, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, cw = state.class_w;
  var klass = cw * 0.8, box = (1 - cw) * 0.7;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - klass * 140, 60, klass * 140);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(140, h * 0.8 - box * 140, 60, box * 140);
}
`),
  widget("detr_match", "detr-slots", "Sobra query, sobra emparejamiento vacío", [
    knob("class_w", "peso clase", 0, 1, 0.5, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, cw = state.class_w;
  var links = cw > 0.66 ? 1 : cw > 0.33 ? 2 : 3;
  var i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    ctx.strokeStyle = "#1d1a16";
    ctx.strokeRect(30 + i * 70, 36, 40, 28);
    ctx.fillStyle = i < links ? "#1f4b99" : "#eadfce";
    ctx.fillRect(30 + i * 70, h * 0.65, 28, 28);
  }
}
`),
  widget("residual", "skip-depth", "Sin atajo la señal se apaga", [
    knob("skip", "atajo", 0.4, 1, 0.85, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, skip = state.skip, i, left;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 8; i++) {
    left = Math.pow(skip, i);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(16 + i * (w / 9), h * 0.82 - left * (h * 0.55), 18, left * (h * 0.55));
  }
}
`),
  widget("residual", "skip-split", "Entrada y capa se suman", [
    knob("skip", "atajo", 0, 1, 0.5, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, skip = state.skip;
  var inn = skip * 90, layer = (1 - skip) * 70;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.8 - inn, 50, inn);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(120, h * 0.8 - layer, 50, Math.max(2, layer));
  ctx.fillStyle = "#3f8a6b";
  ctx.fillRect(210, h * 0.8 - (inn + layer) * 0.5, 50, (inn + layer) * 0.5);
}
`),
  widget("nucleus", "nucleus-rare", "Subir p deja entrar lo raro", [
    knob("p", "masa p", 0.3, 1, 0.7, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, p = state.p;
  var probs = [0.55, 0.2, 0.12, 0.08, 0.05], i, mass = 0, keep = 5;
  for (i = 0; i < probs.length; i++) { mass += probs[i]; if (mass >= p) { keep = i + 1; break; } }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < probs.length; i++) {
    ctx.fillStyle = i < keep ? "#1f4b99" : "#eadfce";
    ctx.fillRect(20 + i * (w / 6), h * 0.75 - probs[i] * 180, 28, probs[i] * 180);
  }
}
`),
  widget("nucleus", "nucleus-curve", "La masa acumulada cruza p", [
    knob("p", "masa p", 0.2, 1, 0.9, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, p = state.p;
  var probs = [0.42, 0.24, 0.14, 0.1, 0.06, 0.04], i, acc = 0, x, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath();
  ctx.moveTo(16, h * 0.85 - p * (h * 0.6));
  ctx.lineTo(w - 16, h * 0.85 - p * (h * 0.6));
  ctx.stroke();
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i < probs.length; i++) {
    acc += probs[i];
    x = 20 + i * ((w - 40) / probs.length);
    y = h * 0.85 - acc * (h * 0.6);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`),
  widget("contrastive_temp", "tau-gap", "Tau cierra la brecha del positivo", [
    knob("tau", "tau", 0.15, 2, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau;
  var pos = 1.4 / tau, neg = 0.3 / tau, gap = pos - neg;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - Math.min(pos, 8) * 14, 50, Math.min(pos, 8) * 14);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(130, h * 0.8 - Math.min(gap, 8) * 14, 50, Math.min(gap, 8) * 14);
}
`),
  widget("contrastive_temp", "tau-row", "El lote se aplana si tau sube", [
    knob("tau", "tau", 0.2, 2.5, 0.7, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau;
  var sims = [1.6, 0.5, 0.2, 0, -0.3], i, m = -1e9, exps = [], s = 0, p;
  for (i = 0; i < sims.length; i++) if (sims[i] / tau > m) m = sims[i] / tau;
  for (i = 0; i < sims.length; i++) { exps[i] = Math.exp(sims[i] / tau - m); s += exps[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < sims.length; i++) {
    p = exps[i] / s;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(16 + i * (w / 6), h * 0.82 - p * (h * 0.6), 28, p * (h * 0.6));
  }
}
`),
];
