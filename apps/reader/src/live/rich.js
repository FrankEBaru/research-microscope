// Multi-step draws. Papers and the newcomer question live in compass IDEAS.md.
// Numbers are illustrative except where the note in IDEAS says they come from the paper.

import { knob, widget } from "./banks.js";

const ATTN = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, stage = Math.round(state.stage), d = state.d;
  var sim = [0.15, 0.72, 1, -0.25];
  var name = ["el", "gato", "mira", "ya"];
  var V = [0.9, 0.15, 0.1, 0.2, 0.85, 0.15, 0.12, 0.2, 0.92, 0.75, 0.7, 0.12];
  var s = Math.sqrt(d < 1 ? 1 : d), i, k, m, acc;
  var raw = [], sc = [], pr = [], ps = [];
  function soft(src, dst) {
    m = src[0]; acc = 0;
    for (k = 1; k < 4; k++) if (src[k] > m) m = src[k];
    for (k = 0; k < 4; k++) { dst[k] = Math.exp(src[k] - m); acc += dst[k]; }
    for (k = 0; k < 4; k++) dst[k] = dst[k] / acc;
  }
  for (i = 0; i < 4; i++) { raw[i] = sim[i] * s; sc[i] = sim[i]; }
  soft(raw, pr); soft(sc, ps);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var tags = ["1 puntaje", "2 / raíz", "3 softmax", "4 mezcla"];
  var bw = Math.max(28, w * 0.09);
  ctx.font = "13px sans-serif";
  for (i = 0; i < 4; i++) {
    ctx.fillStyle = i === stage ? "#1d1a16" : "#b7aa9a";
    ctx.fillText(tags[i], w * 0.02 + i * w * 0.18, h * 0.06);
  }
  function colx(i) { return w * 0.08 + i * w * 0.2; }
  function bar(i, val, y0, scale, down) {
    var bh = Math.abs(val) / scale * (h * 0.42);
    bh = Math.min(bh, val < 0 ? 16 : h * 0.48);
    var y = val >= 0 || !down ? y0 - bh : y0;
    ctx.fillStyle = i === 2 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(colx(i), y, bw, Math.max(bh, 2));
  }
  if (stage < 2) {
    var y0 = h * 0.72;
    ctx.strokeStyle = "#e0d5c6";
    ctx.beginPath();
    ctx.moveTo(24, y0);
    ctx.lineTo(w - 16, y0);
    ctx.stroke();
    for (i = 0; i < 4; i++) {
      if (stage === 0) bar(i, raw[i], y0, 8, 1);
      else bar(i, sc[i], y0, 1.35, 1);
      ctx.fillStyle = "#1d1a16";
      ctx.font = "13px sans-serif";
      ctx.fillText(name[i] + " " + Math.round((stage === 0 ? raw[i] : sc[i]) * 10) / 10, colx(i), y0 + 22);
    }
    ctx.fillStyle = "#5c564c";
    ctx.font = "13px sans-serif";
    ctx.fillText(stage === 0 ? "Q·K crece con la raíz de d" : "Q·K / raíz de d, ya no crece", 24, h * 0.14);
  } else if (stage === 2) {
    var top = h * 0.46, bot = h * 0.84, lift = h * 0.28;
    ctx.font = "13px sans-serif";
    ctx.fillStyle = "#c4512c";
    ctx.fillText("sin raíz: se queda con una", 16, h * 0.14);
    ctx.fillStyle = "#1f4b99";
    ctx.fillText("con raíz: se reparte", 16, h * 0.54);
    for (i = 0; i < 4; i++) {
      ctx.fillStyle = i === 2 ? "#c4512c" : "#e7a090";
      ctx.fillRect(colx(i), top - pr[i] * lift, bw, pr[i] * lift);
      ctx.fillStyle = i === 2 ? "#1f4b99" : "#9db4dc";
      ctx.fillRect(colx(i), bot - ps[i] * lift, bw, ps[i] * lift);
      ctx.fillStyle = "#1d1a16";
      ctx.font = "13px sans-serif";
      ctx.fillText(name[i], colx(i) + 4, bot + 20);
    }
  } else {
    var mixA = [0, 0, 0], mixB = [0, 0, 0], c, cols = ["#c4512c", "#1f4b99", "#2e7d32"];
    for (i = 0; i < 4; i++) for (c = 0; c < 3; c++) {
      mixA[c] += pr[i] * V[i * 3 + c];
      mixB[c] += ps[i] * V[i * 3 + c];
    }
    ctx.font = "13px sans-serif";
    ctx.fillStyle = "#5c564c";
    ctx.fillText("pesos con raíz", 16, h * 0.16);
    for (i = 0; i < 4; i++) {
      ctx.fillStyle = i === 2 ? "#c4512c" : "#1f4b99";
      ctx.fillRect(w * 0.03 + i * w * 0.07, h * 0.62 - ps[i] * h * 0.36, w * 0.05, ps[i] * h * 0.36);
      ctx.fillStyle = "#1d1a16";
      ctx.fillText(name[i], w * 0.03 + i * w * 0.07, h * 0.68);
    }
    function trio(mix, x, label, col) {
      ctx.fillStyle = col;
      ctx.font = "13px sans-serif";
      ctx.fillText(label, x, h * 0.16);
      for (c = 0; c < 3; c++) {
        ctx.fillStyle = cols[c];
        ctx.fillRect(x, h * 0.22 + c * h * 0.12, Math.max(4, mix[c] * w * 0.22), h * 0.07);
      }
    }
    trio(mixA, w * 0.4, "sin raíz", "#c4512c");
    trio(mixB, w * 0.68, "con raíz", "#1f4b99");
  }
}
`;

const DENOISE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, step = Math.round(state.step), bT = state.beta;
  var T = 1000, b1 = 0.0001, s, acc = 1, bs, ab = [];
  ab[0] = 1;
  for (s = 1; s <= T; s++) {
    bs = b1 + (bT - b1) * (s - 1) / (T - 1);
    acc = acc * (1 - bs);
    ab[s] = acc;
  }
  function grid(x, y, cellpx, tt, hot) {
    var i, j, bit, eps, sig, noi, v, n;
    sig = Math.sqrt(ab[tt]);
    noi = Math.sqrt(Math.max(0, 1 - ab[tt]));
    for (i = 0; i < 8; i++) for (j = 0; j < 8; j++) {
      bit = (i === 3 || i === 4 || j === 3 || j === 4) ? 1 : 0;
      n = Math.sin(i * 12.9898 + j * 78.233) * 43758.5453;
      eps = (n - Math.floor(n)) * 2 - 1;
      v = sig * bit + noi * eps;
      ctx.fillStyle = v > 0.45 ? "#1f4b99" : (v > 0.12 ? "#e7a090" : "#efe6d8");
      ctx.fillRect(x + j * cellpx, y + i * cellpx, cellpx - 1, cellpx - 1);
    }
    if (hot) {
      ctx.strokeStyle = "#2e7d32";
      ctx.lineWidth = 2;
      ctx.strokeRect(x - 2, y - 2, cellpx * 8 + 3, cellpx * 8 + 3);
    }
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  if (step < 0) step = 0;
  if (step > T) step = T;
  var sig = Math.sqrt(ab[step]);
  var noi = Math.sqrt(Math.max(0, 1 - ab[step]));
  var cell = Math.floor(Math.min((h - 48) / 8, (w * 0.46) / 8));
  if (cell < 8) cell = 8;
  grid(16, 24, cell, step, 0);
  var rx = 32 + cell * 8;
  var marks = [0, 200, 400, 700, 1000], f, fr, near = 0, dist = 9999;
  var pitch = (w - rx - 16) / 5;
  var scell = Math.floor(Math.min(pitch / 8, 14));
  if (scell < 3) scell = 3;
  for (f = 0; f < 5; f++) if (Math.abs(marks[f] - step) < dist) { dist = Math.abs(marks[f] - step); near = f; }
  for (f = 0; f < 5; f++) {
    fr = marks[f];
    grid(rx + f * pitch, 28, scell, fr, f === near);
    ctx.fillStyle = "#5c564c";
    ctx.font = "11px sans-serif";
    ctx.fillText("" + fr, rx + f * pitch, 36 + scell * 8);
  }
  var ps = Math.round(sig * 100), pn = Math.round(noi * 100), s2 = Math.round(sig * sig * 100);
  ctx.fillStyle = "#5c564c";
  ctx.font = "12px sans-serif";
  ctx.fillText("azul alto   rosa medio   crema bajo", rx, h * 0.36);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText("t " + step + " / 1000", rx, h * 0.44);
  ctx.fillText("√a " + ps + "%    ruido " + pn + "%", rx, h * 0.52);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("cuadrados " + s2 + "+" + (100 - s2) + "=100", rx, h * 0.60);
  var mid = Math.round(Math.sqrt(ab[500]) * 100);
  ctx.fillText("ensucia, no limpia; e fijo, no gaussiana", rx, h * 0.68);
  ctx.fillText("en t=500 queda " + mid + "%, no 50", rx, h * 0.76);
  ctx.fillStyle = "#e4d6c4";
  ctx.fillRect(rx, h * 0.84, w - rx - 20, 8);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(rx, h * 0.84, Math.max(2, (w - rx - 20) * sig), 8);
}
`;

const RESID = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, depth = Math.round(state.depth), skip = state.skip;
  var e = [1, 0.85, 0.25, 0, 0, 0, 0, 0];
  var D = [
    0, 0, 0.15, 0.8, 0.1, 0, 0, 0,
    0, 0, 0, 0, 0.55, 0.7, 0, 0,
    0, 0, 0, 0, 0, 0.15, 0.75, 0.1,
    0, 0, 0, 0, 0, 0, 0.1, 0.65
  ];
  var cur = [], i, layer, v, x, y;
  for (i = 0; i < 8; i++) cur[i] = e[i];
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "11px sans-serif";
  ctx.fillStyle = "#8a8175";
  ctx.fillText("fila = dim del token", 8, 26);
  var pitch = Math.min(72, (w * 0.58) / 5);
  var cw = pitch - 8, ch = (h * 0.7) / 8;
  function paint(col) {
    for (i = 0; i < 8; i++) {
      v = cur[i];
      if (v < 0) v = 0;
      x = 16 + col * pitch;
      y = h * 0.08 + i * ch;
      ctx.fillStyle = v > 0.66 ? "#1f4b99" : (v > 0.28 ? "#7ea0d0" : (v > 0.06 ? "#d9e3f5" : "#efe6d8"));
      ctx.fillRect(x, y, cw, ch - 3);
      if (i < 2 && cur[i] > 0.2) {
        ctx.strokeStyle = "#c4512c";
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, cw, ch - 3);
      }
    }
    ctx.fillStyle = "#5c564c";
    ctx.font = "12px sans-serif";
    ctx.fillText(col === 0 ? "emb" : "L" + col, 16 + col * pitch, h * 0.08 + 8 * ch + 16);
  }
  paint(0);
  for (layer = 0; layer < depth; layer++) {
    for (i = 0; i < 8; i++) cur[i] = skip * cur[i] + D[layer * 8 + i];
    paint(layer + 1);
  }
  var left = depth === 0 ? 100 : Math.round(100 * Math.pow(skip, depth));
  var tx = 28 + 5 * pitch;
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("queda " + left + "% del token", tx, h * 0.22);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText(skip > 0.5 ? "y = x + cambio" : "red plana, sin suma", tx, h * 0.32);
  ctx.fillText(skip > 0.5 ? "el atajo lo conserva" : "sin atajo se apaga", tx, h * 0.4);
  ctx.fillText("contorno coral: entrada", tx, h * 0.66);
  ctx.fillText("0 o 1: nunca se cierra", tx, h * 0.74);
  ctx.fillText("azul lleno = valor alto", tx, h * 0.82);
  ctx.fillStyle = "#e4d6c4";
  ctx.fillRect(tx, h * 0.46, w - tx - 20, 14);
  ctx.fillStyle = left > 40 ? "#2e7d32" : "#c4512c";
  ctx.fillRect(tx, h * 0.46, Math.max(2, (w - tx - 20) * left / 100), 14);
  ctx.fillStyle = "#5c564c";
  ctx.fillText("atajo " + Math.round(skip * 100) / 100, tx, h * 0.58);
}
`;

const MOE = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, top = Math.round(state.k), factor = state.factor;
  var cap = Math.round((8 / 4) * factor);
  var L = [2.2, 0.2, 0, -0.4, 1.8, 0.4, 0.1, -0.2, 1.6, 0.3, 0.5, 0, 0.2, 2, 0.1, 0.3, 1.4, 0.2, 0.6, -0.1, 0.1, 0.2, 1.8, 0.4, 1.1, 0.5, 0.2, 0.3, 0, 0.3, 0.2, 1.7];
  var count = [0, 0, 0, 0], slot = [], drop = [], ti, e, k, b1, b2, got, di, fans = "";
  if (cap < 1) cap = 1;
  for (ti = 0; ti < 16; ti++) slot[ti] = -1;
  for (ti = 0; ti < 8; ti++) {
    b1 = 0; b2 = 1;
    if (L[ti * 4 + 1] > L[ti * 4]) { b1 = 1; b2 = 0; }
    for (e = 2; e < 4; e++) {
      if (L[ti * 4 + e] > L[ti * 4 + b1]) { b2 = b1; b1 = e; }
      else if (L[ti * 4 + e] > L[ti * 4 + b2]) b2 = e;
    }
    if (b1 === 0) fans = fans + " t" + ti;
    got = 0;
    var pick = [b1, b2];
    for (k = 0; k < top; k++) {
      e = pick[k];
      if (count[e] < cap) { count[e] += 1; slot[ti * 2 + k] = e; got = 1; }
    }
    if (!got) drop.push(ti);
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var used = [0, 0, 0, 0];
  var colw = (w - 28) / 4;
  var boxH = h * 0.58;
  ctx.font = "14px sans-serif";
  for (e = 0; e < 4; e++) {
    var x = 12 + e * colw;
    ctx.fillStyle = "#1d1a16";
    ctx.fillText("E" + e, x, h * 0.06);
    ctx.fillStyle = count[e] >= cap ? "#c4512c" : "#5c564c";
    ctx.fillText(count[e] + "/" + cap, x + 36, h * 0.06);
    ctx.strokeStyle = "#e0d5c6";
    ctx.strokeRect(x, h * 0.1, colw - 12, boxH);
  }
  var slotH = Math.min(28, (boxH - 16) / 6);
  for (ti = 0; ti < 8; ti++) {
    for (k = 0; k < top; k++) {
      e = slot[ti * 2 + k];
      if (e >= 0) {
        var x = 18 + e * colw;
        var y = h * 0.12 + used[e] * (slotH + 4);
        used[e] += 1;
        ctx.fillStyle = k === 0 ? "#1f4b99" : "#b9c8e6";
        ctx.fillRect(x, y, colw - 28, slotH);
        ctx.fillStyle = k === 0 ? "#f6f3ec" : "#1d1a16";
        ctx.font = "13px sans-serif";
        ctx.fillText("t" + ti, x + 8, y + slotH * 0.72);
      }
    }
  }
  ctx.font = "14px sans-serif";
  ctx.fillStyle = "#1d1a16";
  ctx.fillText("piden E0:" + fans, 12, h * 0.76);
  if (top > 1) ctx.fillText("claro: segunda", w * 0.72, h * 0.76);
  ctx.fillText("cupo (8/4) x " + Math.round(factor * 100) / 100 + " = " + cap, 12, h * 0.84);
  if (drop.length) {
    ctx.fillStyle = "#c4512c";
    ctx.fillText("atajo", 12, h * 0.93);
    for (di = 0; di < drop.length; di++) {
      ctx.fillStyle = "#c4512c";
      ctx.fillRect(64 + di * 44, h * 0.875, 36, 20);
      ctx.fillStyle = "#f6f3ec";
      ctx.fillText("t" + drop[di], 70 + di * 44, h * 0.915);
    }
  } else {
    ctx.fillStyle = "#2e7d32";
    ctx.fillText("nadie al atajo; sobra hueco", 12, h * 0.93);
  }
}
`;

const KV = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, len = Math.round(state.len), heads = Math.round(state.kv);
  var layers = 4, cells = layers * len * heads * 2, budget = 256, cap = 1536;
  var layer, tok, x, y, bh;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var rowH = h * 0.135;
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#8a8175";
  for (layer = 0; layer < layers; layer++) ctx.fillText("L" + (layer + 1), 8, h * 0.1 + layer * rowH);
  var cw = Math.min(22, (w - 56) / len - 2);
  if (cw < 4) cw = 4;
  for (layer = 0; layer < layers; layer++) {
    y = h * 0.04 + layer * rowH;
    for (tok = 0; tok < len; tok++) {
      x = 36 + tok * (cw + 3);
      bh = 4 + heads * rowH * 0.1;
      if (bh > rowH * 0.85) bh = rowH * 0.85;
      ctx.fillStyle = "#1f4b99";
      ctx.fillRect(x, y + rowH * 0.7 - bh, cw, bh * 0.55);
      ctx.fillStyle = "#c4512c";
      ctx.fillRect(x, y + rowH * 0.7 - bh * 0.45, cw, bh * 0.45);
    }
  }
  var regime = heads <= 1 ? "MQA" : (heads >= 8 ? "MHA" : "GQA");
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText("8 queries comparten " + heads + (heads === 1 ? " grupo KV" : " grupos KV"), 28, h * 0.62);
  ctx.fillText(regime + "   4 x " + len + " x " + heads + " x 2 = " + cells, 28, h * 0.70);
  ctx.fillStyle = "#e4d6c4";
  ctx.fillRect(28, h * 0.76, w - 48, 12);
  var mw = (w - 48) * cells / cap;
  if (mw > w - 48) mw = w - 48;
  ctx.fillStyle = cells > budget ? "#c4512c" : "#2e7d32";
  ctx.fillRect(28, h * 0.76, Math.max(2, mw), 12);
  var bx = 28 + (w - 48) * budget / cap;
  ctx.strokeStyle = "#1d1a16";
  ctx.beginPath();
  ctx.moveTo(bx, h * 0.74);
  ctx.lineTo(bx, h * 0.82);
  ctx.stroke();
  ctx.fillStyle = "#1d1a16";
  ctx.font = "12px sans-serif";
  ctx.fillText("cupo", bx + 6, h * 0.90);
  ctx.fillStyle = "#5c564c";
  ctx.font = "13px sans-serif";
  ctx.fillText("K azul  V coral    MHA = 8 grupos    MQA = 1    cupo de juguete", 28, h * 0.96);
}
`;

const QUANT = `
function draw(ctx, state, t) {
  var w = state.w, h = state.h, mag = state.mag, keep = Math.round(state.keep);
  var n = 16, xs = [], rec = [], i, ax, amax = 0, step, q, err = 0, cnt = 0;
  for (i = 0; i < n; i++) xs[i] = i === 7 ? mag : Math.sin(i * 1.7 + 0.4) * 0.35;
  for (i = 0; i < n; i++) {
    ax = xs[i] < 0 ? -xs[i] : xs[i];
    if (!(keep === 1 && ax > 6) && ax > amax) amax = ax;
  }
  if (amax < 1e-6) amax = 1e-6;
  step = amax / 127;
  for (i = 0; i < n; i++) {
    ax = xs[i] < 0 ? -xs[i] : xs[i];
    if (keep === 1 && ax > 6) rec[i] = xs[i];
    else {
      q = Math.round(xs[i] / step);
      if (q > 127) q = 127;
      if (q < -127) q = -127;
      rec[i] = q * step;
      err += (rec[i] - xs[i]) * (rec[i] - xs[i]);
      cnt += 1;
    }
  }
  err = cnt ? Math.sqrt(err / cnt) : 0;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  function Y(v) {
    if (v > 0.55) v = 0.55;
    if (v < -0.55) v = -0.55;
    return h * 0.52 - v * h * 0.4;
  }
  ctx.strokeStyle = "#e0d5c6";
  ctx.beginPath();
  ctx.moveTo(12, Y(0));
  ctx.lineTo(w - 12, Y(0));
  ctx.stroke();
  var gap = (w - 36) / n;
  for (i = 0; i < n; i++) {
    var x = 16 + i * gap;
    ax = xs[i] < 0 ? -xs[i] : xs[i];
    var held = keep === 1 && ax > 6;
    ctx.strokeStyle = "#b7aa9a";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x + 4, Y(0));
    ctx.lineTo(x + 4, Y(xs[i]));
    ctx.stroke();
    ctx.fillStyle = held ? "#2e7d32" : "#1f4b99";
    var y1 = Y(0), y2 = Y(rec[i]);
    var top = y1 < y2 ? y1 : y2;
    var bw = Math.max(6, gap * 0.34);
    ctx.fillRect(x + gap * 0.4, top, bw, Math.max(2, Math.abs(y2 - y1)));
    if (!held && Math.abs(xs[i] - rec[i]) > 0.08) {
      ctx.fillStyle = "#c4512c";
      ctx.fillRect(x + gap * 0.4, Y(xs[i]) - 2, bw, 4);
    }
    if (i === 7 && ax > 1.15) {
      ctx.fillStyle = "#c4512c";
      ctx.font = "13px sans-serif";
      ctx.fillText("" + Math.round(mag), x, h * 0.1);
    }
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText("paso = máx/127 = " + Math.round(step * 1000) / 1000, 12, 22);
  ctx.fillStyle = err > 0.05 ? "#c4512c" : "#2e7d32";
  ctx.fillText(err > 0.05 ? "un valor se come el paso" : "el paso cabe en los chicos", w * 0.42, 22);
  ctx.fillStyle = "#5c564c";
  ctx.font = "11px sans-serif";
  ctx.fillText(keep === 1 ? "gris: valor   azul: cuantizado   verde: se quedó afuera" : "gris: valor   azul: cuantizado   coral: se movió", 12, h - 8);
}
`;

const ATTN_COPY = {
  explain: "Una cabeza hace cuatro pasos. Q por K crece con la dimensión, y por eso se divide entre la raíz de d_k. Sin esa división el softmax se queda con una clave. Con ella, los pesos mezclan varios valores.",
  questions: [
    { q: "¿Por qué el puntaje crudo se queda con una sola clave?", why: "crece con la raíz de d_k y el softmax se afila" },
    { q: "¿Qué cambia al dividir entre la raíz antes del softmax?", why: "más de una clave conserva peso" },
    { q: "¿Qué se mezcla al final, las claves o los valores?", why: "los valores, pesados por el softmax con raíz" },
  ],
};

const DENOISE_COPY = {
  explain: "Ho 2006.11239, proceso directo: cada paso mete ruido, no limpia. x_t = √ᾱ x0 + √(1−ᾱ) ε, ᾱ producto de (1−β), β lineal de 0.0001 al beta final, en 1000 pasos. El ε pintado es un seno fijo, no la gaussiana. En t=500 la señal no es 50%: mira el número y sube el beta final.",
  questions: [
    { q: "¿Por qué en t=200 el plus sigue y la señal marca 81%?", why: "recién va el producto de (1−β); todavía queda ᾱ" },
    { q: "¿En t=500 queda la mitad de la señal?", why: "no: el número del lienzo no es 50" },
    { q: "¿Subir el beta final borra antes, en el mismo t?", why: "el producto de (1−β) cae más rápido" },
    { q: "¿Este dibujo es el modelo limpiando, o el proceso que ensucia?", why: "el directo, que ensucia; limpiar es el inverso" },
  ],
};

const RESID_COPY = {
  explain: "He et al. 1512.03385: y = F(x) + x. El atajo copia la entrada y la capa escribe el cambio. El control es solo 0 o 1: «identity shortcuts are never closed». En 0 ves la red plana, que entrena peor. El tablero y el % son un ejemplo, no ImageNet. Contorno coral: la entrada.",
  questions: [
    { q: "¿Por qué el contorno coral sigue en L4 si cada capa escribe algo?", why: "escribe el cambio; la entrada se suma, no se reemplaza" },
    { q: "¿Qué se apaga si pones el atajo en 0?", why: "la red plana: las dos filas de la entrada" },
    { q: "¿Las filas nuevas son la entrada o lo que escribió la capa?", why: "lo que escribió la capa; la entrada es el contorno" },
    { q: "¿El 100% es el error del paper en ImageNet?", why: "no: es cuánto del token de este ejemplo sigue ahí" },
  ],
};

export const RICH = [
  widget("attention_scale", "attn-walk", "La cabeza, del puntaje a la mezcla", [
    knob("stage", "paso", 0, 3, 2, 1),
    knob("d", "d_k", 4, 128, 64, 4),
  ], ATTN, ATTN_COPY),
  widget("noise_schedule", "denoise-strip", "Ho disuelve el dibujo en mil pasos", [
    knob("step", "paso t", 0, 1000, 200, 20),
    knob("beta", "beta final", 0.005, 0.05, 0.02, 0.001),
  ], DENOISE, DENOISE_COPY),
  widget("residual", "resid-stream", "El atajo se lleva el token de capa en capa", [
    knob("depth", "capa", 0, 4, 4, 1),
    knob("skip", "atajo", 0, 1, 1, 1),
  ], RESID, RESID_COPY),
  widget("moe", "moe-drop", "El experto lleno deja tokens afuera", [
    knob("k", "k", 1, 2, 1, 1),
    knob("factor", "factor", 0.5, 2.5, 1, 0.25),
  ], MOE, {
    explain: "Fedus et al. 2101.03961: cada token va al experto de mayor puntaje. Cupo = (tokens / expertos) × factor. Si se llena, «computation is skipped» y el token sigue por el atajo. Un factor grande deja hueco y gasta de más. Los puntajes son un ejemplo.",
    questions: [
      { q: "¿Por qué t2, t4 y t6 no entran a un experto con factor 1?", why: "E0 ya va 2/2; el cupo es (8/4) por 1" },
      { q: "¿A dónde van los que no cupieron, se pierden?", why: "no: el lienzo los pone en el atajo, sin experto" },
      { q: "¿k=2 devuelve a t2 y t4, o también deja a alguien nuevo en el atajo?", why: "vuelven t2 y t4; t7 cae porque el segundo puesto llenó E3" },
      { q: "¿Por qué un factor de 2 deja casillas vacías?", why: "el cupo crece y sobra buffer, que también cuesta" },
    ],
  }),
  widget("gqa", "kv-grow", "El cache crece con el texto y con los grupos", [
    knob("len", "tokens", 1, 24, 12, 1),
    knob("kv", "grupos KV", 1, 8, 8, 1),
  ], KV, {
    explain: "Ainslie et al. 2305.13245: GQA comparte K y V por grupo, «interpolating between multi-head and multi-query». MHA es 8 grupos y MQA es 1. Cache = capas × tokens × grupos × 2; las cabezas que preguntan no cuentan. El cupo y las 4 capas son de juguete, no una GPU.",
    questions: [
      { q: "¿Por qué 12 tokens y 8 grupos pasan el cupo?", why: "4 x 12 x 8 x 2 = 768, y la raya está en 256" },
      { q: "¿Qué baja si pones 1 grupo: el texto o las copias de K y V?", why: "las copias; el texto sigue en 12 tokens" },
      { q: "¿MQA y MHA son los extremos de este control?", why: "sí: 1 grupo es MQA y 8 es MHA" },
      { q: "¿La raya del cupo es la memoria de una GPU?", why: "no: es un cupo de juguete para ver cuándo se pasa" },
    ],
  }),
  widget("quant", "int8-outlier", "Un valor grande se come el paso", [
    knob("mag", "magnitud", 1, 120, 90, 1),
    knob("keep", "dejar afuera", 0, 1, 0, 1),
  ], QUANT),
];

export const RICH_LEADS = RICH.filter((item) => item.id === "moe-drop" || item.id === "kv-grow" || item.id === "int8-outlier");
