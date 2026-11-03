// Gallery figures outside the four gold draws. Provenance stays out of the widget.
// Illustrative layout, paper's rule. The last three fill bank topics the probe had no draw for.
function q(question, why) {
  return { q: question, why };
}

function knob(id, label, min, max, value, step) {
  return { id, label, min, max, value, step };
}

export const GUEST = [
  {
    claim: "RoPE rotates each token by its absolute position, but the attention score depends only on the relative gap, so shifting both tokens leaves q·k unchanged.",
    widget: {
      id: "rope-relative",
      topic: "rope",
      title: "Shift both tokens: the attention score does not move",
      explain: "Each circle is one rotation frequency. q (red) is rotated by its position m, k (blue) by n. Drag shift: both arrows turn together and q·k stays fixed. Drag m or n: the gap m−n changes and so does the score. Absolute rotations, relative score.",
      questions: [
        q("If RoPE rotates by the absolute position, why is it called relative?", "both tokens pick up the same extra angle, and that shared turn cancels in the dot product"),
        q("What happens to the score when the whole sentence moves right?", "the gap m minus n stays the same, so q·k stays on the flat line"),
        q("Why use several rotation speeds instead of one?", "each pair of dimensions spins at its own speed, and the score adds those pairs"),
      ],
      controls: [
        knob("m", "query position m", 0, 20, 3, 1),
        knob("n", "key position n", 0, 20, 7, 1),
        knob("shift", "shift both", 0, 40, 0, 1),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, m = state.m + state.shift, n = state.n + state.shift;\n  var th = [1, 0.32, 0.1], qa = [0.3, 1.1, 2.0], ka = [1.4, 0.2, 2.6], i, s = 0, r = Math.min(h * 0.26, w / 9);\n  function fx(v) { return \"\" + Math.round(v * 1000) / 1000; }\n  function arrow(cx, cy, a, col) {\n    ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(cx, cy);\n    ctx.lineTo(cx + r * Math.cos(a), cy - r * Math.sin(a)); ctx.stroke();\n    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(cx + r * Math.cos(a), cy - r * Math.sin(a), 4, 0, 2 * Math.PI); ctx.fill();\n  }\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  ctx.font = \"12px sans-serif\";\n  for (i = 0; i < 3; i++) {\n    var cx = w * (0.17 + 0.25 * i), cy = h * 0.36, aq = qa[i] + m * th[i], ak = ka[i] + n * th[i];\n    ctx.strokeStyle = \"#ccc\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(cx, cy, r, 0, 2 * Math.PI); ctx.stroke();\n    arrow(cx, cy, aq, \"#c0392b\"); arrow(cx, cy, ak, \"#1f4b99\");\n    s += Math.cos(aq - ak);\n    ctx.fillStyle = \"#444\"; ctx.fillText(\"speed \" + th[i], cx - 24, cy + r + 16);\n  }\n  ctx.fillStyle = \"#222\"; ctx.font = \"15px sans-serif\";\n  ctx.fillText(\"q·k = \" + fx(s), w * 0.80, h * 0.2); ctx.font = \"12px sans-serif\"; ctx.fillText(\"m−n = \" + (state.m - state.n), w * 0.80, h * 0.2 + 18); ctx.fillText(\"shift = \" + state.shift, w * 0.80, h * 0.2 + 34);\n  var gx = 40, gy = h * 0.72, gw = w - 60, gh = h * 0.2, k, v;\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#555\"; ctx.fillText(\"q·k as shift goes 0→40 (same m−n)\", gx, gy - 6);\n  ctx.strokeStyle = \"#bbb\"; ctx.lineWidth = 1; ctx.strokeRect(gx, gy, gw, gh);\n  ctx.strokeStyle = \"#2c3e50\"; ctx.lineWidth = 2; ctx.beginPath();\n  for (k = 0; k <= 40; k++) {\n    v = 0; for (i = 0; i < 3; i++) v += Math.cos(qa[i] - ka[i] + (state.m - state.n) * th[i]);\n    if (k === 0) ctx.moveTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6)); else ctx.lineTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));\n  }\n  ctx.stroke();\n  ctx.fillStyle = \"#c0392b\"; ctx.beginPath(); ctx.arc(gx + gw * state.shift / 40, gy + gh * (1 - (s + 3) / 6), 5, 0, 2 * Math.PI); ctx.fill();\n}",
    },
  },
  {
    claim: "Online softmax keeps a running max and a running sum, and after the last block it matches the full softmax exactly.",
    widget: {
      id: "online-softmax",
      topic: "online_softmax",
      title: "Softmax one block at a time, and still exact",
      explain: "Scores arrive in 4 blocks. After each block we keep only a running max m and a running sum ℓ; when m grows, the old sum is rescaled by e^(m_old − m_new). Slide to 4 blocks: the result lands exactly on the full softmax outline. No need to hold all scores at once.",
      questions: [
        q("How can softmax start before all the scores are known?", "a running max and a running sum are enough to rescale what was already seen"),
        q("Why multiply the old sum by e to the m old minus m new?", "raising the max shrinks every earlier exponential by that same factor"),
        q("Is the block-by-block answer approximate?", "when every block is in, the green bars sit on the outline and the gap is zero"),
      ],
      controls: [
        knob("blocks", "blocks seen", 1, 4, 2, 1),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, B = state.blocks, n = 16, seed = 4242, s = [], i, b;\n  function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }\n  function fx(v) { return \"\" + Math.round(v * 1000) / 1000; }\n  for (i = 0; i < n; i++) s[i] = rnd() * 6 - 2 + (i === 13 ? 3 : 0);\n  var M = -1e9, Z = 0; for (i = 0; i < n; i++) M = Math.max(M, s[i]); for (i = 0; i < n; i++) Z += Math.exp(s[i] - M);\n  var m = -1e9, l = 0, mo, rows = [];\n  for (b = 0; b < B; b++) {\n    mo = m; for (i = 4 * b; i < 4 * b + 4; i++) m = Math.max(m, s[i]);\n    var add = 0; for (i = 4 * b; i < 4 * b + 4; i++) add += Math.exp(s[i] - m);\n    var fac = b === 0 ? 1 : Math.exp(mo - m); l = l * fac + add;\n    rows[b] = \"block \" + (b + 1) + \":  m = \" + fx(m) + \"   rescale old ℓ × \" + fx(fac) + \"   ℓ = \" + fx(l);\n  }\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  var bw = (w - 40) / n, top = 14, sh = h * 0.22, py = h * 0.62, ph = h * 0.32, dmax = 0;\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#555\"; ctx.fillText(\"scores\", 20, top - 3);\n  for (i = 0; i < n; i++) {\n    var seen = i < 4 * B, x = 20 + i * bw;\n    ctx.fillStyle = Math.floor(i / 4) % 2 ? \"#e8e3d8\" : \"#efebe2\"; ctx.fillRect(x, top, bw, sh);\n    ctx.globalAlpha = seen ? 1 : 0.25; ctx.fillStyle = \"#1f4b99\";\n    ctx.fillRect(x + 2, top + sh * (1 - (s[i] + 2) / 9), bw - 4, sh * (s[i] + 2) / 9); ctx.globalAlpha = 1;\n    var full = Math.exp(s[i] - M) / Z, part = seen ? Math.exp(s[i] - m) / l : 0;\n    ctx.strokeStyle = \"#999\"; ctx.lineWidth = 1; ctx.strokeRect(x + 2, py + ph * (1 - full / 0.6), bw - 4, ph * full / 0.6);\n    ctx.fillStyle = \"#2e7d32\"; ctx.fillRect(x + 4, py + ph * (1 - part / 0.6), bw - 8, ph * part / 0.6);\n    if (B === 4) dmax = Math.max(dmax, Math.abs(full - part));\n  }\n  ctx.fillStyle = \"#333\"; ctx.font = \"12px sans-serif\";\n  for (b = 0; b < B; b++) ctx.fillText(rows[b], 20, top + sh + 18 + b * 15);\n  ctx.fillStyle = \"#555\"; ctx.font = \"11px sans-serif\";\n  ctx.fillText(\"green: running softmax of seen scores   outline: full softmax\", 20, py - 4);\n  if (B === 4) { ctx.fillStyle = \"#2e7d32\"; ctx.fillText(\"max |running − full| = \" + dmax, 20, h - 3); }\n}",
    },
  },
  {
    claim: "Byte-pair encoding repeatedly merges the most frequent pair, so an unseen word is still spelled with pieces learned from the other words.",
    widget: {
      id: "bpe-merges",
      topic: "bpe_merge",
      title: "Byte-pair encoding on the paper's own four words",
      explain: "The paper's toy vocabulary: low ×5, lower ×2, newest ×6, widest ×3. Each merge glues the most frequent adjacent pair everywhere. Slide the number of merges: frequent pieces fuse into tokens, and the unseen word 'lowest' is still spelled with learned pieces.",
      questions: [
        q("Why merge the most frequent pair instead of keeping whole words?", "the pair that shows up most becomes one token, and the next counts are taken on those pieces"),
        q("How does a word never seen in training still get tokens?", "lowest was not in the vocabulary, but low and est were learned from the other four words"),
        q("What does the end-of-word marker do?", "it is a piece of the word, so a merge can glue it on and keep the boundary"),
      ],
      controls: [
        knob("merges", "merges", 0, 10, 4, 1),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, K = state.merges, i, j, k, q;\n  var V = [[\"l\",\"o\",\"w\",\"</w>\"], [\"l\",\"o\",\"w\",\"e\",\"r\",\"</w>\"], [\"n\",\"e\",\"w\",\"e\",\"s\",\"t\",\"</w>\"], [\"w\",\"i\",\"d\",\"e\",\"s\",\"t\",\"</w>\"]];\n  var cnt = [5, 2, 6, 3], ML = [], MA = [], MB = [];\n  function merge(x, a, b) { var o = [], n = 0, p = 0; while (p < x.length) { if (p < x.length - 1 && x[p] === a && x[p + 1] === b) { o[n] = a + b; p += 2; } else { o[n] = x[p]; p += 1; } n++; } return o; }\n  for (k = 0; k < K; k++) {\n    var keys = [], ka = [], kb = [], val = [], nk = 0, bi = 0;\n    for (i = 0; i < V.length; i++) for (j = 0; j < V[i].length - 1; j++) {\n      var key = V[i][j] + \" \" + V[i][j + 1], f = -1;\n      for (q = 0; q < nk; q++) if (keys[q] === key) f = q;\n      if (f < 0) { keys[nk] = key; ka[nk] = V[i][j]; kb[nk] = V[i][j + 1]; val[nk] = 0; f = nk; nk++; }\n      val[f] += cnt[i];\n    }\n    for (q = 1; q < nk; q++) if (val[q] > val[bi]) bi = q;\n    MA[k] = ka[bi]; MB[k] = kb[bi]; ML[k] = (k + 1) + \". \" + ka[bi] + \" + \" + kb[bi] + \"  (\" + val[bi] + \")\";\n    for (i = 0; i < V.length; i++) V[i] = merge(V[i], ka[bi], kb[bi]);\n  }\n  var oov = [\"l\",\"o\",\"w\",\"e\",\"s\",\"t\",\"</w>\"]; for (k = 0; k < K; k++) oov = merge(oov, MA[k], MB[k]);\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  function row(x, y, toks, label, hl) {\n    var cx = x; ctx.font = \"13px monospace\";\n    for (j = 0; j < toks.length; j++) {\n      var tw = 9 * toks[j].length + 10, isNew = K > 0 && toks[j] === MA[K - 1] + MB[K - 1];\n      ctx.fillStyle = isNew ? \"#f9d67a\" : (toks[j].length > 1 ? \"#cfe0f5\" : \"#fff\"); ctx.fillRect(cx, y, tw, 22);\n      ctx.strokeStyle = \"#888\"; ctx.lineWidth = 1; ctx.strokeRect(cx, y, tw, 22);\n      ctx.fillStyle = \"#222\"; ctx.fillText(toks[j], cx + 5, y + 15); cx += tw + 3;\n    }\n    ctx.font = \"11px sans-serif\"; ctx.fillStyle = hl; ctx.fillText(label, cx + 6, y + 15);\n  }\n  for (i = 0; i < V.length; i++) row(14, 12 + i * 30, V[i], \"×\" + cnt[i], \"#555\");\n  row(14, 12 + 4 * 30 + 16, oov, \"unseen word 'lowest'\", \"#c0392b\");\n  ctx.font = \"12px monospace\"; ctx.fillStyle = \"#333\";\n  var mx = w * 0.62; ctx.fillText(\"merges learned:\", mx, 18);\n  for (k = 0; k < K; k++) { ctx.fillStyle = k === K - 1 ? \"#b9770e\" : \"#333\"; ctx.fillText(ML[k], mx, 36 + k * 16); }\n}",
    },
  },
  {
    claim: "Speculative decoding has expected speedup (1 - alpha^(gamma+1)) / ((1 - alpha) * (gamma * c + 1)). There is a best draft length gamma.",
    widget: {
      id: "spec-cost",
      topic: "spec_cost",
      title: "Speculative decoding: the best draft length",
      explain: "Each extra draft token is kept only while the draft keeps matching (chance α), but each costs c of a target call. The curve is the paper's expected speedup for γ = 1…12; the dot is the best γ. Low α or expensive drafts push the curve under 1×: slower than plain decoding.",
      questions: [
        q("Why not let the draft model guess 50 tokens at once?", "each extra guess is kept only while the draft keeps matching, and a long run almost never is"),
        q("What is c, and why does it matter so much?", "c is the cost of one draft token against one target call, so a pricey draft pulls the curve under the 1x line"),
        q("Can speculative decoding make generation slower?", "when acceptance is low or the draft is expensive, the best length is 1 and the speedup drops below 1"),
      ],
      controls: [
        knob("alpha", "acceptance α", 0.3, 0.95, 0.8, 0.01),
        knob("c", "draft cost c", 0.01, 1, 0.1, 0.01),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, a = state.alpha, c = state.c, g, f = [], best = 1, top = 0;\n  function fx(v) { return \"\" + Math.round(v * 100) / 100; }\n  for (g = 1; g <= 12; g++) { f[g] = (1 - Math.pow(a, g + 1)) / ((1 - a) * (g * c + 1)); if (f[g] > f[best]) best = g; top = Math.max(top, f[g]); }\n  top = Math.max(top, 1.2) * 1.1;\n  var x0 = 50, y0 = h - 30, gw = w - 80, gh = h - 60;\n  function X(g) { return x0 + (g - 1) / 11 * gw; }\n  function Y(v) { return y0 - v / top * gh; }\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  ctx.strokeStyle = \"#bbb\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + gw, y0); ctx.moveTo(x0, y0); ctx.lineTo(x0, y0 - gh); ctx.stroke();\n  ctx.strokeStyle = \"#c0392b\"; ctx.beginPath(); ctx.moveTo(x0, Y(1)); ctx.lineTo(x0 + gw, Y(1)); ctx.stroke();\n  ctx.fillStyle = \"#c0392b\"; ctx.font = \"11px sans-serif\"; ctx.fillText(\"1× (no gain)\", x0 + gw - 70, Y(1) - 4);\n  ctx.strokeStyle = \"#1f4b99\"; ctx.lineWidth = 2.5; ctx.beginPath();\n  for (g = 1; g <= 12; g++) { if (g === 1) ctx.moveTo(X(g), Y(f[g])); else ctx.lineTo(X(g), Y(f[g])); }\n  ctx.stroke();\n  ctx.fillStyle = \"#1f4b99\"; for (g = 1; g <= 12; g++) { ctx.beginPath(); ctx.arc(X(g), Y(f[g]), 3, 0, 2 * Math.PI); ctx.fill(); }\n  ctx.fillStyle = \"#2e7d32\"; ctx.beginPath(); ctx.arc(X(best), Y(f[best]), 7, 0, 2 * Math.PI); ctx.fill();\n  ctx.fillStyle = \"#555\"; for (g = 1; g <= 12; g++) ctx.fillText(\"\" + g, X(g) - 3, y0 + 14);\n  ctx.fillText(\"draft length γ\", x0 + gw / 2 - 30, h - 2);\n  ctx.fillStyle = \"#222\"; ctx.font = \"14px sans-serif\";\n  ctx.fillText(\"best γ = \" + best + \"   speedup ≈ \" + fx(f[best]) + \"×   tokens per target call ≈ \" + fx((1 - Math.pow(a, best + 1)) / (1 - a)), x0 + 6, 20);\n}",
    },
  },
  {
    claim: "YaRN NTK-by-parts leaves high-frequency RoPE dimensions untouched and interpolates only the dimensions whose wavelength is longer than the context.",
    widget: {
      id: "yarn-parts",
      topic: "yarn_parts",
      title: "YaRN stretches only the slow RoPE dimensions",
      explain: "NTK-by-parts: one bar per RoPE frequency, height = its wavelength. Fast dimensions (short bars) already cycle many times inside the training context and are left alone; slow ones (taller than the context line) are divided by s; the band in between is blended. Raise the scale s or the context L and watch the colors move.",
      questions: [
        q("Why not divide every position by the same factor?", "the fast dimensions already fit the training context, and stretching them throws away position"),
        q("What does a wavelength longer than the context mean?", "that dimension has not finished one turn inside the training length, so it is the one to interpolate"),
        q("Which dimensions would break at a longer context?", "the tall bars, the slow ones, which the orange band divides by the scale"),
      ],
      controls: [
        knob("s", "scale s", 1, 32, 8, 1),
        knob("logl", "log2 train context", 9, 14, 12, 1),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, s = state.s, L = Math.pow(2, state.logl), D = 128, b = 10000, al = 1, be = 32, d;\n  var n = D / 2, bw = (w - 70) / n, y0 = h * 0.62, gh = h * 0.55, lo = 0, hi = Math.log(2 * Math.PI * Math.pow(b, 1)) + 0.5;\n  function Y(lam) { return y0 - (Math.log(lam) - lo) / (hi - lo) * gh; }\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  var cnt0 = 0, cnt1 = 0;\n  for (d = 0; d < n; d++) {\n    var lam = 2 * Math.PI * Math.pow(b, 2 * d / D), r = L / lam, g = r < al ? 0 : (r > be ? 1 : (r - al) / (be - al));\n    if (g === 0) cnt0++; if (g === 1) cnt1++;\n    ctx.fillStyle = g === 1 ? \"#1f4b99\" : (g === 0 ? \"#e67e22\" : \"#8e44ad\");\n    ctx.globalAlpha = g === 0 || g === 1 ? 1 : 0.45 + 0.5 * g;\n    ctx.fillRect(50 + d * bw, Y(lam), bw - 1, y0 - Y(lam));\n    var ratio = (1 - g) / s + g;\n    ctx.globalAlpha = 1; ctx.fillStyle = \"#333\";\n    ctx.fillRect(50 + d * bw, h - 12 - ratio * (h * 0.22), bw - 1, 2);\n  }\n  ctx.strokeStyle = \"#c0392b\"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(45, Y(L)); ctx.lineTo(w - 15, Y(L)); ctx.stroke();\n  ctx.strokeStyle = \"#999\"; ctx.beginPath(); ctx.moveTo(45, Y(L / be)); ctx.lineTo(w - 15, Y(L / be)); ctx.stroke();\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#c0392b\"; ctx.fillText(\"λ = L = \" + L, w - 95, Y(L) - 4);\n  ctx.fillStyle = \"#777\"; ctx.fillText(\"λ = L/32\", w - 70, Y(L / be) + 12);\n  ctx.fillStyle = \"#444\"; ctx.fillText(\"wavelength λ (log)\", 4, 12); ctx.fillText(\"θ_new / θ  (1 = untouched, 1/s = interpolated)\", 50, y0 + 18);\n  \n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#1f4b99\"; ctx.fillText(\"untouched \" + cnt1, 60, 28);\n  ctx.fillStyle = \"#8e44ad\"; ctx.fillText(\"blended \" + (n - cnt0 - cnt1), 160, 28);\n  ctx.fillStyle = \"#e67e22\"; ctx.fillText(\"interpolated ÷\" + s + \": \" + cnt0, 250, 28);\n}",
    },
  },
  {
    claim: "In a selective state space model, a large delta resets the hidden state to the current input, while a small delta keeps the old state.",
    widget: {
      id: "mamba-delta",
      topic: "ssm_delta",
      title: "Mamba's Δ: remember, or reset to the new input",
      explain: "The grey bars are inputs; orange ones are the tokens worth keeping. The blue line is the state h. Each step h ← e^(ΔA)·h + (1 − e^(ΔA))·x. A large Δ on orange tokens lets them overwrite h; a small Δ on the rest lets the noise slip past, so h holds on to the last orange value. Make the two Δ equal and the selection disappears.",
      questions: [
        q("What does delta do to the hidden state?", "a large delta overwrites the state with the current input, and a small delta keeps what was already there"),
        q("How can one parameter both remember and forget?", "the same update mixes the old state and the new input, and delta picks the mix"),
        q("Why does delta have to depend on the input?", "the tokens worth keeping get a large delta and the noise gets a small one, which is the selection"),
      ],
      controls: [
        knob("dkeep", "Δ on orange tokens", 0.01, 5, 3, 0.01),
        knob("dnoise", "Δ on other tokens", 0.01, 5, 0.03, 0.01),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, n = 48, A = -1, i, seed = 31, x = [], keep = [], hs = [], hh = 0;\n  function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }\n  for (i = 0; i < n; i++) { keep[i] = i === 6 || i === 20 || i === 34; x[i] = keep[i] ? (i === 20 ? -0.8 : (i === 6 ? 0.9 : 0.4)) : (rnd() - 0.5) * 1.6; }\n  for (i = 0; i < n; i++) { var d = keep[i] ? state.dkeep : state.dnoise, g = Math.exp(d * A); hh = g * hh + (1 - g) * x[i]; hs[i] = hh; }\n  var x0 = 30, gw = w - 50, bw = gw / n, mid = h * 0.5, sc = h * 0.38;\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  ctx.strokeStyle = \"#ccc\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x0, mid); ctx.lineTo(x0 + gw, mid); ctx.stroke();\n  for (i = 0; i < n; i++) {\n    ctx.fillStyle = keep[i] ? \"#e67e22\" : \"#c9c4ba\";\n    var v = x[i] * sc; ctx.fillRect(x0 + i * bw + 2, v > 0 ? mid - v : mid, bw - 4, Math.abs(v));\n  }\n  ctx.strokeStyle = \"#1f4b99\"; ctx.lineWidth = 3; ctx.beginPath();\n  for (i = 0; i < n; i++) { var px = x0 + i * bw + bw / 2, py = mid - hs[i] * sc; if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py); }\n  ctx.stroke();\n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#1f4b99\"; ctx.fillText(\"state h\", x0, 16);\n  ctx.fillStyle = \"#e67e22\"; ctx.fillText(\"tokens to keep\", x0 + 70, 16);\n  ctx.fillStyle = \"#777\"; ctx.fillText(\"noise\", x0 + 175, 16);\n  ctx.fillStyle = \"#333\"; ctx.fillText(\"time →\", w - 60, h - 6);\n}",
    },
  },
  {
    claim: "SmoothQuant migrates activation outliers into the weights with a scale alpha, and the quantization error is a valley in alpha.",
    widget: {
      id: "smoothquant-seesaw",
      topic: "smoothquant",
      title: "SmoothQuant: hand the outliers from activations to weights",
      explain: "Two activation channels carry huge outliers, so 8-bit rounding of X wipes out the small channels. Dividing channel j of X by s_j and multiplying row j of W by s_j leaves X·W exactly the same. α decides how much of the spike moves: at 0 X keeps it, at 1 W takes it, near 0.5 both are easy to quantize.",
      questions: [
        q("Why are activations harder to quantize than weights?", "a few activation channels are huge, so 8-bit rounding wipes out the small ones"),
        q("Does rescaling change the layer output?", "dividing a channel of X and multiplying the matching row of W leaves the product the same"),
        q("Why is alpha 0.5 a good default?", "the error valley sits near the middle, where neither side keeps the whole spike"),
      ],
      controls: [
        knob("alpha", "migration α", 0, 1, 0.5, 0.05),
      ],
      draw: "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, a = state.alpha, n = 8, j, k;\n  var xm = [1.2, 0.8, 40, 1.0, 0.6, 25, 1.4, 0.9], wm = [0.5, 0.7, 0.4, 0.6, 0.8, 0.5, 0.3, 0.6];\n  function fx(v) { return \"\" + Math.round(v * 1000) / 1000; }\n  function q(v, m) { var st = m / 127; return Math.abs(v - Math.round(v / st) * st) / v; }\n  function run(al, sx, sw) {\n    var mx = 0, mw = 0, ex = 0, ew = 0;\n    for (j = 0; j < n; j++) { var s = Math.pow(xm[j], al) / Math.pow(wm[j], 1 - al); sx[j] = xm[j] / s; sw[j] = wm[j] * s; mx = Math.max(mx, sx[j]); mw = Math.max(mw, sw[j]); }\n    for (j = 0; j < n; j++) { ex = Math.max(ex, q(sx[j] * 0.37, mx)); ew = Math.max(ew, q(sw[j] * 0.37, mw)); }\n    return [ex, ew, mx, mw];\n  }\n  var SX = [], SW = [], r = run(a, SX, SW), prod = 0, prod0 = 0;\n  for (j = 0; j < n; j++) { prod += SX[j] * SW[j]; prod0 += xm[j] * wm[j]; }\n  ctx.fillStyle = \"#f7f5f0\"; ctx.fillRect(0, 0, w, h);\n  function panel(x0, vals, m, col, label, e) {\n    var pw = w * 0.28, ph = h * 0.42, y0 = 34 + ph, bw = pw / n;\n    ctx.fillStyle = \"#333\"; ctx.font = \"13px sans-serif\"; ctx.fillText(label, x0, 20);\n    for (j = 0; j < n; j++) { ctx.fillStyle = col; ctx.fillRect(x0 + j * bw + 2, y0 - ph * vals[j] / m, bw - 4, ph * vals[j] / m); }\n    ctx.fillStyle = e > 0.05 ? \"#c0392b\" : \"#2e7d32\"; ctx.font = \"12px sans-serif\";\n    ctx.fillText(\"worst 8-bit error: \" + Math.round(e * 1000) / 10 + \"%\", x0, y0 + 18);\n  }\n  panel(16, SX, r[2], \"#1f4b99\", \"activations X / s\", r[0]);\n  panel(w * 0.34, SW, r[3], \"#8e44ad\", \"weights s · W\", r[1]);\n  var gx = w * 0.68, gy = 30, gw = w * 0.29, gh = h * 0.42, e, top = 0.2;\n  ctx.fillStyle = \"#333\"; ctx.font = \"13px sans-serif\"; ctx.fillText(\"error vs α\", gx, 20);\n  ctx.strokeStyle = \"#bbb\"; ctx.lineWidth = 1; ctx.strokeRect(gx, gy, gw, gh);\n  for (var c = 0; c < 3; c++) {\n    ctx.strokeStyle = c === 0 ? \"#1f4b99\" : (c === 1 ? \"#8e44ad\" : \"#222\"); ctx.lineWidth = c === 2 ? 2.5 : 1.5; ctx.beginPath();\n    for (k = 0; k <= 40; k++) { e = run(k / 40, [], []); var v = c === 2 ? Math.max(e[0], e[1]) : e[c];\n      var py = gy + gh * (1 - Math.min(v, top) / top); if (k === 0) ctx.moveTo(gx + gw * k / 40, py); else ctx.lineTo(gx + gw * k / 40, py); }\n    ctx.stroke();\n  }\n  ctx.fillStyle = \"#c0392b\"; ctx.beginPath(); ctx.arc(gx + gw * a, gy + gh * (1 - Math.min(Math.max(r[0], r[1]), top) / top), 5, 0, 2 * Math.PI); ctx.fill();\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#555\"; ctx.fillText(\"0\", gx, gy + gh + 12); ctx.fillText(\"1\", gx + gw - 6, gy + gh + 12);\n  ctx.fillText(\"black = worse of the two\", gx, gy + gh + 26);\n  ctx.fillStyle = \"#333\"; ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"Σ_j X_j·W_j before = \" + fx(prod0) + \"   after = \" + fx(prod) + \"   (the layer output does not change)\", 16, h - 10);\n}",
    },
  },
  {
    claim: "Adam steps by the bias-corrected first moment divided by the square root of the second moment. On a narrow valley, SGD zigzags and Adam does not.",
    widget: {
      "id": "adam-valley",
      "topic": "adam",
      "title": "En el valle, el segundo momento frena el rebote",
      "explain": "Adam guarda dos momentos: hacia dónde empuja el gradiente y qué tan brusco es cada eje. En un valle angosto el segundo momento crece en la pared y achica ese paso. SGD, con el mismo lr, zigzaguea; si subes lr, se sale.",
      "questions": [
        {
          "q": "¿Por qué SGD rebota en un valle angosto y Adam no?",
          "why": "el segundo momento achica el eje empinado"
        },
        {
          "q": "¿Qué se está promediando: la dirección o el tamaño del paso?",
          "why": "los dos momentos, uno para cada cosa"
        },
        {
          "q": "¿Qué pasa si subo el lr y el valle sigue igual de angosto?",
          "why": "SGD se sale y Adam aguanta más"
        }
      ],
      "controls": [
        {
          "id": "lr",
          "label": "paso lr",
          "min": 0.01,
          "max": 0.1,
          "value": 0.04,
          "step": 0.005
        },
        {
          "id": "beta2",
          "label": "beta2",
          "min": 0.8,
          "max": 0.999,
          "value": 0.99,
          "step": 0.001
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, lr = state.lr, b2 = state.beta2, b1 = 0.9, eps = 1e-8;\n  var x0 = 28, y0 = 14, pw = w * 0.68, ph = h - 28;\n  function X(x) { return x0 + (x + 1.5) / 3 * pw; }\n  function Y(y) { return y0 + (1.15 - y) / 2.3 * ph; }\n  var levels = [0.5, 1.5, 3, 6, 9], li, a, c, ct, st;\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.strokeStyle = \"#e4d6c4\";\n  ctx.lineWidth = 1;\n  for (li = 0; li < levels.length; li++) {\n    c = levels[li];\n    ctx.beginPath();\n    for (a = 0; a <= 48; a++) {\n      ct = Math.cos(a / 48 * 6.2832);\n      st = Math.sin(a / 48 * 6.2832);\n      var px = Math.sqrt(2 * c) * ct, py = Math.sqrt(c / 20) * st;\n      if (a === 0) ctx.moveTo(X(px), Y(py)); else ctx.lineTo(X(px), Y(py));\n    }\n    ctx.stroke();\n  }\n  function path(kind) {\n    var x = -1.15, y = 0.55, mx = 0, my = 0, vx = 0, vy = 0, step, gx, gy, out = 0;\n    ctx.beginPath();\n    ctx.moveTo(X(x), Y(y));\n    for (step = 1; step <= 26; step++) {\n      gx = x; gy = 40 * y;\n      if (kind === 0) { x -= lr * gx; y -= lr * gy; }\n      else {\n        mx = b1 * mx + (1 - b1) * gx; my = b1 * my + (1 - b1) * gy;\n        vx = b2 * vx + (1 - b2) * gx * gx; vy = b2 * vy + (1 - b2) * gy * gy;\n        var mhx = mx / (1 - Math.pow(b1, step)), mhy = my / (1 - Math.pow(b1, step));\n        var vhx = vx / (1 - Math.pow(b2, step)), vhy = vy / (1 - Math.pow(b2, step));\n        x -= lr * mhx / (Math.sqrt(vhx) + eps);\n        y -= lr * mhy / (Math.sqrt(vhy) + eps);\n      }\n      if (x > 1.45 || x < -1.45 || y > 1.1 || y < -1.1) { out = 1; break; }\n      ctx.lineTo(X(x), Y(y));\n    }\n    ctx.stroke();\n    return out;\n  }\n  ctx.strokeStyle = \"#c4512c\";\n  ctx.lineWidth = 2;\n  var sgdOut = path(0);\n  ctx.strokeStyle = \"#1f4b99\";\n  ctx.lineWidth = 2;\n  path(1);\n  ctx.fillStyle = \"#c4512c\";\n  ctx.fillRect(x0 + pw + 8, 28, 10, 10);\n  ctx.fillStyle = \"#1f4b99\";\n  ctx.fillRect(x0 + pw + 8, 48, 10, 10);\n  ctx.font = \"11px sans-serif\";\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.fillText(\"SGD\", x0 + pw + 22, 37);\n  ctx.fillText(\"Adam\", x0 + pw + 22, 57);\n  if (sgdOut) {\n    ctx.fillStyle = \"#c4512c\";\n    ctx.fillText(\"SGD se sale\", x0 + pw + 8, 80);\n  }\n}"
    },
  },
  {
    claim: "Batch normalization recenters each activation by the batch mean and rescales it by the batch standard deviation, then applies gamma and beta.",
    widget: {
      "id": "bn-stable",
      "topic": "batchnorm",
      "title": "La escala de la entrada no cruza el lote",
      "explain": "BatchNorm resta la media del lote y divide entre su desviación. Mueve la escala o el corrimiento de la entrada: la fila de arriba cambia y la del medio no. Gamma y beta, aprendidos, vuelven a estirar y a mover la salida.",
      "questions": [
        {
          "q": "¿Por qué la fila de en medio no se entera de la escala?",
          "why": "restar la media y dividir cancela ese cambio"
        },
        {
          "q": "¿Para qué están gamma y beta si ya normalicé?",
          "why": "la red todavía puede pedir otra escala"
        },
        {
          "q": "¿Qué se mueve cuando corro la entrada y qué se queda?",
          "why": "solo la fila cruda; las otras usan el lote normalizado"
        }
      ],
      "controls": [
        {
          "id": "scale",
          "label": "escala",
          "min": 0.4,
          "max": 3,
          "value": 2.2,
          "step": 0.1
        },
        {
          "id": "shift",
          "label": "corrimiento",
          "min": -1.5,
          "max": 1.5,
          "value": 0.8,
          "step": 0.1
        },
        {
          "id": "gamma",
          "label": "gamma",
          "min": 0.3,
          "max": 2.2,
          "value": 1.8,
          "step": 0.1
        },
        {
          "id": "bias",
          "label": "beta",
          "min": -1,
          "max": 1,
          "value": 0.35,
          "step": 0.05
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, z = [-1.5, -0.8, -0.2, 0.35, 0.9, 1.45];\n  var n = 6, i, mean = 0, v = 0, raw = [], hat = [], out = [];\n  for (i = 0; i < n; i++) { raw[i] = state.shift + state.scale * z[i]; mean += raw[i]; }\n  mean /= n;\n  for (i = 0; i < n; i++) v += (raw[i] - mean) * (raw[i] - mean);\n  v = Math.sqrt(v / n) + 1e-6;\n  for (i = 0; i < n; i++) { hat[i] = (raw[i] - mean) / v; out[i] = state.gamma * hat[i] + state.bias; }\n  function row(vals, y, col, label) {\n    ctx.strokeStyle = \"#e4d6c4\";\n    ctx.beginPath();\n    ctx.moveTo(20, y);\n    ctx.lineTo(w - 16, y);\n    ctx.stroke();\n    ctx.fillStyle = col;\n    for (i = 0; i < n; i++) {\n      var x = w * 0.5 + vals[i] * 28;\n      if (x < 16) x = 16;\n      if (x > w - 16) x = w - 16;\n      ctx.beginPath();\n      ctx.arc(x, y, 5, 0, 6.2832);\n      ctx.fill();\n    }\n    ctx.fillStyle = \"#5c564c\";\n    ctx.font = \"11px sans-serif\";\n    ctx.fillText(label, 8, y - 10);\n  }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.lineWidth = 1;\n  row(raw, 48, \"#c4512c\", \"entrada\");\n  row(hat, 108, \"#1f4b99\", \"tras el lote\");\n  row(out, 168, \"#2e7d32\", \"gamma y beta\");\n}"
    },
  },
  {
    claim: "Knowledge distillation raises the softmax temperature so the teacher's small probabilities, the dark knowledge, become visible to the student.",
    widget: {
      "id": "distill-temp",
      "topic": "distill_temp",
      "title": "La temperatura del maestro saca las chicas",
      "explain": "Subir la temperatura del maestro saca las probabilidades chicas, las que el argmax esconde. El alumno aprende de ese orden, no solo de la clase ganadora.",
      "questions": [
        {
          "q": "¿Por qué entrenar con las probabilidades del maestro?",
          "why": "el orden entre las clases perdedoras también informa"
        },
        {
          "q": "¿Qué aparece cuando sube la temperatura?",
          "why": "las probabilidades chicas se vuelven legibles"
        },
        {
          "q": "¿Qué se aplasta si la temperatura vuelve a uno?",
          "why": "otra vez solo se ve la clase ganadora"
        }
      ],
      "controls": [
        {
          "id": "temp",
          "label": "temperatura",
          "min": 1,
          "max": 8,
          "value": 1,
          "step": 0.5
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, temp = state.temp;\n  if (temp < 0.05) temp = 0.05;\n  var logits = [2.2, 1.1, 0.4, -0.2];\n  var hard = [1, 0, 0, 0];\n  var i, m = logits[0], s = 0, p = [];\n  for (i = 1; i < 4; i++) if (logits[i] > m) m = logits[i];\n  for (i = 0; i < 4; i++) { p[i] = Math.exp((logits[i] - m) / temp); s += p[i]; }\n  for (i = 0; i < 4; i++) p[i] = p[i] / s;\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  function bars(vals, x0, label) {\n    var base = h * 0.74, bw = 36, gap = 14, maxH = h * 0.48, k, bh;\n    ctx.fillStyle = \"#5c564c\";\n    ctx.font = \"13px sans-serif\";\n    ctx.fillText(label, x0, 32);\n    for (k = 0; k < 4; k++) {\n      bh = vals[k] * maxH;\n      if (bh < 1) bh = 1;\n      ctx.fillStyle = k === 0 ? \"#1f4b99\" : \"#c4512c\";\n      ctx.fillRect(x0 + k * (bw + gap), base - bh, bw, bh);\n    }\n    ctx.strokeStyle = \"#e4d6c4\";\n    ctx.lineWidth = 1;\n    ctx.beginPath();\n    ctx.moveTo(x0, base);\n    ctx.lineTo(x0 + 4 * bw + 3 * gap, base);\n    ctx.stroke();\n  }\n  bars(hard, 28, \"lo que ve el argmax\");\n  bars(p, w * 0.52, \"lo que entrega el maestro\");\n  var hidden = Math.round((1 - p[0]) * 100);\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"14px sans-serif\";\n  ctx.fillText(\"temperatura \" + temp, w * 0.52, 54);\n  ctx.fillText(\"masa fuera del ganador \" + hidden + \"%\", 28, h - 18);\n}\n"
    },
  },
];
