import { knob, widget } from "./banks.js";

export const VARIANTS2 = [
  widget("positional_encoding", "pe-fastslow", "La base no toca la onda rápida", [
    knob("base", "base", 20, 20000, 1000, 10),
    knob("dim", "par i", 0, 8, 6, 1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base, i, x, pos, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  function wave(dim, color, amp) {
    var freq = 1 / Math.pow(base, (2 * dim) / 64);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (i = 0; i <= 60; i++) {
      pos = i;
      x = 10 + (i / 60) * (w - 20);
      y = h * 0.5 - Math.sin(pos * freq) * amp;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  wave(0, "#c4512c", h * 0.16);
  wave(state.dim, "#1f4b99", h * 0.28);
}
`),
  widget("positional_encoding", "pe-cycles", "Cuántas vueltas caben en 64 pasos", [
    knob("base", "base", 10, 10000, 100, 10),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base;
  var freq = 1 / Math.pow(base, 8 / 64);
  var cycles = Math.min(12, (64 * freq) / (Math.PI * 2));
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(24, h * 0.7 - cycles * 10, cycles * 22, 18);
}
`),
  widget("softmax_temperature", "temp-logits", "El control parte los logits", [
    knob("temp", "temperatura", 0.25, 4, 1, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, temp = state.temp;
  var zs = [1.6, 0.4, -0.6], i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    var v = zs[i] / temp;
    ctx.fillStyle = v >= 0 ? "#1f4b99" : "#c4512c";
    ctx.fillRect(30 + i * 70, h * 0.55 - Math.max(0, v) * 16, 36, Math.abs(v) * 16);
  }
}
`),
  widget("softmax_temperature", "temp-winner", "Baja temperatura, un solo ganador", [
    knob("temp", "temperatura", 0.15, 3, 0.8, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, temp = state.temp;
  var logits = [1.3, 0.9, 0.2], i, m = logits[0], exps = [], s = 0, best = 0, p, bp = 0;
  for (i = 1; i < 3; i++) if (logits[i] > m) m = logits[i];
  for (i = 0; i < 3; i++) { exps[i] = Math.exp((logits[i] - m) / temp); s += exps[i]; }
  for (i = 0; i < 3; i++) { p = exps[i] / s; if (p > bp) { bp = p; best = i; } }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40 + best * 80, h * 0.75 - bp * 100, 48, bp * 100);
}
`),
  widget("attention_scale", "scale-rows", "Arriba sin raíz, abajo con raíz", [
    knob("d", "d_k", 4, 64, 16, 4),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, d = state.d, s = Math.sqrt(d);
  var raw = [0.8, 0.3, -0.1], i, m1 = -1e9, m2 = -1e9, a = [], b = [], s1 = 0, s2 = 0;
  for (i = 0; i < 3; i++) { if (raw[i] * s > m1) m1 = raw[i] * s; if (raw[i] > m2) m2 = raw[i]; }
  for (i = 0; i < 3; i++) { a[i] = Math.exp(raw[i] * s - m1); s1 += a[i]; b[i] = Math.exp(raw[i] - m2); s2 += b[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(30 + i * 70, h * 0.42 - (a[i] / s1) * 60, 36, (a[i] / s1) * 60);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(30 + i * 70, h * 0.9 - (b[i] / s2) * 60, 36, (b[i] / s2) * 60);
  }
}
`),
  widget("attention_scale", "scale-ratio", "La raíz deja más de una clave viva", [
    knob("d", "d_k", 4, 100, 25, 1),
  ], `
function draw(ctx, state, t) {
  var d = state.d, s = Math.sqrt(d);
  var sharp = Math.exp(s) / (Math.exp(s) + Math.exp(0.2 * s));
  var flat = Math.exp(1) / (Math.exp(1) + Math.exp(0.2));
  var w = state.w, h = state.h;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - sharp * 100, 60, sharp * 100);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(140, h * 0.8 - flat * 100, 60, flat * 100);
}
`),
  widget("stddev", "std-band", "La banda es más o menos sigma", [
    knob("sigma", "sigma", 0.3, 3, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sigma = state.sigma, mid = h * 0.55, band = sigma * 28;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9e3f5";
  ctx.fillRect(0, mid - band, w, band * 2);
  ctx.strokeStyle = "#1f4b99";
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();
}
`),
  widget("stddev", "std-ticks", "Los mismos puntos, distinto ancho", [
    knob("sigma", "sigma", 0.4, 2.5, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sigma = state.sigma;
  var zs = [-1.4, -0.6, 0, 0.5, 1.2], i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  for (i = 0; i < zs.length; i++) ctx.fillRect(30 + i * 50, h * 0.55 - zs[i] * sigma * 24, 8, 8);
}
`),
  widget("rope", "rope-arc", "El ángulo crece con el paso", [
    knob("theta", "paso", 0.1, 1.5, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, ang = 6 * state.theta;
  var cx = w * 0.45, cy = h * 0.6;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(cx, cy, 50, 0, ang);
  ctx.stroke();
}
`),
  widget("rope", "rope-delta", "La diferencia de giros es la distancia", [
    knob("theta", "paso", 0.05, 0.6, 0.15, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, gap = 5 * state.theta;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(30, h * 0.7 - Math.min(gap, 3) * 40, 80, Math.min(gap, 3) * 40);
}
`),
  widget("dpo_beta", "dpo-sigmoid", "Beta empina la preferencia", [
    knob("beta", "beta", 0.2, 5, 1.2, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, beta = state.beta, i, gap, y, x;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 40; i++) {
    gap = -2 + (i / 40) * 4;
    y = h * 0.8 - (1 / (1 + Math.exp(-beta * gap))) * (h * 0.55);
    x = 16 + (i / 40) * (w - 32);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`),
  widget("dpo_beta", "dpo-stay", "Beta grande se queda en la referencia", [
    knob("beta", "beta", 0.25, 4, 1, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, dist = 120 / state.beta;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.45, 14, 14);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40 + Math.min(dist, w - 80), h * 0.45, 14, 14);
}
`),
  widget("yarn_scale", "yarn-cycles", "Más escala, menos vueltas", [
    knob("scale", "escala", 1, 8, 2, 0.25),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale, i, x, y;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 50; i++) {
    x = 12 + (i / 50) * (w - 24);
    y = h * 0.55 - Math.sin((i / s) * 0.7) * 40;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
`),
  widget("yarn_scale", "yarn-cover", "La escala reparte el entrenamiento", [
    knob("scale", "escala", 1, 5, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.scale, n = Math.round(4 * s), i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < n; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(16 + i * ((w - 30) / 20), h * 0.4, 12, 24);
  }
}
`),
  widget("speculative", "spec-blocks", "Acuerdo alto, bloque largo", [
    knob("agree", "acuerdo", 0.1, 1, 0.5, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, n = Math.max(1, Math.round(state.agree * 6)), i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < n; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * 36, h * 0.4, 28, 28);
  }
}
`),
  widget("speculative", "spec-cost", "Verificar el borrador sale más barato", [
    knob("agree", "acuerdo", 0.15, 0.9, 0.45, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, saved = state.agree * 100;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.75 - 70, 50, 70);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(140, h * 0.75 - saved, 50, saved);
}
`),
  widget("noise_schedule", "noise-fade", "La señal se apaga con beta", [
    knob("beta", "beta", 0, 1, 0.3, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, b = state.beta, keep = (1 - b) * 80;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(w * 0.3, h * 0.7 - keep, 70, Math.max(2, keep));
}
`),
  widget("noise_schedule", "noise-steps", "Beta alto borra en menos pasos", [
    knob("beta", "beta", 0.05, 1, 0.2, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, steps = Math.max(1, Math.round((1 - state.beta) * 8)), i, left = 1;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < steps; i++) {
    left = left * (1 - state.beta * 0.5);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(16 + i * 32, h * 0.75 - left * 80, 22, left * 80);
  }
}
`),
  widget("guidance", "guide-target", "La escala acerca la muestra al texto", [
    knob("scale", "escala", 0, 2.5, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, x = w * 0.2 + state.scale * (w * 0.22);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(w * 0.62, h * 0.4, 20, 40);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(Math.min(w - 24, x), h * 0.48, 16, 16);
}
`),
  widget("guidance", "guide-gap", "Sin guía te quedas en lo incondicional", [
    knob("scale", "escala", 0, 3, 0.5, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, gap = state.scale * 50;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9cbb8";
  ctx.fillRect(40, h * 0.45, 30, 30);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40 + gap, h * 0.45, 30, 30);
}
`),
  widget("detr_match", "detr-swap", "Pesar la clase cruza el emparejamiento", [
    knob("class_w", "peso clase", 0, 1, 0.2, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, cross = state.class_w > 0.5;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1d1a16";
  ctx.beginPath();
  ctx.moveTo(60, h * 0.7);
  ctx.lineTo(cross ? w * 0.75 : 80, h * 0.3);
  ctx.moveTo(w * 0.7, h * 0.7);
  ctx.lineTo(cross ? 80 : w * 0.72, h * 0.3);
  ctx.stroke();
}
`),
  widget("detr_match", "detr-bars", "El costo de clase contra el de caja", [
    knob("class_w", "peso clase", 0, 1, 0.35, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, a = state.class_w * 100, b = (1 - state.class_w) * 90;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(50, h * 0.8 - a, 40, a);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(140, h * 0.8 - b, 40, b);
}
`),
  widget("residual", "skip-mix", "El atajo mezcla entrada y capa", [
    knob("skip", "atajo", 0, 1, 0.6, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, inn = state.skip * 100, mid = (1 - state.skip) * 80;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(36, h * 0.78 - inn, 46, Math.max(2, inn));
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(120, h * 0.78 - mid, 46, Math.max(2, mid));
}
`),
  widget("residual", "skip-fade", "Capas sin atajo se achican", [
    knob("skip", "atajo", 0.5, 1, 0.8, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, i, v = 1;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 6; i++) {
    v *= state.skip;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * 48, h * 0.8 - v * 90, 28, v * 90);
  }
}
`),
  widget("nucleus", "nucleus-keep", "p chico deja un conjunto chico", [
    knob("p", "masa p", 0.25, 1, 0.55, 0.05),
  ], `
function draw(ctx, state, t) {
  var probs = [0.5, 0.22, 0.13, 0.09, 0.06], i, mass = 0, keep = 5;
  var w = state.w, h = state.h;
  for (i = 0; i < probs.length; i++) { mass += probs[i]; if (mass >= state.p) { keep = i + 1; break; } }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.75 - keep * 16, 70, keep * 16);
}
`),
  widget("nucleus", "nucleus-tail", "La cola entra solo si p alcanza", [
    knob("p", "masa p", 0.4, 1, 0.75, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, show = state.p > 0.85;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(30, h * 0.35, 40, 50);
  ctx.fillRect(80, h * 0.45, 40, 40);
  ctx.fillStyle = show ? "#c4512c" : "#eadfce";
  ctx.fillRect(140, h * 0.55, 30, 24);
  ctx.fillRect(180, h * 0.6, 24, 18);
}
`),
  widget("contrastive_temp", "tau-pos", "Tau bajo se queda con el positivo", [
    knob("tau", "tau", 0.15, 2, 0.35, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau;
  var a = Math.exp(1.5 / tau), b = Math.exp(0.2 / tau), p = a / (a + 3 * b);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(50, h * 0.8 - p * 110, 60, p * 110);
}
`),
  widget("contrastive_temp", "tau-soft", "Tau alto iguala positivos y negativos", [
    knob("tau", "tau", 0.2, 2.4, 0.6, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau;
  var sims = [1.2, 0.4, 0.15], i, m = -1e9, exps = [], s = 0;
  for (i = 0; i < 3; i++) if (sims[i] / tau > m) m = sims[i] / tau;
  for (i = 0; i < 3; i++) { exps[i] = Math.exp(sims[i] / tau - m); s += exps[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    var p = exps[i] / s;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(30 + i * 80, h * 0.8 - p * 120, 46, p * 120);
  }
}
`),
];
