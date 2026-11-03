// Hand-built figures for the sandbox gallery. Illustrative, not measurements.
import { GUEST } from "./guest.js";

function q(question, why) {
  return { q: question, why };
}

function knob(id, label, min, max, value, step) {
  return { id, label, min, max, value, step };
}

const PE = `function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base, pos = state.pos;
  var rows = [0, 2, 4, 8, 16], d = 64, i, k, x, qv, y, f, s, y0, idx;
  var left = 58, right = w - 16, span = right - left;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f4efe5";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "13px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  for (i = 0; i < rows.length; i++) {
    idx = rows[i];
    f = 1 / Math.pow(base, (2 * idx) / d);
    y0 = 28 + i * 36;
    ctx.fillStyle = "#6b6357";
    ctx.fillText("i=" + idx, 8, y0);
    ctx.beginPath();
    ctx.lineWidth = idx === 0 ? 2.4 : 1.7;
    ctx.strokeStyle = idx === 0 ? "#c2321f" : "#0b6782";
    for (x = left; x <= right; x += 2) {
      qv = ((x - left) / span) * 64;
      y = y0 - Math.sin(qv * f) * 13;
      if (x === left) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  x = left + (pos / 64) * span;
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x, 12);
  ctx.lineTo(x, 198);
  ctx.stroke();
  ctx.fillStyle = "#6b6357";
  ctx.textBaseline = "alphabetic";
  ctx.fillText("how alike two positions are", left, 232);
  ctx.strokeStyle = "#e2d9c8";
  ctx.beginPath();
  ctx.moveTo(left, 334);
  ctx.lineTo(right, 334);
  ctx.stroke();
  ctx.beginPath();
  ctx.lineWidth = 2.6;
  ctx.strokeStyle = "#127a55";
  for (qv = 0; qv <= 64; qv++) {
    s = 0;
    for (k = 0; k < 16; k++) {
      f = 1 / Math.pow(base, (2 * k) / d);
      s = s + Math.cos((pos - qv) * f);
    }
    s = s / 16;
    x = left + (qv / 64) * span;
    y = 334 - s * 86;
    if (qv === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.fillStyle = "#127a55";
  ctx.beginPath();
  ctx.arc(left + (pos / 64) * span, 334 - 86, 4, 0, Math.PI * 2);
  ctx.fill();
}`;

const ROPE = `function draw(ctx, state, t) {
  var w = state.w, h = state.h, m = state.m, base = state.base;
  var cx = 176, cy = 196, R = 118, freq, ang, k, a, x, y, dot, bh;
  freq = 1 / Math.pow(base, 16 / 64);
  ang = m * freq;
  dot = Math.cos(ang);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f4efe5";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#e2d9c8";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(cx - R - 18, cy);
  ctx.lineTo(cx + R + 18, cy);
  ctx.moveTo(cx, cy - R - 14);
  ctx.lineTo(cx, cy + R + 14);
  ctx.stroke();
  ctx.strokeStyle = "#e0a100";
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (k = 0; k <= 28; k++) {
    a = ang * (k / 28);
    x = cx + Math.cos(a) * 42;
    y = cy - Math.sin(a) * 42;
    if (k === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.strokeStyle = "#0b6782";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + R, cy);
  ctx.stroke();
  ctx.strokeStyle = "#c2321f";
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(ang) * R, cy - Math.sin(ang) * R);
  ctx.stroke();
  ctx.fillStyle = "#0b6782";
  ctx.beginPath();
  ctx.arc(cx + R, cy, 5.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#c2321f";
  ctx.beginPath();
  ctx.arc(cx + Math.cos(ang) * R, cy - Math.sin(ang) * R, 5.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = "14px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#0b6782";
  ctx.fillRect(390, 78, 14, 14);
  ctx.fillStyle = "#1d1a16";
  ctx.fillText("key at position 0", 412, 85);
  ctx.fillStyle = "#c2321f";
  ctx.fillRect(390, 104, 14, 14);
  ctx.fillStyle = "#1d1a16";
  ctx.fillText("query at token m", 412, 111);
  ctx.fillStyle = "#6b6357";
  ctx.fillText("their dot product", 390, 168);
  ctx.strokeStyle = "#e2d9c8";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(390, 250);
  ctx.lineTo(600, 250);
  ctx.stroke();
  ctx.fillStyle = dot >= 0 ? "#127a55" : "#c2321f";
  bh = Math.abs(dot) * 70;
  if (dot >= 0) ctx.fillRect(390, 250 - bh, 210, bh);
  else ctx.fillRect(390, 250, 210, bh);
  ctx.fillStyle = "#6b6357";
  ctx.font = "12px sans-serif";
  ctx.fillText("same way", 344, 236);
  ctx.fillText("opposite", 344, 268);
}`;

const SOFTMAX = `function draw(ctx, state, t) {
  var w = state.w, h = state.h, temp = state.temp;
  var logits = [2.2, 0.7, 0.0, -0.5, -1.1];
  var names = ["the", "cat", "sat", "on", "mat"];
  var i, m, exps = [], s = 0, p, bw, gap, x, bh, top, baseY;
  if (temp < 0.05) temp = 0.05;
  m = logits[0];
  for (i = 1; i < logits.length; i++) if (logits[i] > m) m = logits[i];
  for (i = 0; i < logits.length; i++) {
    exps[i] = Math.exp((logits[i] - m) / temp);
    s = s + exps[i];
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f4efe5";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "14px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#6b6357";
  ctx.fillText("chance of the next word", 28, 36);
  gap = 28;
  bw = (w - gap * (logits.length + 1)) / logits.length;
  baseY = h - 58;
  top = 64;
  ctx.strokeStyle = "#e2d9c8";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(gap, baseY - (1 / logits.length) * (baseY - top));
  ctx.lineTo(w - gap, baseY - (1 / logits.length) * (baseY - top));
  ctx.stroke();
  ctx.fillStyle = "#6b6357";
  ctx.font = "12px sans-serif";
  ctx.fillText("even split", w - 110, baseY - (1 / logits.length) * (baseY - top) - 6);
  for (i = 0; i < logits.length; i++) {
    p = exps[i] / s;
    bh = p * (baseY - top);
    x = gap + i * (bw + gap);
    ctx.fillStyle = i === 0 ? "#c2321f" : "#0b6782";
    ctx.fillRect(x, baseY - bh, bw, bh);
    ctx.fillStyle = "#1d1a16";
    ctx.font = "16px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(names[i], x + bw / 2, h - 28);
  }
}`;

const ATTN = `function draw(ctx, state, t) {
  var w = state.w, h = state.h, d = state.d;
  var raw = [1.5, 0.55, 0.05, -0.35];
  var s = Math.sqrt(d < 1 ? 1 : d);
  var grown = [], flat = [], i, gap, bw, x, rowH;
  function probs(xs) {
    var m = xs[0], k, out = [], acc = 0;
    for (k = 1; k < xs.length; k++) if (xs[k] > m) m = xs[k];
    for (k = 0; k < xs.length; k++) { out[k] = Math.exp(xs[k] - m); acc = acc + out[k]; }
    for (k = 0; k < xs.length; k++) out[k] = out[k] / acc;
    return out;
  }
  for (i = 0; i < raw.length; i++) { grown[i] = raw[i] * s; flat[i] = raw[i]; }
  var top = probs(grown), bot = probs(flat);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f4efe5";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "15px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  gap = 18;
  bw = (w - 150 - gap * (raw.length + 1)) / raw.length;
  rowH = h * 0.28;
  function row(ps, y0, label, color) {
    var j, bh;
    ctx.fillStyle = "#1d1a16";
    ctx.font = "15px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(label, 16, y0 + 18);
    for (j = 0; j < ps.length; j++) {
      bh = ps[j] * rowH;
      x = 132 + gap + j * (bw + gap);
      ctx.fillStyle = "#e7e0d4";
      ctx.fillRect(x, y0, bw, rowH);
      ctx.fillStyle = color;
      ctx.fillRect(x, y0 + rowH - bh, bw, bh);
    }
  }
  row(top, 70, "no scale", "#c2321f");
  row(bot, 210, "divide by sqrt(d)", "#127a55");
}`;

const STD = `function draw(ctx, state, t) {
  var w = state.w, h = state.h, sigma = state.sigma, mu = state.mu;
  var zs = [-1.5, -0.8, -0.2, 0.35, 0.9, 1.45], i, v, x, y;
  function X(v) { return 36 + ((v + 8) / 16) * (w - 72); }
  function bell(center, spread, yBase, amp, color) {
    var px, val, g, py;
    ctx.beginPath();
    ctx.lineWidth = 2.4;
    ctx.strokeStyle = color;
    for (px = 36; px <= w - 36; px += 3) {
      val = -8 + ((px - 36) / (w - 72)) * 16;
      g = Math.exp(-0.5 * Math.pow((val - center) / spread, 2));
      py = yBase - g * amp;
      if (px === 36) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  }
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f4efe5";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "14px sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#6b6357";
  ctx.fillText("raw cloud", 36, 28);
  ctx.fillText("after dividing by sigma", 36, 196);
  bell(mu, sigma, 150, 78, "#c2321f");
  bell(0, 1, 324, 78, "#127a55");
  ctx.fillStyle = "#c2321f";
  for (i = 0; i < zs.length; i++) {
    v = mu + zs[i] * sigma;
    x = X(v);
    y = 150;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = "#127a55";
  for (i = 0; i < zs.length; i++) {
    x = X(zs[i]);
    y = 324;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(X(mu), 40);
  ctx.lineTo(X(mu), 156);
  ctx.stroke();
}`;

export const SHOWCASE = [
  ...GUEST,
  {
    claim: "Positional encodings use sine waves so nearby positions look alike. The base 10000 sets how fast those waves slow down.",
    widget: {
      id: "pe-peak",
      topic: "positional_encoding",
      title: "Nearby positions share a peak",
      explain: "Each row is one positional encoding frequency. The red wave is the fast pair and barely cares about the base. Drag the base and the lower waves stretch. The green curve is how alike position p is to every other position: it always peaks at p, and a larger base makes that peak wider.",
      questions: [
        q("Why does a larger base make nearby positions look more alike?", "the slow waves stretch, so the similarity peak gets wider"),
        q("Why keep a fast wave if the base barely changes it?", "that pair marks fine distance no matter how long the sentence is"),
        q("What is the green curve peaking on?", "the dot product of the two position vectors is highest at the same spot"),
      ],
      controls: [
        knob("base", "base", 10, 100000, 10000, 10),
        knob("pos", "position", 0, 64, 24, 1),
      ],
      draw: PE,
    },
  },
  {
    claim: "RoPE rotates a pair of dimensions by the token position, so the dot product depends on how far apart two tokens are.",
    widget: {
      id: "rope-turn",
      topic: "rope",
      title: "Position is an angle",
      explain: "RoPE turns the query as the token moves, and leaves the key at position 0. The yellow arc is that turn. The bar is their dot product: it falls as the query rotates away, and a larger base makes the same token index rotate less.",
      questions: [
        q("Why does moving the token rotate the query?", "RoPE adds an angle proportional to the position"),
        q("Why does a larger base rotate more slowly?", "the angle per token is smaller when the base is larger"),
        q("When is the dot product negative?", "the query has turned past a right angle from the key"),
      ],
      controls: [
        knob("m", "token m", 0, 40, 8, 1),
        knob("base", "base", 100, 100000, 10000, 100),
      ],
      draw: ROPE,
    },
  },
  {
    claim: "Softmax temperature sharpens or flattens the next-word distribution.",
    widget: {
      id: "softmax-melt",
      topic: "softmax_temperature",
      title: "Temperature melts the choice",
      explain: "The same five logits go through softmax. At a low temperature almost all of the chance sits on the largest logit. Raise it and the bars fall toward an even split, the gray line. The words are not changing. Only the temperature is.",
      questions: [
        q("Why does a low temperature pick one word?", "dividing by a small number exaggerates the largest logit"),
        q("What is the gray line?", "an even split, one chance in five, which high temperature approaches"),
        q("Are the logits changing, or the chances?", "the logits stay put and the temperature rescales them"),
      ],
      controls: [knob("temp", "temperature", 0.25, 4, 0.8, 0.05)],
      draw: SOFTMAX,
    },
  },
  {
    claim: "Attention scale divides the dot product by the square root of d so softmax does not collapse onto one key.",
    widget: {
      id: "attn-sqrt",
      topic: "attention_scale",
      title: "Without the square root, one key wins",
      explain: "The top row is softmax of the raw dot products times the square root of d. As d grows, one bar eats the rest. The bottom row is the same dots divided by that square root, which is what attention actually does, so the weights stay spread out.",
      questions: [
        q("Why do the top bars collapse when d grows?", "the dot products get larger and softmax turns that into a spike"),
        q("Why divide by the square root and not by d?", "the dot product grows like the square root, so that is the factor that flattens it"),
        q("What stays the same in the bottom row?", "those bars are the unscaled dots, so d does not move them"),
      ],
      controls: [knob("d", "dimension d", 4, 256, 64, 4)],
      draw: ATTN,
    },
  },
  {
    claim: "Standard deviation is the width of a cloud. Dividing by sigma puts every cloud on the same scale.",
    widget: {
      id: "sigma-width",
      topic: "stddev",
      title: "Sigma is the width",
      explain: "The red cloud is the raw numbers. Drag sigma and it spreads around the mean. Drag the mean and the whole cloud slides. The green cloud is those same points after subtracting the mean and dividing by sigma, so it does not move.",
      questions: [
        q("What does sigma change in the red cloud?", "it is the width around the mean, so the points spread out or bunch up"),
        q("Why does the green cloud stay still?", "dividing by sigma removes the width, and subtracting the mean removes the shift"),
        q("What happens when sigma gets small?", "the same gaps count as more widths, which is why models guard a tiny sigma"),
      ],
      controls: [
        knob("sigma", "sigma", 0.4, 3.2, 1, 0.1),
        knob("mu", "mean", -3, 3, 0.8, 0.1),
      ],
      draw: STD,
    },
  },
];
