// Hand-written draws for the explore pass. Same contract shape as the first 100.
// Numbers that come from a paper are named in compass equipo-artefactos/IDEAS.md.
// Everything drawn here is illustrative.

import { knob, widget } from "./banks.js";

const PE_SINCOS = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base, p = state.pos, d = 64, N = 64;
  var rows = [0, 4, 10, 16], r, i, q, y0, y, f, rh;
  function X(q) { return 26 + (q / N) * (w - 36); }
  function freq(k) { return 1 / Math.pow(base, (2 * k) / d); }
  function sim(a, b) {
    var acc = 0, k, fr;
    for (k = 0; k < d / 2; k++) {
      fr = freq(k);
      acc += Math.sin(a * fr) * Math.sin(b * fr) + Math.cos(a * fr) * Math.cos(b * fr);
    }
    return acc / (d / 2);
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  rh = (h * 0.56) / rows.length;
  for (r = 0; r < rows.length; r++) {
    y0 = 8 + r * rh + rh * 0.5;
    f = freq(rows[r]);
    ctx.font = "10px sans-serif";
    ctx.fillStyle = "#8a8175";
    ctx.fillText("" + rows[r], 2, y0 + 3);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "#1f4b99";
    ctx.beginPath();
    for (i = 0; i <= N; i++) {
      q = i;
      y = y0 - Math.sin(q * f) * rh * 0.34;
      if (i === 0) ctx.moveTo(X(q), y); else ctx.lineTo(X(q), y);
    }
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#c4512c";
    ctx.beginPath();
    for (i = 0; i <= N; i++) {
      q = i;
      y = y0 - Math.cos(q * f) * rh * 0.34;
      if (i === 0) ctx.moveTo(X(q), y); else ctx.lineTo(X(q), y);
    }
    ctx.stroke();
    ctx.fillStyle = "#1f4b99";
    ctx.beginPath();
    ctx.arc(X(p), y0 - Math.sin(p * f) * rh * 0.34, 2.6, 0, 6.2832);
    ctx.fill();
    ctx.fillStyle = "#c4512c";
    ctx.beginPath();
    ctx.arc(X(p), y0 - Math.cos(p * f) * rh * 0.34, 2.3, 0, 6.2832);
    ctx.fill();
  }
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(X(p), 4);
  ctx.lineTo(X(p), h * 0.58);
  ctx.stroke();
  var sy = h * 0.66, sh = h * 0.26;
  ctx.fillStyle = "#5c564c";
  ctx.font = "10px sans-serif";
  ctx.fillText("parecido", 2, sy + 4);
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  for (i = 0; i <= N; i++) {
    y = sy + sh - ((sim(p, i) + 0.2) / 1.35) * sh;
    if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);
  }
  ctx.stroke();
}
`;

const ROPE_SHIFT = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, m = state.m + state.shift, n = state.n + state.shift;
  var th = [1, 0.32, 0.1], qa = [0.4, 1.1, 2.1], ka = [1.5, 0.25, 2.5];
  var i, s = 0, r = Math.min(h * 0.16, w / 11);
  function arrow(cx, cy, a, col) {
    ctx.strokeStyle = col;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + r * Math.cos(a), cy - r * Math.sin(a));
    ctx.stroke();
    ctx.fillStyle = col;
    ctx.beginPath();
    ctx.arc(cx + r * Math.cos(a), cy - r * Math.sin(a), 3, 0, 6.2832);
    ctx.fill();
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    var cx = w * (0.16 + 0.26 * i), cy = h * 0.3;
    var aq = qa[i] + m * th[i], ak = ka[i] + n * th[i];
    ctx.strokeStyle = "#e0d5c6";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 6.2832);
    ctx.stroke();
    arrow(cx, cy, aq, "#c4512c");
    arrow(cx, cy, ak, "#1f4b99");
    s += Math.cos(aq - ak);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "13px sans-serif";
  ctx.fillText("q·k " + Math.round(s * 100) / 100, w * 0.78, h * 0.16);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("m-n " + (state.m - state.n), w * 0.78, h * 0.16 + 16);
  var gx = 28, gy = h * 0.64, gw = w - 48, gh = h * 0.26, k, v;
  ctx.fillStyle = "#5c564c";
  ctx.font = "10px sans-serif";
  ctx.fillText("q·k al desplazar (la distancia no cambia)", gx, gy - 4);
  ctx.strokeStyle = "#e0d5c6";
  ctx.strokeRect(gx, gy, gw, gh);
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (k = 0; k <= 40; k++) {
    v = 0;
    for (i = 0; i < 3; i++) v += Math.cos(qa[i] - ka[i] + (state.m - state.n) * th[i]);
    if (k === 0) ctx.moveTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));
    else ctx.lineTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));
  }
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(gx + gw * state.shift / 40, gy + gh * (1 - (s + 3) / 6), 4, 0, 6.2832);
  ctx.fill();
}
`;

const ADAM = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, lr = state.lr, b2 = state.beta2, b1 = 0.9, eps = 1e-8;
  var x0 = 28, y0 = 14, pw = w * 0.68, ph = h - 28;
  function X(x) { return x0 + (x + 1.5) / 3 * pw; }
  function Y(y) { return y0 + (1.15 - y) / 2.3 * ph; }
  var levels = [0.5, 1.5, 3, 6, 9], li, a, c, ct, st;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#e4d6c4";
  ctx.lineWidth = 1;
  for (li = 0; li < levels.length; li++) {
    c = levels[li];
    ctx.beginPath();
    for (a = 0; a <= 48; a++) {
      ct = Math.cos(a / 48 * 6.2832);
      st = Math.sin(a / 48 * 6.2832);
      var px = Math.sqrt(2 * c) * ct, py = Math.sqrt(c / 20) * st;
      if (a === 0) ctx.moveTo(X(px), Y(py)); else ctx.lineTo(X(px), Y(py));
    }
    ctx.stroke();
  }
  function path(kind) {
    var x = -1.15, y = 0.55, mx = 0, my = 0, vx = 0, vy = 0, step, gx, gy, out = 0;
    ctx.beginPath();
    ctx.moveTo(X(x), Y(y));
    for (step = 1; step <= 26; step++) {
      gx = x; gy = 40 * y;
      if (kind === 0) { x -= lr * gx; y -= lr * gy; }
      else {
        mx = b1 * mx + (1 - b1) * gx; my = b1 * my + (1 - b1) * gy;
        vx = b2 * vx + (1 - b2) * gx * gx; vy = b2 * vy + (1 - b2) * gy * gy;
        var mhx = mx / (1 - Math.pow(b1, step)), mhy = my / (1 - Math.pow(b1, step));
        var vhx = vx / (1 - Math.pow(b2, step)), vhy = vy / (1 - Math.pow(b2, step));
        x -= lr * mhx / (Math.sqrt(vhx) + eps);
        y -= lr * mhy / (Math.sqrt(vhy) + eps);
      }
      if (x > 1.45 || x < -1.45 || y > 1.1 || y < -1.1) { out = 1; break; }
      ctx.lineTo(X(x), Y(y));
    }
    ctx.stroke();
    return out;
  }
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  var sgdOut = path(0);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  path(1);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(x0 + pw + 8, 28, 10, 10);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(x0 + pw + 8, 48, 10, 10);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#1d1a16";
  ctx.fillText("SGD", x0 + pw + 22, 37);
  ctx.fillText("Adam", x0 + pw + 22, 57);
  if (sgdOut) {
    ctx.fillStyle = "#c4512c";
    ctx.fillText("SGD se sale", x0 + pw + 8, 80);
  }
}
`;

const LORA = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, r = Math.round(state.rank), n = 8, i, j, v, left;
  function val(i, j, rank) {
    var v = 0;
    if (rank >= 1 && i >= 3 && i <= 4) v += 1;
    if (rank >= 2 && j >= 3 && j <= 4) v += 1;
    if (rank >= 3 && i <= 1) v += 1;
    return v;
  }
  function paint(x, rank) {
    var cw = 13, ch = 13;
    for (i = 0; i < n; i++) for (j = 0; j < n; j++) {
      v = val(i, j, rank);
      ctx.fillStyle = v <= 0 ? "#efe6d8" : (v < 1.5 ? "#7ea0d0" : "#1f4b99");
      ctx.fillRect(x + j * cw, 28 + i * ch, cw - 2, ch - 2);
    }
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("rango 3", 16, 18);
  ctx.fillText("rango " + r, 150, 18);
  paint(16, 3);
  paint(150, r);
  var d = 4096, lo = 2 * d * r, hi = d * d, times = Math.round(hi / lo);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "12px sans-serif";
  ctx.fillText("capa 4096:  " + lo + "   frente a   " + hi, 16, h - 28);
  ctx.fillText("el rango " + r + " es 1/" + times + " del ajuste completo", 16, h - 10);
}
`;

const KL = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, beta = state.beta;
  var name = ["si", "ok", "eh", "bueno", "ja"];
  var ref = [0.42, 0.28, 0.16, 0.1, 0.04];
  var reward = [0.1, 0.3, 0.5, 0.6, 2.4];
  var raw = [], z = 0, i, p = [], kl = 0;
  for (i = 0; i < 5; i++) { raw[i] = ref[i] * Math.exp(reward[i] / beta); z += raw[i]; }
  for (i = 0; i < 5; i++) { p[i] = raw[i] / z; kl += p[i] * Math.log(p[i] / ref[i]); }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var bw = (w - 36) / 5, bh = h * 0.28;
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("referencia", 8, 16);
  ctx.fillText("politica", 8, h * 0.48);
  for (i = 0; i < 5; i++) {
    var x = 16 + i * bw;
    ctx.fillStyle = "#e4d6c4";
    ctx.fillRect(x, 24, bw - 10, bh);
    ctx.fillStyle = "#8a8175";
    ctx.fillRect(x, 24 + bh * (1 - ref[i] / 0.5), bw - 10, bh * ref[i] / 0.5);
    ctx.fillStyle = "#d9e3f5";
    ctx.fillRect(x, h * 0.5, bw - 10, bh);
    ctx.fillStyle = i === 4 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(x, h * 0.5 + bh * (1 - Math.min(p[i], 0.95) / 0.95), bw - 10, bh * Math.min(p[i], 0.95) / 0.95);
    ctx.fillStyle = "#1d1a16";
    ctx.fillText(name[i], x, h - 8);
  }
  ctx.fillText("KL " + Math.round(kl * 100) / 100, w - 70, 16);
}
`;

const BEAM = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, width = Math.round(state.width);
  var w1 = ["el", "un", "ya"];
  var s1 = [-0.15, -0.55, -1.8];
  var w2 = [["día", "fin", "mar"], ["gato", "perro", "sol"], ["no", "va", "es"]];
  var s2 = [[-2.2, -2.5, -2.8], [-0.1, -1.1, -1.6], [-1, -1.2, -1.4]];
  var order = [0, 1, 2], i, j, tmp, a, b, tot, best = -1e9, phrase = "", bi = 0;
  for (i = 0; i < 3; i++) for (j = i + 1; j < 3; j++) if (s1[order[j]] > s1[order[i]]) {
    tmp = order[i]; order[i] = order[j]; order[j] = tmp;
  }
  for (a = 0; a < width; a++) {
    i = order[a];
    for (b = 0; b < 3; b++) {
      tot = s1[i] + s2[i][b];
      if (tot > best) { best = tot; phrase = w1[i] + " " + w2[i][b]; bi = i; }
    }
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("primer token", 16, 16);
  ctx.fillText("frase completa", w * 0.48, 16);
  for (a = 0; a < 3; a++) {
    i = order[a];
    var y = 28 + a * 46, kept = a < width;
    var bestB = 0;
    for (b = 1; b < 3; b++) if (s2[i][b] > s2[i][bestB]) bestB = b;
    var total = s1[i] + s2[i][bestB];
    ctx.fillStyle = kept ? "#1f4b99" : "#e4d6c4";
    ctx.fillRect(16, y, (s1[i] + 2.2) / 2.2 * 90, 16);
    ctx.fillStyle = "#1d1a16";
    ctx.fillText(w1[i], 20, y + 12);
    ctx.fillStyle = kept ? (i === bi ? "#c4512c" : "#1f4b99") : "#e4d6c4";
    ctx.fillRect(w * 0.48, y, Math.max(8, (total + 3.2) / 3.2 * 120), 16);
    ctx.fillStyle = "#1d1a16";
    ctx.fillText(w1[i] + " " + w2[i][bestB], w * 0.48 + 4, y + 12);
  }
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.5;
  ctx.strokeRect(10, 24, w * 0.42, width * 46 - 4);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#1d1a16";
  ctx.fillText("devuelve: " + phrase, 16, h - 10);
}
`;

const BN = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, z = [-1.5, -0.8, -0.2, 0.35, 0.9, 1.45];
  var n = 6, i, mean = 0, v = 0, raw = [], hat = [], out = [];
  for (i = 0; i < n; i++) { raw[i] = state.shift + state.scale * z[i]; mean += raw[i]; }
  mean /= n;
  for (i = 0; i < n; i++) v += (raw[i] - mean) * (raw[i] - mean);
  v = Math.sqrt(v / n) + 1e-6;
  for (i = 0; i < n; i++) { hat[i] = (raw[i] - mean) / v; out[i] = state.gamma * hat[i] + state.bias; }
  function row(vals, y, col, label) {
    ctx.strokeStyle = "#e4d6c4";
    ctx.beginPath();
    ctx.moveTo(20, y);
    ctx.lineTo(w - 16, y);
    ctx.stroke();
    ctx.fillStyle = col;
    for (i = 0; i < n; i++) {
      var x = w * 0.5 + vals[i] * 28;
      if (x < 16) x = 16;
      if (x > w - 16) x = w - 16;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, 6.2832);
      ctx.fill();
    }
    ctx.fillStyle = "#5c564c";
    ctx.font = "11px sans-serif";
    ctx.fillText(label, 8, y - 10);
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.lineWidth = 1;
  row(raw, 48, "#c4512c", "entrada");
  row(hat, 108, "#1f4b99", "tras el lote");
  row(out, 168, "#2e7d32", "gamma y beta");
}
`;

const CHINCHILLA = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, C = Math.pow(10, state.logc);
  var E = 1.69, A = 406.4, B = 410.7, a = 0.34, b = 0.28;
  var x0 = 36, y0 = h - 28, gw = w - 52, gh = h - 58;
  var nlo = 7, nhi = 12.2, Llo = 1.75, Lhi = 3.6;
  var k, ln, N, D, L, best = 0, bl = 1e9;
  function X(ln) { return x0 + (ln - nlo) / (nhi - nlo) * gw; }
  function Y(L) { return y0 - (Math.min(L, Lhi) - Llo) / (Lhi - Llo) * gh; }
  function sci(v) {
    var e = Math.floor(Math.log(v) / Math.log(10));
    var m = Math.round((v / Math.pow(10, e)) * 10) / 10;
    return m + "e" + e;
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#e4d6c4";
  ctx.strokeRect(x0, y0 - gh, gw, gh);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (k = 0; k <= 160; k++) {
    ln = nlo + (nhi - nlo) * k / 160;
    N = Math.pow(10, ln);
    D = C / (6 * N);
    L = E + A / Math.pow(N, a) + B / Math.pow(D, b);
    if (L < bl) { bl = L; best = ln; }
    if (k === 0) ctx.moveTo(X(ln), Y(L)); else ctx.lineTo(X(ln), Y(L));
  }
  ctx.stroke();
  N = Math.pow(10, best);
  D = C / (6 * N);
  ctx.fillStyle = "#2e7d32";
  ctx.beginPath();
  ctx.arc(X(best), Y(bl), 5, 0, 6.2832);
  ctx.fill();
  ctx.font = "10px sans-serif";
  ctx.fillStyle = "#8a8175";
  for (k = 7; k <= 12; k++) ctx.fillText("1e" + k, X(k) - 8, y0 + 12);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "12px sans-serif";
  ctx.fillText("N " + sci(N) + "   datos " + sci(D) + "   perdida " + Math.round(bl * 1000) / 1000, x0, 16);
}
`;

const SPEC = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, a = state.agree, c = state.cost;
  var g, f = [], best = 1, top = 0;
  for (g = 1; g <= 12; g++) {
    f[g] = (1 - Math.pow(a, g + 1)) / ((1 - a) * (g * c + 1));
    if (f[g] > f[best]) best = g;
    if (f[g] > top) top = f[g];
  }
  top = Math.max(top, 1.15) * 1.15;
  var x0 = 32, y0 = h - 26, gw = w - 52, gh = h - 52;
  function X(g) { return x0 + (g - 1) / 11 * gw; }
  function Y(v) { return y0 - v / top * gh; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#e4d6c4";
  ctx.strokeRect(x0, y0 - gh, gw, gh);
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x0, Y(1));
  ctx.lineTo(x0 + gw, Y(1));
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  ctx.font = "10px sans-serif";
  ctx.fillText("1x", x0 + gw - 16, Y(1) - 4);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (g = 1; g <= 12; g++) {
    if (g === 1) ctx.moveTo(X(g), Y(f[g])); else ctx.lineTo(X(g), Y(f[g]));
  }
  ctx.stroke();
  ctx.fillStyle = "#2e7d32";
  ctx.beginPath();
  ctx.arc(X(best), Y(f[best]), 5, 0, 6.2832);
  ctx.fill();
  ctx.fillStyle = "#5c564c";
  ctx.font = "10px sans-serif";
  for (g = 1; g <= 12; g += 1) if (g % 2 === 1) ctx.fillText("" + g, X(g) - 3, y0 + 12);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "12px sans-serif";
  ctx.fillText("mejor largo " + best + "   " + Math.round(f[best] * 10) / 10 + "x", x0, 16);
}
`;

const ONLINE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, B = Math.round(state.blocks), n = 16, seed = 4242, s = [], i, b;
  function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
  for (i = 0; i < n; i++) s[i] = rnd() * 5 - 1.2;
  var M = -1e9, Z = 0, m = -1e9, l = 0;
  for (i = 0; i < n; i++) if (s[i] > M) M = s[i];
  for (i = 0; i < n; i++) Z += Math.exp(s[i] - M);
  for (b = 0; b < B; b++) {
    var mo = m, add = 0;
    for (i = 4 * b; i < 4 * b + 4; i++) if (s[i] > m) m = s[i];
    for (i = 4 * b; i < 4 * b + 4; i++) add += Math.exp(s[i] - m);
    l = l * (b === 0 ? 1 : Math.exp(mo - m)) + add;
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var bw = (w - 24) / n, top = 22, sh = h * 0.28, py = h * 0.58, ph = h * 0.32, dmax = 0;
  for (i = 0; i < n; i++) {
    var x = 12 + i * bw, seen = i < 4 * B;
    ctx.fillStyle = seen ? "#1f4b99" : "#e4d6c4";
    var bh = (s[i] + 1.2) / 6.2 * sh;
    ctx.fillRect(x, top + sh - bh, bw - 3, bh);
    var full = Math.exp(s[i] - M) / Z;
    var part = seen ? Math.exp(s[i] - m) / l : 0;
    ctx.strokeStyle = "#1d1a16";
    ctx.lineWidth = 1;
    ctx.strokeRect(x, py + ph - full / 0.55 * ph, bw - 3, full / 0.55 * ph);
    ctx.fillStyle = "#2e7d32";
    ctx.fillRect(x + 1, py + ph - part / 0.55 * ph, bw - 5, part / 0.55 * ph);
    if (B === 4) dmax = Math.max(dmax, Math.abs(full - part));
  }
  ctx.fillStyle = "#5c564c";
  ctx.font = "11px sans-serif";
  ctx.fillText("verde: bloques vistos   contorno: lista completa", 12, 14);
  if (B === 4) {
    ctx.fillStyle = "#2e7d32";
    ctx.fillText("diferencia " + Math.round(dmax * 10000) / 10000, 12, h - 4);
  }
}
`;

const TAU = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, tau = state.tau < 0.05 ? 0.05 : state.tau;
  var ang = [0.3, 1.1, 2.0, 2.8, 4.0, 5.1];
  var rad = [0.55, 1.15, 1.35, 1.5, 1.25, 1.45];
  var sim = [], i, m = -1e9, z = 0, ex = [];
  for (i = 0; i < 6; i++) {
    sim[i] = Math.cos(ang[i]) / rad[i];
    sim[i] = sim[i] / tau;
    if (sim[i] > m) m = sim[i];
  }
  for (i = 0; i < 6; i++) { ex[i] = Math.exp(sim[i] - m); z += ex[i]; }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var cx = w * 0.28, cy = h * 0.52, sc = h * 0.28;
  ctx.strokeStyle = "#e4d6c4";
  ctx.beginPath();
  ctx.arc(cx, cy, 4, 0, 6.2832);
  ctx.stroke();
  ctx.fillStyle = "#1d1a16";
  ctx.beginPath();
  ctx.arc(cx, cy, 4, 0, 6.2832);
  ctx.fill();
  for (i = 0; i < 6; i++) {
    var x = cx + Math.cos(ang[i]) * rad[i] * sc, y = cy - Math.sin(ang[i]) * rad[i] * sc;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.beginPath();
    ctx.arc(x, y, i === 0 ? 6 : 4, 0, 6.2832);
    ctx.fill();
  }
  var bw = (w * 0.42) / 6, bh = h * 0.55, x0 = w * 0.55;
  for (i = 0; i < 6; i++) {
    var p = ex[i] / z;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(x0 + i * bw, h * 0.78 - p * bh, bw - 6, p * bh);
  }
  ctx.fillStyle = "#5c564c";
  ctx.font = "11px sans-serif";
  ctx.fillText("vecino " + Math.round(100 * ex[0] / z) + "%", x0, 18);
}
`;

const PE_COPY = {
  explain: "Cada par es un seno azul y un coseno coral. La base casi no toca la onda rápida de arriba y frena las de abajo. La curva es el parecido de la posición p con las demás; el pico cae en p.",
};

const SPEC_COPY = {
  explain: "El borrador propone varios tokens. Cada uno se acepta con la chance del acuerdo, y cada uno cuesta una fracción del modelo grande. La curva es el speedup según el largo; el punto verde es el largo que más conviene. Si sale caro, queda por debajo de 1.",
};

export const EXPLORE = [
  widget("positional_encoding", "pe-sincos", "Seno y coseno: lo cercano se parece", [
    knob("base", "base", 20, 100000, 10000, 20),
    knob("pos", "posición", 0, 64, 18, 1),
  ], PE_SINCOS, PE_COPY),
  widget("rope_relative", "rope-shift", "Mover los dos tokens no cambia el producto", [
    knob("shift", "desplaza", 0, 40, 0, 1),
    knob("m", "posición m", 0, 20, 3, 1),
    knob("n", "posición n", 0, 20, 8, 1),
  ], ROPE_SHIFT),
  widget("adam", "adam-valley", "En el valle, el segundo momento frena el rebote", [
    knob("lr", "paso lr", 0.01, 0.1, 0.04, 0.005),
    knob("beta2", "beta2", 0.8, 0.999, 0.99, 0.001),
  ], ADAM),
  widget("lora", "lora-rank", "Cada rango suma un patrón", [
    knob("rank", "rango", 1, 6, 2, 1),
  ], LORA),
  widget("kl_rlhf", "kl-policy", "Sin el KL, un token se queda con el premio", [
    knob("beta", "beta", 0.12, 4, 0.7, 0.02),
  ], KL),
  widget("beam", "beam-trap", "El haz ancho rescata el camino que empezó peor", [
    knob("width", "ancho", 1, 3, 1, 1),
  ], BEAM),
  widget("batchnorm", "bn-stable", "La escala de la entrada no cruza el lote", [
    knob("scale", "escala", 0.4, 3, 2.2, 0.1),
    knob("shift", "corrimiento", -1.5, 1.5, 0.8, 0.1),
    knob("gamma", "gamma", 0.3, 2.2, 1.8, 0.1),
    knob("bias", "beta", -1, 1, 0.35, 0.05),
  ], BN),
  widget("scaling", "chinchilla", "Con el mismo cómputo hay un tamaño que conviene", [
    knob("logc", "log10 FLOPs", 19, 25, 22, 0.25),
  ], CHINCHILLA),
  widget("speculative", "spec-best", "El borrador tiene un largo que conviene", [
    knob("agree", "acuerdo", 0.35, 0.95, 0.8, 0.01),
    knob("cost", "costo c", 0.02, 0.8, 0.1, 0.01),
  ], SPEC, SPEC_COPY),
  widget("online_softmax", "online-softmax", "Por bloques, y al final es el mismo softmax", [
    knob("blocks", "bloques", 1, 4, 2, 1),
  ], ONLINE),
  widget("contrastive_temp", "tau-near", "Tau bajo se queda con el vecino", [
    knob("tau", "tau", 0.07, 1.4, 0.2, 0.01),
  ], TAU),
];

const LEAD_IDS = {
  "rope-shift": 1,
  "adam-valley": 1,
  "lora-rank": 1,
  "kl-policy": 1,
  "beam-trap": 1,
  "bn-stable": 1,
  "chinchilla": 1,
  "online-softmax": 1,
};

export const LEADS = EXPLORE.filter((item) => LEAD_IDS[item.id]);
