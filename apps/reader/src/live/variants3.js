import { knob, widget } from "./banks.js";

export const VARIANTS3 = [
  widget("positional_encoding", "pe-pair", "Seno y coseno del mismo par", [
    knob("base", "base", 10, 8000, 400, 10),
    knob("dim", "par i", 0, 6, 3, 1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, freq = 1 / Math.pow(state.base, (2 * state.dim) / 64);
  var i, x, pos;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#1f4b99";
  ctx.beginPath();
  for (i = 0; i <= 40; i++) {
    pos = i * 1.2; x = 12 + (i / 40) * (w - 24);
    var y = h * 0.4 - Math.sin(pos * freq) * 28;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath();
  for (i = 0; i <= 40; i++) {
    pos = i * 1.2; x = 12 + (i / 40) * (w - 24);
    var y2 = h * 0.75 - Math.cos(pos * freq) * 28;
    if (i === 0) ctx.moveTo(x, y2); else ctx.lineTo(x, y2);
  }
  ctx.stroke();
}
`),
  widget("positional_encoding", "pe-slowrow", "Las filas altas casi no se mueven", [
    knob("base", "base", 30, 3000, 200, 10),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, i, k, on;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 6; i++) {
    var freq = 1 / Math.pow(state.base, (2 * i) / 48);
    for (k = 0; k < 16; k++) {
      on = Math.sin(k * freq) > 0;
      ctx.fillStyle = on ? "#1f4b99" : "#eadfce";
      ctx.fillRect(12 + k * 20, 16 + i * 28, 16, 18);
    }
  }
}
`),
  widget("softmax_temperature", "temp-flat", "Temperatura alta aplana las cuatro", [
    knob("temp", "temperatura", 0.2, 4, 1.2, 0.1),
  ], `
function draw(ctx, state, t) {
  var logits = [1.8, 0.2, -0.4, -1], temp = state.temp, i, m = logits[0], exps = [], s = 0;
  var w = state.w, h = state.h;
  for (i = 1; i < 4; i++) if (logits[i] > m) m = logits[i];
  for (i = 0; i < 4; i++) { exps[i] = Math.exp((logits[i] - m) / temp); s += exps[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 4; i++) {
    var p = exps[i] / s;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * 70, h * 0.8 - p * 120, 40, p * 120);
  }
}
`),
  widget("softmax_temperature", "temp-gap", "La brecha entre primero y segundo", [
    knob("temp", "temperatura", 0.2, 3, 0.8, 0.05),
  ], `
function draw(ctx, state, t) {
  var temp = state.temp, a = Math.exp(1.4 / temp), b = Math.exp(0.6 / temp);
  var gap = a / (a + b) - b / (a + b);
  var w = state.w, h = state.h;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(60, h * 0.78 - gap * 120, 80, gap * 120);
}
`),
  widget("attention_scale", "scale-unscaled", "Sin dividir, una barra se come el resto", [
    knob("d", "d_k", 4, 81, 16, 1),
  ], `
function draw(ctx, state, t) {
  var s = Math.sqrt(state.d), a = Math.exp(s), b = Math.exp(0.3 * s), p = a / (a + b);
  var w = state.w, h = state.h;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.82 - p * 120, 50, p * 120);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(120, h * 0.82 - (1 - p) * 120, 50, (1 - p) * 120);
}
`),
  widget("attention_scale", "scale-safe", "Con la raíz el pico se queda quieto", [
    knob("d", "d_k", 4, 144, 36, 4),
  ], `
function draw(ctx, state, t) {
  var grown = Math.exp(Math.sqrt(state.d)) / (Math.exp(Math.sqrt(state.d)) + 1);
  var calm = Math.exp(1) / (Math.exp(1) + 1);
  var w = state.w, h = state.h;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(36, h * 0.8 - grown * 100, 48, grown * 100);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(120, h * 0.8 - calm * 100, 48, calm * 100);
}
`),
  widget("stddev", "std-two", "Dos nubes, una sigma", [
    knob("sigma", "sigma", 0.4, 2.4, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, s = state.sigma, i;
  var a = [-0.8, 0.2, 1], b = [-1.2, -0.2, 0.6];
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(40 + i * 28, h * 0.5 - a[i] * s * 20, 8, 8);
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(180 + i * 28, h * 0.5 - b[i] * s * 20, 8, 8);
  }
}
`),
  widget("stddev", "std-unit", "Tras dividir, el ancho vuelve a uno", [
    knob("sigma", "sigma", 0.5, 3, 1.6, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, raw = state.sigma * 36, unit = 36;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.6 - raw / 2, raw, 16);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.78 - unit / 2, unit, 16);
}
`),
  widget("rope", "rope-step", "Un paso más, un giro más", [
    knob("theta", "paso", 0.1, 1.2, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, i, ang, cx, cy = h * 0.55;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 4; i++) {
    ang = (i + 1) * state.theta;
    cx = 40 + i * 70;
    ctx.strokeStyle = "#1f4b99";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(ang) * 24, cy - Math.sin(ang) * 24);
    ctx.stroke();
  }
}
`),
  widget("rope", "rope-far", "Lejos en el texto, lejos en el ángulo", [
    knob("theta", "paso", 0.05, 0.5, 0.15, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, near = 1 * state.theta, far = 8 * state.theta;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(30, h * 0.7 - near * 80, 40, Math.max(4, near * 80));
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(110, h * 0.7 - Math.min(far, 2.2) * 50, 40, Math.min(far, 2.2) * 50);
}
`),
  widget("dpo_beta", "dpo-brake", "El freno crece con beta", [
    knob("beta", "beta", 0.2, 4, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, brake = Math.min(120, state.beta * 28);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.75 - brake, 36, brake);
}
`),
  widget("dpo_beta", "dpo-reward", "El premio implícito se encoge", [
    knob("beta", "beta", 0.4, 4, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, reward = 1.6 / state.beta;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(50, h * 0.78 - reward * 30, 70, reward * 30);
}
`),
  widget("yarn_scale", "yarn-high", "Las frecuencias altas casi no se estiran", [
    knob("scale", "escala", 1, 6, 2, 0.2),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, low = 10 * state.scale, high = 10;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(30, h * 0.7 - low, 40, low);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(110, h * 0.7 - high, 40, high);
}
`),
  widget("yarn_scale", "yarn-tokens", "Misma vuelta, más tokens", [
    knob("scale", "escala", 1, 7, 2, 0.25),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, n = Math.round(3 * state.scale), i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < n; i++) {
    ctx.fillStyle = i % 2 ? "#1f4b99" : "#c4512c";
    ctx.fillRect(16 + i * 16, h * 0.42, 12, 22);
  }
}
`),
  widget("speculative", "spec-prefix", "Solo el prefijo del borrador queda", [
    knob("agree", "acuerdo", 0.1, 1, 0.5, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, n = Math.round(state.agree * 5) + 1, i;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 6; i++) {
    ctx.fillStyle = i < n ? "#1f4b99" : "#eadfce";
    ctx.fillRect(16 + i * 40, h * 0.4, 28, 22);
  }
}
`),
  widget("speculative", "spec-waste", "Poco acuerdo tira casi todo el borrador", [
    knob("agree", "acuerdo", 0.05, 0.9, 0.3, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, waste = (1 - state.agree) * 100;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.78 - waste, 60, waste);
}
`),
  widget("noise_schedule", "noise-mix", "Señal y ruido se cambian el lugar", [
    knob("beta", "beta", 0, 1, 0.35, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sig = (1 - state.beta) * 90, noi = state.beta * 90;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.8 - sig, 50, Math.max(2, sig));
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(130, h * 0.8 - noi, 50, Math.max(2, noi));
}
`),
  widget("noise_schedule", "noise-early", "Beta alto gasta la señal al principio", [
    knob("beta", "beta", 0.1, 0.9, 0.3, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, i, left = 1;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 7; i++) {
    left *= 1 - state.beta;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(16 + i * 40, h * 0.8 - left * 80, 24, Math.max(2, left * 80));
  }
}
`),
  widget("guidance", "guide-push", "La guía es un empujón extra", [
    knob("scale", "escala", 0, 3, 1, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, x = 40 + state.scale * 50;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(160, h * 0.42, 16, 36);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(x, h * 0.48, 14, 14);
}
`),
  widget("guidance", "guide-plain", "Escala cero deja la muestra sin texto", [
    knob("scale", "escala", 0, 2, 0.4, 0.1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, lean = state.scale * 70;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#d9cbb8";
  ctx.fillRect(30, h * 0.5, 24, 24);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(30 + lean, h * 0.42, 24, 24);
}
`),
  widget("detr_match", "detr-one", "Uno a uno: una línea por query", [
    knob("class_w", "peso clase", 0, 1, 0.25, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, bend = state.class_w * 80;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(50, h * 0.72);
  ctx.lineTo(70 + bend, h * 0.28);
  ctx.stroke();
}
`),
  widget("detr_match", "detr-label", "La etiqueta gana si el peso sube", [
    knob("class_w", "peso clase", 0, 1, 0.3, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, pick = state.class_w > 0.55 ? 1 : 0;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = pick === 0 ? "#1f4b99" : "#eadfce";
  ctx.fillRect(40, h * 0.4, 50, 36);
  ctx.fillStyle = pick === 1 ? "#c4512c" : "#eadfce";
  ctx.fillRect(140, h * 0.4, 50, 36);
}
`),
  widget("residual", "skip-sum", "La suma es entrada más capa", [
    knob("skip", "atajo", 0, 1, 0.55, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, part = 20 + state.skip * 70;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(30, h * 0.78 - part, 40, part);
  ctx.fillStyle = "#3f8a6b";
  ctx.fillRect(100, h * 0.78 - (part + 30) * 0.6, 40, (part + 30) * 0.6);
}
`),
  widget("residual", "skip-off", "Atajo en cero, solo queda la capa", [
    knob("skip", "atajo", 0, 1, 0.4, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, pass = state.skip * 80, layer = 50;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(36, h * 0.75 - pass, 44, Math.max(2, pass));
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(110, h * 0.75 - layer, 44, layer);
}
`),
  widget("nucleus", "nucleus-count", "El conteo lo decide la masa", [
    knob("p", "masa p", 0.2, 1, 0.6, 0.05),
  ], `
function draw(ctx, state, t) {
  var probs = [0.46, 0.24, 0.14, 0.09, 0.07], i, mass = 0, keep = 5;
  var w = state.w, h = state.h;
  for (i = 0; i < probs.length; i++) { mass += probs[i]; if (mass >= state.p) { keep = i + 1; break; } }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < keep; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * 36, h * 0.45, 26, 26);
  }
}
`),
  widget("nucleus", "nucleus-fill", "La barra de masa se llena hasta p", [
    knob("p", "masa p", 0.2, 1, 0.65, 0.05),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, width = state.p * (w - 60);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#eadfce";
  ctx.fillRect(20, h * 0.45, w - 40, 22);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(20, h * 0.45, width, 22);
}
`),
  widget("contrastive_temp", "tau-share", "La tajada del positivo", [
    knob("tau", "tau", 0.15, 2, 0.45, 0.05),
  ], `
function draw(ctx, state, t) {
  var tau = state.tau, a = Math.exp(1.3 / tau), b = Math.exp(0.25 / tau);
  var p = a / (a + b), w = state.w, h = state.h;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.78 - p * 100, 55, p * 100);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(120, h * 0.78 - (1 - p) * 100, 55, (1 - p) * 100);
}
`),
  widget("contrastive_temp", "tau-batch", "Cuatro del lote, uno positivo", [
    knob("tau", "tau", 0.2, 2.2, 0.5, 0.05),
  ], `
function draw(ctx, state, t) {
  var sims = [1.4, 0.45, 0.2, -0.1], tau = state.tau, i, m = -1e9, exps = [], s = 0;
  var w = state.w, h = state.h;
  for (i = 0; i < 4; i++) if (sims[i] / tau > m) m = sims[i] / tau;
  for (i = 0; i < 4; i++) { exps[i] = Math.exp(sims[i] / tau - m); s += exps[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 4; i++) {
    var p = exps[i] / s;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(18 + i * 70, h * 0.8 - p * 110, 40, p * 110);
  }
}
`),
  widget("positional_encoding", "pe-dimbase", "Sube la base y la fila elegida se calma", [
    knob("base", "base", 15, 5000, 250, 5),
    knob("dim", "par i", 1, 7, 4, 1),
  ], `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, freq = 1 / Math.pow(state.base, (2 * state.dim) / 64);
  var amp = 16 + 90 * freq;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(w * 0.3, h * 0.55 - amp, 40, amp);
}
`),
  widget("softmax_temperature", "temp-mass", "Masa del primero contra el resto", [
    knob("temp", "temperatura", 0.2, 3.5, 1, 0.05),
  ], `
function draw(ctx, state, t) {
  var temp = state.temp, a = Math.exp(1.5 / temp), rest = Math.exp(0.4 / temp) + Math.exp(0 / temp) + Math.exp(-0.5 / temp);
  var p = a / (a + rest), w = state.w, h = state.h;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(36, h * 0.8 - p * (h * 0.55), p * (w * 0.7), 28);
}
`),
];
