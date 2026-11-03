// Topics named in the 0.2 table and not yet drawn here: selective state,
// SmoothQuant, YaRN by parts. Papers and the [V]/[I] line live in compass.

import { knob, widget } from "./banks.js";

const MAMBA = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, spike = state.delta, quiet = state.quiet;
  var n = 28, i, hst = 0, xs = [], hs = [], dlt, dec, x, bw, bh;
  for (i = 0; i < n; i++) xs[i] = (i === 4 || i === 13 || i === 22) ? 1 : 0;
  for (i = 0; i < n; i++) {
    dlt = xs[i] > 0.5 ? spike : quiet;
    dec = Math.exp(-dlt);
    hst = dec * hst + (1 - dec) * xs[i];
    hs[i] = hst;
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 36) / n;
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("picos", 8, h * 0.16);
  for (i = 0; i < n; i++) {
    x = 28 + i * bw;
    ctx.fillStyle = xs[i] > 0.5 ? "#c4512c" : "#e4d6c4";
    ctx.fillRect(x, h * 0.1, bw - 3, xs[i] > 0.5 ? 22 : 8);
  }
  ctx.fillStyle = "#5c564c";
  ctx.fillText("estado", 8, h * 0.42);
  for (i = 0; i < n; i++) {
    x = 28 + i * bw;
    bh = Math.max(2, hs[i] * h * 0.42);
    ctx.fillStyle = hs[i] > 0.55 ? "#1f4b99" : "#9db4dc";
    ctx.fillRect(x, h * 0.82 - bh, bw - 3, bh);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(hs[n - 1] > 0.45 ? "se quedó con el último pico" : "el resto se lo borró", 28, h * 0.94);
}
`;

const SMOOTH = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, a = state.alpha;
  var X = [1.2, 0.8, 48, 1.1, 0.6, 36, 1.4, 0.9];
  var Wv = [1.1, 0.9, 1.4, 0.7, 1.2, 0.8, 1.0, 1.3];
  var n = 8, i, s, xp, wp, bw, top = 52;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 40) / n;
  ctx.font = "14px sans-serif";
  ctx.fillStyle = "#c4512c";
  ctx.fillText("activaciones", 16, 22);
  ctx.fillStyle = "#1f4b99";
  ctx.fillText("pesos", 16, h * 0.5);
  for (i = 0; i < n; i++) {
    s = Math.pow(X[i], a) / Math.pow(Wv[i], 1 - a);
    xp = X[i] / s;
    wp = Wv[i] * s;
    ctx.fillStyle = xp > 4 ? "#c4512c" : "#e7a090";
    ctx.fillRect(20 + i * bw, top + h * 0.28 - Math.min(xp, 16) / 16 * h * 0.28, bw - 8, Math.min(xp, 16) / 16 * h * 0.28);
    ctx.fillStyle = wp > 4 ? "#1f4b99" : "#9db4dc";
    ctx.fillRect(20 + i * bw, h * 0.86 - Math.min(wp, 16) / 16 * h * 0.28, bw - 8, Math.min(wp, 16) / 16 * h * 0.28);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(a > 0.35 && a < 0.65 ? "alfa " + Math.round(a * 100) / 100 + "  se encontraron" : (a < 0.35 ? "el outlier sigue en la activación" : "el outlier se fue al peso"), 150, 22);
}
`;

const YARN = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, sc = state.scale, L = state.ctxlen;
  var base = 10000, dim = 16, n = 8, i, lam, r, g, th, th2, lam2, bh, bw;
  var lo = 1, hi = 32;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 48) / n;
  var baseY = h * 0.78, span = h * 0.58;
  function Y(v) { return baseY - (Math.log(v) / Math.log(10) - 0.6) / 5.4 * span; }
  for (i = 0; i < n; i++) {
    lam = 2 * Math.PI * Math.pow(base, (2 * i) / dim);
    r = L / lam;
    if (r < lo) g = 0;
    else if (r > hi) g = 1;
    else g = (r - lo) / (hi - lo);
    th = Math.pow(base, -(2 * i) / dim);
    th2 = (1 - g) * th / sc + g * th;
    lam2 = 2 * Math.PI / th2;
    bh = baseY - Y(lam2);
    if (bh < 4) bh = 4;
    ctx.fillStyle = g > 0.85 ? "#1f4b99" : (g < 0.15 ? "#c4512c" : "#2e7d32");
    ctx.fillRect(24 + i * bw, baseY - bh, bw - 8, bh);
    ctx.fillStyle = "#5c564c";
    ctx.font = "12px sans-serif";
    ctx.fillText("" + i, 28 + i * bw, baseY + 16);
  }
  var ly = Y(L);
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(16, ly);
  ctx.lineTo(w - 12, ly);
  ctx.stroke();
  ctx.fillStyle = "#1d1a16";
  ctx.font = "14px sans-serif";
  ctx.fillText("coral: se estira   azul: se queda   la raya es el contexto", 16, 22);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("alfa 1   beta 32   como Llama", 16, 42);
}
`;

export const MORE = [
  widget("ssm_delta", "mamba-delta", "Delta grande graba el pico y el resto no lo borra", [
    knob("delta", "delta del pico", 0.05, 3, 2.4, 0.05),
    knob("quiet", "delta del resto", 0.02, 2.5, 0.08, 0.02),
  ], MAMBA),
  widget("smoothquant", "smooth-seesaw", "El outlier pasa de la activación al peso", [
    knob("alpha", "alfa", 0, 1, 0.5, 0.05),
  ], SMOOTH),
  widget("yarn_parts", "yarn-parts", "Solo una parte de las ondas se estira", [
    knob("scale", "escala", 1, 16, 4, 0.5),
    knob("ctxlen", "contexto", 512, 16384, 4096, 256),
  ], YARN),
];

export const MORE_LEADS = MORE;
