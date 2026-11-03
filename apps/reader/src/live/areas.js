// Areas the first catalog did not teach. Papers and the [V]/[I] line live in compass.

import { knob, widget } from "./banks.js";

const VIT = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, raw = state.patch;
  var choices = [16, 32, 56, 112], bi = 0, bd = 999, k, P, n, N, s, cell, i, j, su, sv, sun, ground;
  for (k = 0; k < 4; k++) if (Math.abs(choices[k] - raw) < bd) { bd = Math.abs(choices[k] - raw); bi = k; }
  P = choices[bi];
  n = 224 / P;
  N = n * n;
  s = Math.min(h - 40, w * 0.52);
  cell = s / n;
  su = 0.68;
  sv = 0.32;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
    sun = (j / n <= su && su < (j + 1) / n && i / n <= sv && sv < (i + 1) / n) ? 1 : 0;
    ground = (i + 0.5) / n > 0.62 ? 1 : 0;
    ctx.fillStyle = sun ? "#c4512c" : (ground ? "#1f4b99" : "#efe6d8");
    ctx.fillRect(16 + j * cell, 24 + i * cell, Math.max(2, cell - 1), Math.max(2, cell - 1));
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "26px sans-serif";
  ctx.fillText(N + " tokens", s + 36, h * 0.32);
  ctx.font = "15px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("parche " + P, s + 36, h * 0.44);
  ctx.fillText("N = (224/P)^2", s + 36, h * 0.54);
  ctx.fillText(n < 5 ? "el sol cabe en un parche" : "el sol es un parche", s + 36, h * 0.66);
}
`;

const ERF = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, depth = Math.round(state.depth), ker = Math.round(state.ker);
  var rf = 1 + (ker - 1) * depth, sig = 0.85 * Math.sqrt(depth), n = 41, i, dist, g, x, bw, base, bh;
  if (sig < 0.4) sig = 0.4;
  bw = (w * 0.7) / n;
  base = h * 0.78;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var half = rf / 2, x0 = 16 + (20 - half) * bw, ww = rf * bw;
  if (x0 < 16) { ww -= 16 - x0; x0 = 16; }
  ctx.fillStyle = "#e7dcc8";
  ctx.fillRect(x0, h * 0.2, ww, base - h * 0.2);
  for (i = 0; i < n; i++) {
    dist = i - 20;
    g = Math.exp(-(dist * dist) / (2 * sig * sig));
    bh = g * h * 0.5;
    x = 16 + i * bw;
    ctx.fillStyle = g > 0.45 ? "#1f4b99" : "#9db4dc";
    ctx.fillRect(x, base - bh, Math.max(2, bw - 1), bh);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("teorico " + rf + " px", w * 0.74, h * 0.28);
  ctx.fillStyle = "#5c564c";
  ctx.font = "14px sans-serif";
  ctx.fillText("el brillo es mas chico", w * 0.74, h * 0.38);
  ctx.fillText("la campana es ilustrativa", w * 0.74, h * 0.48);
}
`;

const DETR = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, cw = state.class_w;
  var box = [0.1, 0.9, 0.8, 0.8, 0.1, 0.7, 0.6, 0.7, 0.1];
  var cls = [0.9, 0.1, 0.8, 0.2, 0.9, 0.1, 0.1, 0.8, 0.7];
  var perm = [0, 1, 2, 0, 2, 1, 1, 0, 2, 1, 2, 0, 2, 0, 1, 2, 1, 0];
  var best = 0, cost = 999, p, k, o, c, pick = [];
  for (p = 0; p < 6; p++) {
    c = 0;
    for (k = 0; k < 3; k++) {
      o = perm[p * 3 + k];
      c += (1 - cw) * box[k * 3 + o] + cw * cls[k * 3 + o];
    }
    if (c < cost) { cost = c; best = p; }
  }
  for (k = 0; k < 3; k++) pick[k] = perm[best * 3 + k];
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var y0 = h * 0.22, gap = h * 0.22, xq = w * 0.16, xo = w * 0.62;
  for (k = 0; k < 3; k++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(xq, y0 + k * gap, 28, 28);
    ctx.fillStyle = pick[k] === k ? "#2e7d32" : "#c4512c";
    ctx.fillRect(xo, y0 + pick[k] * gap, 28, 28);
    ctx.strokeStyle = "#1d1a16";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(xq + 28, y0 + k * gap + 14);
    ctx.lineTo(xo, y0 + pick[k] * gap + 14);
    ctx.stroke();
    ctx.fillStyle = "#5c564c";
    ctx.font = "14px sans-serif";
    ctx.fillText("q" + k, xq - 28, y0 + k * gap + 18);
    ctx.fillText("obj " + k, xo + 36, y0 + k * gap + 18);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText(cw < 0.45 ? "sigue la caja" : "sigue la clase", w * 0.34, h * 0.12);
}
`;

const PPO = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, eps = state.eps, adv = state.adv, ratio = state.ratio;
  var L = 48, R = w * 0.72, T = 36, B = h * 0.82, i, r, y, lo, hi;
  function clipR(v) {
    if (v < 1 - eps) return 1 - eps;
    if (v > 1 + eps) return 1 + eps;
    return v;
  }
  function loss(v) {
    var a = v * adv, b = clipR(v) * adv;
    return a < b ? a : b;
  }
  function X(v) { return L + (v / 2) * (R - L); }
  function Y(v) {
    if (v > 2.2) v = 2.2;
    if (v < -2.2) v = -2.2;
    return B - ((v + 2.2) / 4.4) * (B - T);
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  lo = X(1 - eps);
  hi = X(1 + eps);
  ctx.fillStyle = "#e7e2d4";
  ctx.fillRect(lo, T, Math.max(2, hi - lo), B - T);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 60; i++) {
    r = (i / 60) * 2;
    y = Y(loss(r));
    if (i === 0) ctx.moveTo(X(r), y);
    else ctx.lineTo(X(r), y);
  }
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(X(ratio), Y(loss(ratio)), 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  var flat = (adv > 0 && ratio > 1 + eps) || (adv < 0 && ratio < 1 - eps);
  ctx.fillText(flat ? "el clip ya no deja pasar" : "todavia dentro del clip", 16, 22);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("razon " + Math.round(ratio * 100) / 100, R + 12, h * 0.4);
}
`;

const GAE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, lam = state.lam, n = 16, prize = 10, i, x, bw, bh, g, pow;
  var gamma = 0.9;
  bw = (w - 36) / n;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("premio", 8, h * 0.18);
  for (i = 0; i < n; i++) {
    x = 28 + i * bw;
    ctx.fillStyle = i === prize ? "#c4512c" : "#e4d6c4";
    ctx.fillRect(x, h * 0.1, bw - 3, i === prize ? 22 : 8);
  }
  ctx.fillStyle = "#5c564c";
  ctx.fillText("ventaja", 8, h * 0.42);
  for (i = 0; i < n; i++) {
    g = 0;
    if (i <= prize) {
      pow = Math.pow(gamma * lam, prize - i);
      g = pow;
    }
    x = 28 + i * bw;
    bh = Math.max(2, g * h * 0.4);
    ctx.fillStyle = g > 0.55 ? "#1f4b99" : "#9db4dc";
    ctx.fillRect(x, h * 0.84 - bh, bw - 3, bh);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(lam < 0.08 ? "solo el paso del premio" : "el credito vuelve atras", 28, h * 0.94);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("gamma 0.9", w * 0.78, h * 0.18);
}
`;

const GCN = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, depth = Math.round(state.depth);
  var n = 6, deg = [1, 1, 1, 1, 1, 1], e, layer, i, j, mx, ang, rad, x, y;
  var linkA = [0, 0, 0, 0], linkB = [1, 2, 3, 4];
  for (e = 0; e < 4; e++) { deg[linkA[e]] += 1; deg[linkB[e]] += 1; }
  function linked(a, b) {
    if (a === b) return 1;
    if (a === 0 && b > 0 && b < 5) return 1;
    if (b === 0 && a > 0 && a < 5) return 1;
    return 0;
  }
  var heat = [1, 0, 0, 0, 0, 0], nh = [], s;
  for (layer = 0; layer < depth; layer++) {
    for (i = 0; i < n; i++) nh[i] = 0;
    for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
      if (linked(i, j)) nh[i] += heat[j] / Math.sqrt(deg[i] * deg[j]);
    }
    for (i = 0; i < n; i++) heat[i] = nh[i];
  }
  mx = 0.01;
  for (i = 0; i < n; i++) if (heat[i] > mx) mx = heat[i];
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var cx = w * 0.36, cy = h * 0.52, R = Math.min(w, h) * 0.26, px = [], py = [];
  px[0] = cx; py[0] = cy;
  for (i = 1; i <= 4; i++) {
    ang = -Math.PI / 2 + (i - 1) * Math.PI / 2;
    px[i] = cx + Math.cos(ang) * R;
    py[i] = cy + Math.sin(ang) * R;
  }
  px[5] = w * 0.84;
  py[5] = cy;
  ctx.strokeStyle = "#b7aa9a";
  ctx.lineWidth = 2;
  for (i = 1; i <= 4; i++) {
    ctx.beginPath();
    ctx.moveTo(px[0], py[0]);
    ctx.lineTo(px[i], py[i]);
    ctx.stroke();
  }
  for (i = 0; i < n; i++) {
    rad = 7 + 32 * heat[i] / mx;
    ctx.fillStyle = heat[i] > 0.12 * mx ? "#1f4b99" : "#e4d6c4";
    ctx.beginPath();
    ctx.arc(px[i], py[i], rad, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(depth === 0 ? "solo el centro" : "los vecinos se encienden", 16, 24);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("suelto", px[5] - 16, py[5] + 36);
}
`;

const CLIP = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau, ang = state.slide;
  var texts = [0.4, 1.35, 2.25, 3.15], name = ["gato", "casa", "tren", "mar"];
  var sim = [], pr = [], i, m, acc, ex, cx, cy, rad, x, y, bw, win = 0;
  if (tau < 0.05) tau = 0.05;
  m = -2;
  for (i = 0; i < 4; i++) {
    sim[i] = Math.cos(ang - texts[i]);
    if (sim[i] / tau > m) m = sim[i] / tau;
  }
  acc = 0;
  for (i = 0; i < 4; i++) { ex = Math.exp(sim[i] / tau - m); pr[i] = ex; acc += ex; }
  for (i = 0; i < 4; i++) { pr[i] = pr[i] / acc; if (pr[i] > pr[win]) win = i; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  cx = w * 0.28;
  cy = h * 0.55;
  rad = Math.min(w, h) * 0.22;
  ctx.strokeStyle = "#e0d5c6";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, rad, 0, Math.PI * 2);
  ctx.stroke();
  for (i = 0; i < 4; i++) {
    x = cx + Math.cos(texts[i]) * rad;
    y = cy + Math.sin(texts[i]) * rad;
    ctx.fillStyle = i === win ? "#1f4b99" : "#9db4dc";
    ctx.beginPath();
    ctx.arc(x, y, i === win ? 9 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#5c564c";
    ctx.font = "13px sans-serif";
    ctx.fillText(name[i], x + 12, y + (y < cy ? -14 : 16));
  }
  x = cx + Math.cos(ang) * rad * 0.62;
  y = cy + Math.sin(ang) * rad * 0.62;
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(x, y, 8, 0, Math.PI * 2);
  ctx.fill();
  bw = w * 0.28;
  for (i = 0; i < 4; i++) {
    ctx.fillStyle = i === win ? "#1f4b99" : "#d9e3f5";
    ctx.fillRect(w * 0.62, 40 + i * (h * 0.16), Math.max(4, pr[i] * bw), h * 0.1);
    ctx.fillStyle = "#5c564c";
    ctx.font = "13px sans-serif";
    ctx.fillText(name[i], w * 0.62 + bw + 8, 40 + i * (h * 0.16) + 16);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("gana " + name[win], 16, 24);
}
`;

const BPE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, merges = Math.round(state.merges);
  var ruleL = [1, 3, 20, 5, 23, 22], ruleR = [2, 4, 21, 6, 7, 24], ruleN = [20, 21, 22, 23, 24, 25];
  var id = [1, 2, 3, 4, 5, 6, 7], span = [1, 1, 1, 1, 1, 1, 1], n = 7, rare = [8, 9, 10, 11];
  var mi, j, m, outI = [], outS = [], i, x, unit, y;
  function apply(L, R, nid) {
    m = 0;
    j = 0;
    while (j < n) {
      if (j + 1 < n && id[j] === L && id[j + 1] === R) {
        outI[m] = nid;
        outS[m] = span[j] + span[j + 1];
        m += 1;
        j += 2;
      } else {
        outI[m] = id[j];
        outS[m] = span[j];
        m += 1;
        j += 1;
      }
    }
    n = m;
    for (j = 0; j < n; j++) { id[j] = outI[j]; span[j] = outS[j]; }
  }
  for (mi = 0; mi < merges && mi < 6; mi++) apply(ruleL[mi], ruleR[mi], ruleN[mi]);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  unit = (w - 48) / 7;
  ctx.fillStyle = "#5c564c";
  ctx.font = "14px sans-serif";
  ctx.fillText("comun", 8, h * 0.2);
  x = 80;
  y = h * 0.12;
  for (i = 0; i < n; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(x, y, Math.max(8, span[i] * unit - 6), 36);
    x += span[i] * unit;
  }
  ctx.fillStyle = "#5c564c";
  ctx.fillText("rara", 8, h * 0.55);
  x = 80;
  y = h * 0.46;
  for (i = 0; i < 4; i++) {
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(x, y, unit - 6, 36);
    x += unit;
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("comun en " + n + "   rara en 4", 16, h * 0.82);
}
`;

const PAGED = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, page = Math.round(state.page);
  var len = [40, 90, 20, 70], maxL = 128, i, pages, waste, used = 0, reserved = 0, paged = 0, y, bw, x0;
  if (page < 1) page = 1;
  for (i = 0; i < 4; i++) {
    used += len[i];
    reserved += maxL;
    pages = Math.ceil(len[i] / page);
    paged += pages * page;
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  x0 = 16;
  bw = (w * 0.42);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("reserva el maximo", x0, 20);
  ctx.fillText("por paginas", w * 0.54, 20);
  for (i = 0; i < 4; i++) {
    y = 36 + i * (h * 0.16);
    ctx.fillStyle = "#e4d6c4";
    ctx.fillRect(x0, y, bw, 22);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(x0, y, bw * len[i] / maxL, 22);
    pages = Math.ceil(len[i] / page);
    waste = pages * page - len[i];
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(w * 0.54, y, bw * len[i] / maxL, 22);
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(w * 0.54 + bw * len[i] / maxL, y, Math.max(2, bw * waste / maxL), 22);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("uso " + Math.round(100 * used / reserved) + "%", 16, h * 0.9);
  ctx.fillText("uso " + Math.round(100 * used / paged) + "%", w * 0.54, h * 0.9);
}
`;

const NUCLEUS = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, p = state.p, temp = state.temp;
  var logits = [3.2, 2.4, 1.1, 0.4, -0.2, -0.6, -1.2, -1.8];
  var n = 8, i, m = -99, acc = 0, ex, pr = [], kept = 0, sum = 0, x, bw, bh;
  if (temp < 0.05) temp = 0.05;
  for (i = 0; i < n; i++) if (logits[i] / temp > m) m = logits[i] / temp;
  for (i = 0; i < n; i++) { ex = Math.exp(logits[i] / temp - m); pr[i] = ex; acc += ex; }
  for (i = 0; i < n; i++) pr[i] = pr[i] / acc;
  sum = 0;
  for (i = 0; i < n; i++) { sum += pr[i]; kept += 1; if (sum >= p) break; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  bw = (w - 40) / n;
  for (i = 0; i < n; i++) {
    x = 20 + i * bw;
    if (i < kept) {
      bh = pr[i] * h * 0.7;
      ctx.fillStyle = "#1f4b99";
      ctx.fillRect(x, h * 0.78 - bh, bw - 8, Math.max(2, bh));
    } else {
      ctx.fillStyle = "#e4d6c4";
      ctx.fillRect(x, h * 0.78 - 8, bw - 8, 8);
    }
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "18px sans-serif";
  ctx.fillText("masa " + Math.round(p * 100) / 100 + "  entran " + kept, 16, 28);
  ctx.fillStyle = "#5c564c";
  ctx.font = "14px sans-serif";
  ctx.fillText("temperatura " + Math.round(temp * 100) / 100, 16, 50);
}
`;

const WARM = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, warm = state.warm, floor = state.floor;
  var N = 100, i, s, a, b, c, p, vas = [], cos = [], mv = 0.0001, mc = 0.0001;
  var L = 36, R = w * 0.78, T = 28, B = h * 0.78;
  function X(v) { return L + (v / N) * (R - L); }
  function Y(v) { return B - v * (B - T); }
  for (i = 1; i <= N; i++) {
    s = i;
    a = 1 / Math.sqrt(s);
    b = s / (warm * Math.sqrt(warm));
    vas[i] = a < b ? a : b;
    if (vas[i] > mv) mv = vas[i];
    if (s < warm) c = s / warm;
    else {
      p = (s - warm) / (N - warm);
      c = floor + (1 - floor) * 0.5 * (1 + Math.cos(Math.PI * p));
    }
    cos[i] = c;
    if (c > mc) mc = c;
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 1; i <= N; i++) {
    if (i === 1) ctx.moveTo(X(i), Y(vas[i] / mv));
    else ctx.lineTo(X(i), Y(vas[i] / mv));
  }
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath();
  for (i = 1; i <= N; i++) {
    if (i === 1) ctx.moveTo(X(i), Y(cos[i] / mc));
    else ctx.lineTo(X(i), Y(cos[i] / mc));
  }
  ctx.stroke();
  ctx.strokeStyle = "#2e7d32";
  ctx.beginPath();
  ctx.moveTo(X(warm), T);
  ctx.lineTo(X(warm), B);
  ctx.stroke();
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText("el pico esta en el warmup", 16, 20);
  ctx.fillStyle = "#1f4b99";
  ctx.font = "13px sans-serif";
  ctx.fillText("1/raiz", R + 8, h * 0.4);
  ctx.fillStyle = "#c4512c";
  ctx.fillText("coseno", R + 8, h * 0.5);
}
`;

const DESCENT = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, width = state.width;
  var N = 30, i, x, te, tr, peak = 0, L = 36, R = w * 0.72, T = 36, B = h * 0.8;
  function testAt(v) {
    return 0.18 + 0.62 * Math.exp(-((v - 10) * (v - 10)) / 6) + 0.5 / (v + 1);
  }
  function trainAt(v) {
    if (v < 10) return 0.12 + 0.7 * (10 - v) / 10;
    return 0.04;
  }
  for (i = 1; i <= N; i++) if (testAt(i) > peak) peak = testAt(i);
  function X(v) { return L + (v / N) * (R - L); }
  function Y(v) { return B - (v / (peak + 0.05)) * (B - T); }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 1; i <= N; i++) {
    if (i === 1) ctx.moveTo(X(i), Y(trainAt(i)));
    else ctx.lineTo(X(i), Y(trainAt(i)));
  }
  ctx.stroke();
  ctx.strokeStyle = "#1f4b99";
  ctx.beginPath();
  for (i = 1; i <= N; i++) {
    if (i === 1) ctx.moveTo(X(i), Y(testAt(i)));
    else ctx.lineTo(X(i), Y(testAt(i)));
  }
  ctx.stroke();
  te = testAt(width);
  tr = trainAt(width);
  ctx.fillStyle = "#2e7d32";
  ctx.beginPath();
  ctx.arc(X(width), Y(te), 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(width > 8 && width < 14 ? "aqui se interpola" : (width >= 14 ? "el test vuelve a bajar" : "todavia falta modelo"), 16, 22);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(R + 16, B - tr / (peak + 0.05) * (B - T), 18, tr / (peak + 0.05) * (B - T));
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(R + 42, B - te / (peak + 0.05) * (B - T), 18, Math.max(2, te / (peak + 0.05) * (B - T)));
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#c4512c";
  ctx.fillText("train", R + 12, B + 16);
  ctx.fillStyle = "#1f4b99";
  ctx.fillText("test", R + 42, B + 16);
}
`;

const GROK = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, step = Math.round(state.step);
  var N = 100, i, tr, va, L = 36, R = w * 0.78, T = 40, B = h * 0.78;
  function trainAt(s) { return 1 - Math.exp(-s / 8); }
  function valAt(s) {
    if (s < 60) return 0.12;
    return 0.12 + (1 - Math.exp(-(s - 60) / 6)) * 0.86;
  }
  function X(v) { return L + (v / N) * (R - L); }
  function Y(v) { return B - v * (B - T); }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= N; i++) {
    tr = trainAt(i);
    if (i === 0) ctx.moveTo(X(i), Y(tr));
    else ctx.lineTo(X(i), Y(tr));
  }
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath();
  for (i = 0; i <= N; i++) {
    va = valAt(i);
    if (i === 0) ctx.moveTo(X(i), Y(va));
    else ctx.lineTo(X(i), Y(va));
  }
  ctx.stroke();
  ctx.strokeStyle = "#2e7d32";
  ctx.beginPath();
  ctx.moveTo(X(step), T);
  ctx.lineTo(X(step), B);
  ctx.stroke();
  tr = trainAt(step);
  va = valAt(step);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText(va < 0.3 ? "entrena ya, valida no" : "de pronto generaliza", 16, 24);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("azul entrena  " + Math.round(tr * 100) + "%", 16, h * 0.92);
  ctx.fillStyle = "#c4512c";
  ctx.fillText("coral valida  " + Math.round(va * 100) + "%", w * 0.48, h * 0.92);
}
`;

const TICKET = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, keep = state.keep;
  var n = 64, mag = [], i, j, greater, keepN, drawn = 0, ticket, random, side, x, y, cell;
  keepN = Math.round(keep * n);
  if (keepN < 1) keepN = 1;
  for (i = 0; i < n; i++) mag[i] = Math.abs(Math.sin(i * 1.3 + 0.4));
  side = Math.min(w * 0.42, h * 0.7);
  cell = side / 8;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < n; i++) {
    greater = 0;
    for (j = 0; j < n; j++) if (mag[j] > mag[i]) greater += 1;
    if (greater < keepN) {
      drawn += 1;
      x = 16 + (i % 8) * cell;
      y = 36 + Math.floor(i / 8) * cell;
      ctx.fillStyle = "#1f4b99";
      ctx.fillRect(x, y, cell - 3, cell - 3);
    }
  }
  ticket = 0.92 / (1 + Math.exp(-(keep - 0.14) * 28));
  random = 0.12 + 0.8 * keep;
  var bx = w * 0.56, bw = w * 0.32, base = h * 0.72;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(bx, base - ticket * h * 0.45, bw * 0.4, Math.max(2, ticket * h * 0.45));
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(bx + bw * 0.5, base - random * h * 0.45, bw * 0.4, Math.max(2, random * h * 0.45));
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText(keep < 0.35 ? "el boleto aguanta" : "casi toda la red", 16, 24);
  ctx.fillStyle = "#1f4b99";
  ctx.font = "13px sans-serif";
  ctx.fillText("boleto", bx, base + 18);
  ctx.fillStyle = "#c4512c";
  ctx.fillText("azar", bx + bw * 0.5, base + 18);
}
`;

const DETR_COPY = {
  explain: "El costo junta la clase y la caja, y el emparejamiento es el de menor costo. Con el peso de la clase bajo, cada query se queda con la caja barata. Si el peso sube, la línea cruza hacia la clase correcta.",
  questions: [
    { q: "¿Por qué la línea cruza cuando sube el peso de la clase?", why: "el costo de clase le gana al de la caja" },
    { q: "¿Quién elige el emparejamiento, cada query por su cuenta?", why: "el mínimo es sobre las asignaciones enteras" },
    { q: "¿Qué pasa con el costo si dos queries quieren el mismo objeto?", why: "una asignación usa cada objeto una vez" },
  ],
};

const NUCLEUS_COPY = {
  explain: "Nucleus se queda con la masa más chica que pasa de p, no con un conteo fijo. La temperatura aplana los logits, así que la misma masa deja entrar más tokens. Fría, uno o dos ya la llenan.",
  questions: [
    { q: "¿Por qué p = 0.9 no significa quedarse con el 90% de los tokens?", why: "el corte es de masa, no de conteo" },
    { q: "¿Qué cambia si la temperatura sube y p se queda?", why: "la masa se reparte y entran más tokens" },
    { q: "¿Cuándo un solo token ya llena la masa?", why: "con temperatura baja el softmax se concentra" },
  ],
};

export const AREAS = [
  widget("vit_patch", "vit-tokens", "Un parche grande se come los tokens", [
    knob("patch", "parche", 16, 112, 32, 8),
  ], VIT),
  widget("erf", "erf-glow", "El brillo es más chico que el campo teórico", [
    knob("depth", "profundidad", 1, 16, 8, 1),
    knob("ker", "kernel", 3, 7, 3, 2),
  ], ERF),
  widget("detr_match", "detr-assign", "La clase cruza el emparejamiento", [
    knob("class_w", "peso clase", 0, 1, 0.7, 0.05),
  ], DETR, DETR_COPY),
  widget("ppo_clip", "ppo-clip", "Pasado el clip, la ventaja ya no paga", [
    knob("eps", "epsilon", 0.05, 0.45, 0.2, 0.01),
    knob("adv", "ventaja", -2, 2, 1, 0.1),
    knob("ratio", "razon", 0, 2, 1.6, 0.05),
  ], PPO),
  widget("gae", "gae-credit", "Lambda devuelve el crédito hacia atrás", [
    knob("lam", "lambda", 0, 1, 0.85, 0.05),
  ], GAE),
  widget("gcn", "gcn-heat", "Una capa enciende a los vecinos", [
    knob("depth", "capas", 0, 4, 1, 1),
  ], GCN),
  widget("clip_align", "clip-space", "La temperatura elige el texto cercano", [
    knob("tau", "tau", 0.08, 1.2, 0.18, 0.02),
    knob("slide", "angulo", 0.2, 3.6, 1.35, 0.05),
  ], CLIP),
  widget("bpe_merge", "bpe-rare", "La palabra rara no entra en la fusión", [
    knob("merges", "fusiones", 0, 6, 3, 1),
  ], BPE),
  widget("paged_kv", "paged-waste", "Solo sobra hueco en la última página", [
    knob("page", "pagina", 8, 64, 16, 8),
  ], PAGED),
  widget("nucleus", "nucleus-temp", "La misma masa entra más si hay temperatura", [
    knob("p", "masa p", 0.2, 1, 0.9, 0.05),
    knob("temp", "temperatura", 0.3, 2, 0.45, 0.05),
  ], NUCLEUS, NUCLEUS_COPY),
  widget("warmup", "warm-cosine", "El warmup corre el pico y el coseno baja", [
    knob("warm", "warmup", 5, 70, 20, 1),
    knob("floor", "piso", 0, 0.6, 0.1, 0.05),
  ], WARM),
  widget("descent", "double-descent", "Al interpolar, el test vuelve a subir", [
    knob("width", "ancho", 1, 30, 10, 1),
  ], DESCENT),
  widget("grok", "grok-delay", "La validación generaliza mucho después", [
    knob("step", "paso", 0, 100, 42, 1),
  ], GROK),
  widget("lottery", "lottery-ticket", "El boleto aguanta y el azar no", [
    knob("keep", "quedan", 0.05, 1, 0.22, 0.01),
  ], TICKET),
];

export const AREAS_LEADS = AREAS.filter((item) => item.topic !== "detr_match" && item.topic !== "nucleus");
