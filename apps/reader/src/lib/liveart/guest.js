// Three figures from RRM-82, copied into the sandbox gallery.
// Provenance stays out of the widget. Illustrative layout, paper's rule.
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
];
