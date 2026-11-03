"""Widgets emulados, como saldrían de Muse Code. No van dentro del prompt.

Los cuatro de oro siguen en fewshots.py y son los únicos few-shots del prompt.
Estos pasan por el mismo verificador. RRM-80 puede reemplazar un draw; la forma no cambia.
"""

from rrm.liveart.offline import _by_name
from rrm.liveart.quality import rows as quality_rows
from rrm.liveart.wave2 import SPECS


def _claim(text, arxiv):
    return {"text": text, "latex": "", "context": "", "arxiv": arxiv}


def _knob(kid, label, lo, hi, value, step):
    return {"id": kid, "label": label, "min": lo, "max": hi, "value": value, "step": step}


def _draw(body):
    return (
        "function draw(ctx, state, t) {\n"
        "  var w = state.w, h = state.h;\n"
        "  ctx.clearRect(0, 0, w, h);\n"
        "  ctx.fillStyle = \"#f6f3ec\";\n"
        "  ctx.fillRect(0, 0, w, h);\n"
        + body
        + "}\n"
    )


def _widget(topic, wid, title, controls, draw):
    spec = _by_name(topic)
    return {
        "id": wid,
        "topic": topic,
        "title": title,
        "explain": spec["explain"],
        "questions": [{"q": q, "why": why} for q, why in spec["questions"]],
        "controls": controls,
        "draw": draw,
    }


def _row(wid, topic, title, claim, arxiv, controls, body):
    return {
        "id": wid,
        "claim": _claim(claim, arxiv),
        "widget": _widget(topic, wid, title, controls, _draw(body)),
    }


_ROPE_GAP = _draw(
    "  var gap = state.theta * 0.5;\n"
    "  var cx = w * 0.32, cy = h * 0.55, r = h * 0.22;\n"
    "  ctx.strokeStyle = \"#1f4b99\";\n"
    "  ctx.lineWidth = 2;\n"
    "  ctx.beginPath();\n"
    "  ctx.moveTo(cx, cy);\n"
    "  ctx.lineTo(cx + r, cy);\n"
    "  ctx.moveTo(cx + w * 0.28, cy);\n"
    "  ctx.lineTo(cx + w * 0.28 + Math.cos(gap) * r, cy - Math.sin(gap) * r);\n"
    "  ctx.stroke();\n"
)

CATALOG = quality_rows() + [
    {
        "id": "rope-gap",
        "claim": _claim("Rotary embeddings rotate pairs of coordinates so two tokens compare by their angle gap.", "2302.13971"),
        "widget": _widget("rope", "rope-gap", "La diferencia de giros separa dos tokens", [_knob("theta", "ángulo", 0.2, 4, 1, 0.1)], _ROPE_GAP),
    },
    _row(
        "dpo-beta", "dpo_beta", "Beta frena la distancia a la referencia",
        "Direct Preference Optimization weighs the KL penalty by beta.",
        "2305.18290",
        [_knob("beta", "beta", 0.05, 5, 0.5, 0.05)],
        "  var penalty = Math.min(h * 0.7, state.beta * h * 0.18);\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillRect(w * 0.25, h - 16 - h * 0.55, 28, h * 0.55);\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.fillRect(w * 0.55, h - 16 - penalty, 28, penalty);\n",
    ),
    _row(
        "yarn-scale", "yarn_scale", "Estirar la escala alarga el contexto",
        "YaRN scales the RoPE frequencies by a factor s so a longer context still fits.",
        "2309.00071",
        [_knob("scale", "escala", 1, 16, 4, 0.5)],
        "  var freq = 0.35 / state.scale;\n"
        "  var x, pos, y;\n"
        "  ctx.beginPath();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  for (x = 0; x < w; x++) {\n"
        "    pos = (x / (w - 1)) * 40;\n"
        "    y = h * 0.55 - Math.sin(pos * freq) * h * 0.3;\n"
        "    if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "draft-run", "speculative", "Un borrador parecido alarga la racha",
        "Speculative decoding accepts a run of draft tokens when the target model agrees.",
        "2211.17192",
        [_knob("agree", "acuerdo", 0, 1, 0.5, 0.05)],
        "  var n = 8, i, accept = Math.round(state.agree * n), bw = (w - 20) / n;\n"
        "  for (i = 0; i < n; i++) {\n"
        "    ctx.fillStyle = i < accept ? \"#1f4b99\" : \"#d9d3c7\";\n"
        "    ctx.fillRect(10 + i * bw, h * 0.4, bw - 4, i < accept ? 22 : 8);\n"
        "  }\n",
    ),
    _row(
        "draft-cost", "speculative", "Rechazar el borrador cuesta otro paso",
        "The acceptance probability of a draft token decides how many target steps you skip.",
        "2211.17192",
        [_knob("agree", "acuerdo", 0, 1, 0.5, 0.05)],
        "  var cost = 1 + 7 * (1 - state.agree);\n"
        "  var bh = cost * h * 0.08;\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.fillRect(w * 0.4, h - 16 - bh, 40, bh);\n",
    ),
    _row(
        "noise-beta", "noise_schedule", "Beta abre la nube de noise",
        "The forward process follows a noise schedule and adds Gaussian noise with variance beta_t.",
        "2107.00630",
        [_knob("beta", "beta", 0.1, 3, 1, 0.1)],
        "  var pts = [0.2, 0.8, -0.4, 0.1, -0.9, 0.5];\n"
        "  var i, x, y;\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  for (i = 0; i < pts.length; i++) {\n"
        "    x = (i + 1) * w / (pts.length + 1);\n"
        "    y = h * 0.5 - pts[i] * state.beta * 18;\n"
        "    ctx.beginPath();\n"
        "    ctx.arc(x, y, 4, 0, Math.PI * 2);\n"
        "    ctx.fill();\n"
        "  }\n",
    ),
    _row(
        "guide-push", "guidance", "La guidance empuja hacia el texto",
        "Classifier-free guidance scales the conditional score minus the unconditional score.",
        "2205.01138",
        [_knob("scale", "guía", 0, 5, 1.5, 0.1)],
        "  var x0 = w * 0.25, x1 = w * 0.75;\n"
        "  var x = x0 + state.scale * (x1 - x0) / 5;\n"
        "  ctx.fillStyle = \"#d9e3f5\";\n"
        "  ctx.fillRect(x0 - 8, h * 0.35, 16, h * 0.3);\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillRect(x1 - 8, h * 0.35, 16, h * 0.3);\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.beginPath();\n"
        "  ctx.arc(x, h * 0.5, 6, 0, Math.PI * 2);\n"
        "  ctx.fill();\n",
    ),
    _row(
        "guide-width", "guidance", "Más guidance, más peso del texto",
        "The guidance scale w pushes the sample away from the unconditional prediction.",
        "2205.01138",
        [_knob("scale", "guía", 0, 5, 1.5, 0.1)],
        "  var bw = 20 + state.scale * 18;\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillRect(w * 0.5 - bw / 2, h * 0.3, bw, h * 0.35);\n",
    ),
    _row(
        "detr-match", "detr_match", "El peso de la clase mueve el matching",
        "The Hungarian algorithm solves the bipartite matching between object queries and boxes.",
        "2005.12872",
        [_knob("class_w", "clase", 0, 1, 0.4, 0.05)],
        "  var y = h * 0.3 + (1 - state.class_w) * (h * 0.4);\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(w * 0.2, h * 0.5);\n"
        "  ctx.lineTo(w * 0.75, y);\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "skip-mix", "residual", "El residual mezcla entrada y salida",
        "A residual connection adds the block input to its output, an identity mapping.",
        "1512.03385",
        [_knob("skip", "atajo", 0, 1, 0.7, 0.05)],
        "  var mixed = state.skip * 0.75 + (1 - state.skip) * 0.15;\n"
        "  var bh = mixed * (h - 30);\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillRect(w * 0.4, h - 16 - bh, 36, bh);\n",
    ),
    _row(
        "nucleus-keep", "nucleus", "p decide cuántas palabras quedan",
        "Nucleus sampling (top-p) keeps the smallest set of tokens whose cumulative mass exceeds p.",
        "1904.09751",
        [_knob("p", "p", 0.05, 1, 0.6, 0.05)],
        "  var probs = [0.42, 0.22, 0.16, 0.12, 0.08];\n"
        "  var i, cum = 0, bw = (w - 24) / probs.length, show;\n"
        "  for (i = 0; i < probs.length; i++) {\n"
        "    show = cum < state.p;\n"
        "    cum += probs[i];\n"
        "    ctx.fillStyle = show ? \"#1f4b99\" : \"#d9d3c7\";\n"
        "    ctx.fillRect(12 + i * bw, h * 0.35, bw - 6, show ? h * 0.3 : 6);\n"
        "  }\n",
    ),
    _row(
        "nucleus-line", "nucleus", "Top-p corta la probability acumulada",
        "Top-p sampling truncates the tail once the cumulative probability passes p.",
        "1904.09751",
        [_knob("p", "p", 0.05, 1, 0.6, 0.05)],
        "  var probs = [0.42, 0.22, 0.16, 0.12, 0.08];\n"
        "  var i, cum = 0, x, y;\n"
        "  ctx.beginPath();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.moveTo(8, h - 16);\n"
        "  for (i = 0; i < probs.length; i++) {\n"
        "    cum += probs[i];\n"
        "    x = 8 + (i + 1) * (w - 16) / probs.length;\n"
        "    y = h - 16 - cum * (h - 30);\n"
        "    ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n"
        "  ctx.strokeStyle = \"#c4512c\";\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(8 + state.p * (w - 16), 10);\n"
        "  ctx.lineTo(8 + state.p * (w - 16), h - 10);\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "contrast-tau", "contrastive_temp", "Tau aplasta el lote en el positivo",
        "The contrastive loss divides similarities by a temperature tau before the softmax over the batch.",
        "2002.05709",
        [_knob("tau", "tau", 0.05, 2, 0.2, 0.05)],
        "  var tau = state.tau < 0.05 ? 0.05 : state.tau;\n"
        "  var sims = [2.1, 0.5, 0.2, -0.2];\n"
        "  var i, m = sims[0], exps = [], s = 0, bw, bh;\n"
        "  for (i = 1; i < sims.length; i++) if (sims[i] > m) m = sims[i];\n"
        "  for (i = 0; i < sims.length; i++) { exps[i] = Math.exp((sims[i] - m) / tau); s += exps[i]; }\n"
        "  bw = (w - 20) / sims.length;\n"
        "  for (i = 0; i < sims.length; i++) {\n"
        "    bh = (exps[i] / s) * (h - 30);\n"
        "    ctx.fillStyle = i === 0 ? \"#c4512c\" : \"#1f4b99\";\n"
        "    ctx.fillRect(10 + i * bw, h - 16 - bh, bw - 8, bh);\n"
        "  }\n",
    ),
    _row(
        "rms-eps", "rmsnorm", "Epsilon frena lo que la norma achica",
        "LLaMA normalizes with RMSNorm, dividing by the root mean square plus epsilon.",
        "2302.13971",
        [_knob("eps", "epsilon", 0.01, 8, 1, 0.05)],
        "  var vals = [1, -2, 0.5, 3];\n"
        "  var i, ms = 0, rms, bw = (w - 16) / vals.length, bh;\n"
        "  for (i = 0; i < vals.length; i++) ms += vals[i] * vals[i];\n"
        "  rms = Math.sqrt(ms / vals.length + state.eps);\n"
        "  for (i = 0; i < vals.length; i++) {\n"
        "    bh = Math.abs(vals[i] / rms) * h * 0.2;\n"
        "    ctx.fillStyle = \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h * 0.7 - bh, bw - 8, bh);\n"
        "  }\n",
    ),
    _row(
        "swiglu-beta", "swiglu", "La compuerta Swish abre o cierra",
        "The feed-forward network uses SwiGLU, a Swish gate multiplying the linear path.",
        "2302.13971",
        [_knob("beta", "beta", 0.2, 4, 1, 0.1)],
        "  var x, u, sig, y;\n"
        "  ctx.beginPath();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  for (x = 0; x < w; x++) {\n"
        "    u = (x / (w - 1)) * 6 - 3;\n"
        "    sig = 1 / (1 + Math.exp(-state.beta * u));\n"
        "    y = h * 0.7 - (u * sig) * h * 0.08;\n"
        "    if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "gqa-share", "gqa", "Menos grupos, más query por llave",
        "Grouped-query attention shares one key head across several query heads (GQA).",
        "2307.09288",
        [_knob("kv", "grupos", 1, 8, 2, 1)],
        "  var queries = 8, i, slot, bw = (w - 16) / queries;\n"
        "  for (i = 0; i < queries; i++) {\n"
        "    slot = Math.floor(i * state.kv / queries);\n"
        "    ctx.fillStyle = slot % 2 === 0 ? \"#1f4b99\" : \"#c4512c\";\n"
        "    ctx.fillRect(8 + i * bw, h * 0.3, bw - 3, 16 + slot * 6);\n"
        "  }\n",
    ),
    _row(
        "heads-split", "multihead", "Más cabezas, trozos más cortos",
        "Multi-head attention splits d_model into h heads.",
        "1706.03762",
        [_knob("heads", "cabezas", 1, 8, 4, 1)],
        "  var i, bw = (w - 16) / state.heads;\n"
        "  for (i = 0; i < state.heads; i++) {\n"
        "    ctx.fillStyle = i % 2 ? \"#c4512c\" : \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h * 0.35, bw - 3, h * 0.3);\n"
        "  }\n",
    ),
    _row(
        "alibi-slope", "alibi", "La pendiente apaga lo lejano",
        "ALiBi adds a head-specific slope as a linear bias on the attention scores.",
        "2108.12409",
        [_knob("slope", "pendiente", 0.05, 3, 0.6, 0.05)],
        "  var x, dist, y;\n"
        "  ctx.beginPath();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  for (x = 0; x < w; x++) {\n"
        "    dist = (x / (w - 1)) * 12;\n"
        "    y = h * 0.25 + state.slope * dist * (h * 0.04);\n"
        "    if (y > h - 8) y = h - 8;\n"
        "    if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "gelu-mix", "gelu", "GELU deja una cola bajo cero",
        "GELU weights the input by the Gaussian cdf instead of cutting at zero like ReLU.",
        "1606.08415",
        [_knob("mix", "mezcla", 0, 1, 0.5, 0.05)],
        "  var x, u, relu, inner, gelu, y;\n"
        "  ctx.beginPath();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  for (x = 0; x < w; x++) {\n"
        "    u = (x / (w - 1)) * 6 - 3;\n"
        "    relu = u > 0 ? u : 0;\n"
        "    inner = 0.797885 * (u + 0.044715 * u * u * u);\n"
        "    gelu = 0.5 * u * (1 + (Math.exp(2 * inner) - 1) / (Math.exp(2 * inner) + 1));\n"
        "    y = h * 0.65 - ((1 - state.mix) * relu + state.mix * gelu) * h * 0.1;\n"
        "    if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "smooth-eps", "label_smoothing", "Epsilon aplana la etiqueta smoothing",
        "Label smoothing spreads a probability eps off the true class.",
        "1512.00567",
        [_knob("eps", "epsilon", 0, 0.4, 0.1, 0.02)],
        "  var masses = [1 - state.eps, state.eps / 3, state.eps / 3, state.eps / 3];\n"
        "  var i, bw = (w - 16) / 4, bh;\n"
        "  for (i = 0; i < 4; i++) {\n"
        "    bh = masses[i] * (h - 30);\n"
        "    ctx.fillStyle = i === 0 ? \"#c4512c\" : \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h - 16 - bh, bw - 6, bh);\n"
        "  }\n",
    ),
    _row(
        "drop-rate", "dropout", "Sube la tasa y se apagan más celdas",
        "The dropout rate p_drop zeros hidden units during training.",
        "1207.0580",
        [_knob("p", "tasa", 0, 0.9, 0.3, 0.05)],
        "  var gates = [0.05, 0.2, 0.35, 0.5, 0.62, 0.74, 0.86, 0.95];\n"
        "  var i, bw = (w - 16) / gates.length;\n"
        "  for (i = 0; i < gates.length; i++) {\n"
        "    ctx.fillStyle = gates[i] < state.p ? \"#d9d3c7\" : \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h * 0.4, bw - 4, gates[i] < state.p ? 8 : 26);\n"
        "  }\n",
    ),
    _row(
        "warm-steps", "warmup", "Alargar el warmup retrasa el paso",
        "The learning rate warmup raises the step size linearly for warmup steps, then holds.",
        "1706.03762",
        [_knob("steps", "pasos", 10, 250, 80, 5)],
        "  var x, s, lr, y;\n"
        "  ctx.beginPath();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  for (x = 0; x < w; x++) {\n"
        "    s = (x / (w - 1)) * 300;\n"
        "    lr = s < state.steps ? s / state.steps : 1;\n"
        "    y = h * 0.8 - lr * h * 0.5;\n"
        "    if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "moe-k", "moe", "k expertos se prenden por token",
        "A mixture of experts routes each token to the top-k experts.",
        "1701.06538",
        [_knob("k", "k", 1, 4, 2, 1)],
        "  var scores = [0.9, 0.7, 0.55, 0.4, 0.25, 0.1];\n"
        "  var i, bw = (w - 16) / scores.length, bh;\n"
        "  for (i = 0; i < scores.length; i++) {\n"
        "    bh = (i < state.k ? scores[i] : 0.08) * h * 0.45;\n"
        "    ctx.fillStyle = i < state.k ? \"#c4512c\" : \"#d9d3c7\";\n"
        "    ctx.fillRect(8 + i * bw, h - 16 - bh, bw - 6, bh);\n"
        "  }\n",
    ),
    _row(
        "topk-cut", "topk", "k es el número, no la masa",
        "Top-k sampling keeps only the k most likely tokens and drops the rest.",
        "1904.09751",
        [_knob("k", "k", 1, 5, 2, 1)],
        "  var probs = [0.4, 0.25, 0.15, 0.12, 0.08];\n"
        "  var i, kept = 0, bw = (w - 16) / probs.length, bh;\n"
        "  for (i = 0; i < state.k && i < probs.length; i++) kept += probs[i];\n"
        "  for (i = 0; i < probs.length; i++) {\n"
        "    bh = (i < state.k ? probs[i] / kept : 0) * (h - 30);\n"
        "    ctx.fillStyle = i < state.k ? \"#1f4b99\" : \"#d9d3c7\";\n"
        "    ctx.fillRect(8 + i * bw, h - 16 - bh, bw - 6, bh);\n"
        "  }\n",
    ),
    _row(
        "focal-gamma", "focal", "Gamma apaga los ejemplos fáciles",
        "Focal loss down-weights easy examples by (1-p)^gamma.",
        "1708.02002",
        [_knob("gamma", "gamma", 0, 5, 2, 0.25)],
        "  var ps = [0.2, 0.5, 0.8, 0.95];\n"
        "  var i, bw = (w - 16) / ps.length, bh;\n"
        "  for (i = 0; i < ps.length; i++) {\n"
        "    bh = Math.pow(1 - ps[i], state.gamma) * (h - 30);\n"
        "    ctx.fillStyle = \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h - 16 - bh, bw - 6, bh);\n"
        "  }\n",
    ),
    _row(
        "pe-freqs", "positional_encoding", "La base frena las higher dimensions",
        "PE(pos, 2i) = sin(pos / 10000^{2i/d}) and a larger base slows the higher dimensions.",
        "1706.03762",
        [_knob("base", "base", 10, 100000, 10000, 10), _knob("dim", "par i", 0, 7, 4, 1)],
        "  var i, freq, bw = (w - 16) / 8, bh, x, y, fdim;\n"
        "  for (i = 0; i < 8; i++) {\n"
        "    freq = 1 / Math.pow(state.base, (2 * i) / 64);\n"
        "    bh = freq * h * 0.55;\n"
        "    ctx.fillStyle = i === state.dim ? \"#c4512c\" : \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h * 0.95 - bh, bw - 4, bh);\n"
        "  }\n"
        "  fdim = 1 / Math.pow(state.base, (2 * state.dim) / 64);\n"
        "  ctx.strokeStyle = \"#c4512c\";\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.beginPath();\n"
        "  for (i = 0; i <= 40; i++) {\n"
        "    x = 8 + (i / 40) * (w - 16);\n"
        "    y = h * 0.22 + Math.sin(i * fdim * 8) * (h * 0.12);\n"
        "    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n",
    ),
    _row(
        "temp-peak", "softmax_temperature", "Bajar la temperatura sube el pico",
        "We divide the logits by a temperature before the softmax.",
        "1706.03762",
        [_knob("temp", "temperatura", 0.05, 5, 1, 0.05)],
        "  var temp = state.temp < 0.05 ? 0.05 : state.temp;\n"
        "  var logits = [1.4, 0.3, -0.4];\n"
        "  var i, m = logits[0], e, s = 0, peak = 0, bh;\n"
        "  for (i = 1; i < logits.length; i++) if (logits[i] > m) m = logits[i];\n"
        "  for (i = 0; i < logits.length; i++) {\n"
        "    e = Math.exp((logits[i] - m) / temp);\n"
        "    s += e;\n"
        "    if (e > peak) peak = e;\n"
        "  }\n"
        "  bh = (peak / s) * (h - 24);\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.fillRect(w * 0.35, h - 16 - bh, w * 0.3, bh);\n",
    ),
    _row(
        "scale-peak", "attention_scale", "Sin la raíz, el pico se come el peso",
        "Attention scores grow with sqrt(d_k) unless the softmax is scaled back down.",
        "1706.03762",
        [_knob("d", "d_k", 4, 256, 64, 4)],
        "  var d = state.d < 1 ? 1 : state.d;\n"
        "  var raw = [1, 0.3, -0.2];\n"
        "  var s = Math.sqrt(d), i, m, z, acc = 0, peak = 0, bh;\n"
        "  m = raw[0] * s;\n"
        "  for (i = 1; i < raw.length; i++) if (raw[i] * s > m) m = raw[i] * s;\n"
        "  for (i = 0; i < raw.length; i++) {\n"
        "    z = Math.exp(raw[i] * s - m);\n"
        "    acc += z;\n"
        "    if (z > peak) peak = z;\n"
        "  }\n"
        "  bh = (peak / acc) * (h - 24);\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.fillRect(w * 0.3, h - 16 - bh, 36, bh);\n",
    ),
    _row(
        "sigma-z", "stddev", "Sigma mueve qué tan lejos se ve el punto",
        "A z-score divides the distance from the mean by the standard deviation sigma.",
        "1706.03762",
        [_knob("sigma", "sigma", 0.25, 4, 1, 0.05)],
        "  var z = 1.2 / state.sigma;\n"
        "  var x = w * 0.5 + z * 12;\n"
        "  if (x < 8) x = 8;\n"
        "  if (x > w - 8) x = w - 8;\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(8, h * 0.6);\n"
        "  ctx.lineTo(w - 8, h * 0.6);\n"
        "  ctx.stroke();\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.beginPath();\n"
        "  ctx.arc(x, h * 0.6, 5, 0, Math.PI * 2);\n"
        "  ctx.fill();\n",
    ),
    _row(
        "giou-gap", "giou", "IoU se queda en cero; el encierre no",
        "GIoU subtracts the empty part of the smallest enclosing box from IoU.",
        "1902.09630",
        [_knob("gap", "hueco", 0, 160, 110, 1)],
        "  var gap = state.gap, s = 58;\n"
        "  var ax0 = 28, ay0 = 46, ax1 = ax0 + s, ay1 = ay0 + s;\n"
        "  var bx0 = ax0 + gap, by0 = ay0, bx1 = bx0 + s, by1 = by0 + s;\n"
        "  var ix0 = Math.max(ax0, bx0), iy0 = Math.max(ay0, by0);\n"
        "  var ix1 = Math.min(ax1, bx1), iy1 = Math.min(ay1, by1);\n"
        "  var iw = ix1 - ix0, ih = iy1 - iy0;\n"
        "  if (iw < 0) iw = 0;\n"
        "  if (ih < 0) ih = 0;\n"
        "  var inter = iw * ih, union = s * s * 2 - inter, iou = inter / union;\n"
        "  var cx0 = Math.min(ax0, bx0), cy0 = Math.min(ay0, by0);\n"
        "  var cx1 = Math.max(ax1, bx1), cy1 = Math.max(ay1, by1);\n"
        "  var c = (cx1 - cx0) * (cy1 - cy0);\n"
        "  var giou = iou - (c - union) / c;\n"
        "  var y0 = 108, bh;\n"
        "  ctx.fillStyle = \"#e4d8bc\";\n"
        "  ctx.fillRect(cx0, cy0, cx1 - cx0, cy1 - cy0);\n"
        "  ctx.globalAlpha = 0.9;\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillRect(ax0, ay0, s, s);\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.fillRect(bx0, by0, s, s);\n"
        "  ctx.globalAlpha = 1;\n"
        "  ctx.strokeStyle = \"#5c564c\";\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(w - 92, y0);\n"
        "  ctx.lineTo(w - 12, y0);\n"
        "  ctx.stroke();\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  bh = iou * 72;\n"
        "  ctx.fillRect(w - 78, y0 - bh, 18, bh);\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  if (giou >= 0) ctx.fillRect(w - 46, y0 - giou * 72, 18, giou * 72);\n"
        "  else ctx.fillRect(w - 46, y0, 18, Math.min(72, -giou * 160));\n"
        "  ctx.fillStyle = \"#1c1915\";\n"
        "  ctx.font = \"12px sans-serif\";\n"
        "  ctx.fillText(\"IoU \" + Math.round(iou * 100), w - 96, 18);\n"
        "  ctx.fillText(\"GIoU \" + Math.round(giou * 100), w - 96, 34);\n",
    ),
    _row(
        "ppo-clip", "ppo_clip", "El recorte aplana los dos lados",
        "Proximal Policy Optimization clips the probability ratio with epsilon.",
        "1707.06347",
        [_knob("eps", "épsilon", 0.05, 0.5, 0.2, 0.05), _knob("ratio", "ratio", 0.2, 2, 1, 0.05)],
        "  var eps = state.eps, ratio = state.ratio, lo = 1 - eps, hi = 1 + eps;\n"
        "  function X(r) { return 36 + (r / 2) * (w - 52); }\n"
        "  function clipr(r) { return r < lo ? lo : r > hi ? hi : r; }\n"
        "  function obj(r, A) { var raw = r * A, cut = clipr(r) * A; return raw < cut ? raw : cut; }\n"
        "  function Y(v) { return h * 0.78 - (v + 2) * (h * 0.2); }\n"
        "  var i, r, y;\n"
        "  ctx.fillStyle = \"#d9e3f5\";\n"
        "  ctx.fillRect(X(lo), 16, Math.max(1, X(hi) - X(lo)), h - 36);\n"
        "  ctx.strokeStyle = \"#c8c0b2\";\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(36, Y(0));\n"
        "  ctx.lineTo(w - 12, Y(0));\n"
        "  ctx.stroke();\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.strokeStyle = \"#c4512c\";\n"
        "  ctx.beginPath();\n"
        "  for (i = 0; i <= 80; i++) {\n"
        "    r = i / 40; y = Y(obj(r, 1));\n"
        "    if (i === 0) ctx.moveTo(X(r), y); else ctx.lineTo(X(r), y);\n"
        "  }\n"
        "  ctx.stroke();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.beginPath();\n"
        "  for (i = 0; i <= 80; i++) {\n"
        "    r = i / 40; y = Y(obj(r, -1));\n"
        "    if (i === 0) ctx.moveTo(X(r), y); else ctx.lineTo(X(r), y);\n"
        "  }\n"
        "  ctx.stroke();\n"
        "  ctx.fillStyle = \"#1c1915\";\n"
        "  ctx.beginPath();\n"
        "  ctx.arc(X(ratio), Y(obj(ratio, 1)), 4, 0, Math.PI * 2);\n"
        "  ctx.fill();\n"
        "  ctx.font = \"12px sans-serif\";\n"
        "  ctx.fillStyle = \"#c4512c\";\n"
        "  ctx.fillText(\"A > 0\", 8, 16);\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillText(\"A < 0\", 8, h - 8);\n",
    ),
    _row(
        "nerf-freq", "nerf_freq", "Más frecuencias, un borde más fino",
        "A neural radiance field lifts each coordinate with L frequency levels, and a low L blurs the scene.",
        "2003.08934",
        [_knob("levels", "niveles", 1, 8, 6, 1)],
        "  var L = Math.round(state.levels), i, x, y, px;\n"
        "  if (L < 1) L = 1;\n"
        "  function raw(x) {\n"
        "    var s = 0, k, f;\n"
        "    for (k = 0; k < L; k++) { f = Math.pow(2, k); s += Math.cos(f * Math.PI * (x - 0.5)) / f; }\n"
        "    return s;\n"
        "  }\n"
        "  var mid = raw(0.5);\n"
        "  function pxOf(x) { return 12 + x * (w - 24); }\n"
        "  ctx.strokeStyle = \"#d9d3c7\";\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(pxOf(0.46), 22); ctx.lineTo(pxOf(0.46), h - 16);\n"
        "  ctx.moveTo(pxOf(0.54), 22); ctx.lineTo(pxOf(0.54), h - 16);\n"
        "  ctx.stroke();\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.beginPath();\n"
        "  for (i = 0; i <= 120; i++) {\n"
        "    x = i / 120; y = h * 0.82 - (raw(x) / mid) * (h * 0.55);\n"
        "    if (i === 0) ctx.moveTo(pxOf(x), y); else ctx.lineTo(pxOf(x), y);\n"
        "  }\n"
        "  ctx.stroke();\n"
        "  ctx.fillStyle = \"#1c1915\";\n"
        "  ctx.font = \"12px sans-serif\";\n"
        "  ctx.fillText(\"L = \" + L, 12, 16);\n",
    ),
    _row(
        "vit-patch", "vit_patch", "El parche grande se come la forma",
        "A Vision Transformer splits an image into patches of size P, and each patch is one token.",
        "2010.11929",
        [_knob("patch", "parche", 1, 4, 1, 1)],
        "  var p = state.patch < 1.5 ? 1 : state.patch < 3 ? 2 : 4;\n"
        "  var bits = [1,0,0,0,0,0,0,1, 0,1,0,0,0,0,1,0, 0,0,1,0,0,1,0,0, 0,0,0,1,1,0,0,0,"
        " 0,0,0,1,1,0,0,0, 0,0,1,0,0,1,0,0, 0,1,0,0,0,0,1,0, 1,0,0,0,0,0,0,1];\n"
        "  var n = 8, cell = Math.min((w - 96) / n, (h - 36) / n);\n"
        "  var x0 = 16, y0 = 28, pr, pc, r, c, acc, cnt;\n"
        "  for (pr = 0; pr < n; pr += p) {\n"
        "    for (pc = 0; pc < n; pc += p) {\n"
        "      acc = 0; cnt = 0;\n"
        "      for (r = pr; r < pr + p; r++) {\n"
        "        for (c = pc; c < pc + p; c++) { acc += bits[r * n + c]; cnt++; }\n"
        "      }\n"
        "      ctx.fillStyle = acc / cnt > 0.5 ? \"#1c1915\" : acc > 0 ? \"#8aa0c8\" : \"#f6f3ec\";\n"
        "      ctx.fillRect(x0 + pc * cell, y0 + pr * cell, cell * p - 1, cell * p - 1);\n"
        "      ctx.strokeStyle = \"#d9d3c7\";\n"
        "      ctx.strokeRect(x0 + pc * cell, y0 + pr * cell, cell * p - 1, cell * p - 1);\n"
        "    }\n"
        "  }\n"
        "  ctx.fillStyle = \"#1c1915\";\n"
        "  ctx.font = \"12px sans-serif\";\n"
        "  ctx.fillText((n / p) * (n / p) + \" tokens\", x0 + n * cell + 12, y0 + 14);\n",
    ),
    _row(
        "online-softmax", "online_softmax", "Al último bloque queda igual",
        "FlashAttention softmax is exact: the running max and the rescaled running sum, updated block by block, match the full softmax.",
        "2205.14135",
        [_knob("blocks", "bloques", 1, 4, 2, 1)],
        "  var S = [1.2, 0.2, 2.4, -0.5, 0.1, 1.8, -1, 3.1, 0.4, 0, 1.1, -0.2, 2, 0.6, -0.8, 1.5];\n"
        "  var blocks = state.blocks, n = 16, seen = blocks * 4;\n"
        "  var m = -1e9, l = 0, i, b, mb, m2, acc, Fm, Fl, diff, bw, x, p, pf;\n"
        "  Fm = -1e9; Fl = 0;\n"
        "  for (i = 0; i < n; i++) if (S[i] > Fm) Fm = S[i];\n"
        "  for (i = 0; i < n; i++) Fl += Math.exp(S[i] - Fm);\n"
        "  for (b = 0; b < blocks; b++) {\n"
        "    mb = -1e9;\n"
        "    for (i = b * 4; i < b * 4 + 4; i++) if (S[i] > mb) mb = S[i];\n"
        "    m2 = m > mb ? m : mb;\n"
        "    acc = 0;\n"
        "    for (i = b * 4; i < b * 4 + 4; i++) acc += Math.exp(S[i] - m2);\n"
        "    l = l * Math.exp(m - m2) + acc;\n"
        "    m = m2;\n"
        "  }\n"
        "  diff = 0;\n"
        "  bw = (w - 24) / n;\n"
        "  for (i = 0; i < n; i++) {\n"
        "    pf = Math.exp(S[i] - Fm) / Fl;\n"
        "    p = i < seen ? Math.exp(S[i] - m) / l : 0;\n"
        "    if (i < seen && Math.abs(p - pf) > diff) diff = Math.abs(p - pf);\n"
        "    x = 12 + i * bw;\n"
        "    ctx.fillStyle = \"#d9d3c7\";\n"
        "    ctx.fillRect(x, h * 0.78 - pf * h * 0.5, bw - 2, pf * h * 0.5);\n"
        "    if (p > 0) {\n"
        "      ctx.fillStyle = \"#1f4b99\";\n"
        "      ctx.fillRect(x, h * 0.78 - p * h * 0.5, bw - 2, Math.max(1, p * h * 0.5));\n"
        "    }\n"
        "  }\n"
        "  ctx.fillStyle = \"#5c564c\";\n"
        "  ctx.font = \"13px sans-serif\";\n"
        "  ctx.fillText(diff < 0.001 ? \"igual\" : \"aún no\", 8, 16);\n",
    ),
    _row(
        "chinchilla-valley", "chinchilla", "El cómputo fijo hace un valle",
        "For a fixed compute budget C approximately 6ND, the Chinchilla loss is a valley: there is a best model size.",
        "2203.15556",
        [_knob("budget", "presupuesto", 18, 24, 22, 0.5)],
        "  var C = Math.pow(10, state.budget);\n"
        "  var i, logn, N, D, L, best = 1e9, bestI = 0, lo = 1e9, hi = 0, x, y;\n"
        "  var pts = [];\n"
        "  for (i = 0; i <= 48; i++) {\n"
        "    logn = 7 + (i / 48) * 5;\n"
        "    N = Math.pow(10, logn);\n"
        "    D = C / (6 * N);\n"
        "    L = 1.69 + 406.4 * Math.pow(N, -0.34) + 410.7 * Math.pow(D, -0.28);\n"
        "    pts.push(L);\n"
        "    if (L < best) { best = L; bestI = i; }\n"
        "    if (L < lo) lo = L;\n"
        "    if (L > hi) hi = L;\n"
        "  }\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.beginPath();\n"
        "  for (i = 0; i <= 48; i++) {\n"
        "    x = 16 + (i / 48) * (w - 32);\n"
        "    y = h * 0.82 - ((pts[i] - lo) / (hi - lo)) * (h * 0.56);\n"
        "    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n"
        "  }\n"
        "  ctx.stroke();\n"
        "  x = 16 + (bestI / 48) * (w - 32);\n"
        "  ctx.strokeStyle = \"#c4512c\";\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(x, h * 0.22);\n"
        "  ctx.lineTo(x, h * 0.84);\n"
        "  ctx.stroke();\n"
        "  ctx.fillStyle = \"#5c564c\";\n"
        "  ctx.font = \"13px sans-serif\";\n"
        "  ctx.fillText(\"\" + Math.round(best * 100) / 100, 8, 16);\n",
    ),
]


def _spec_row(spec):
    return _row(spec["id"], spec["name"], spec["title"], spec["claim"], spec["arxiv"], spec["controls"], spec["body"])


CATALOG = CATALOG + [_spec_row(spec) for spec in SPECS]


def __getattr__(name):
    if name == "COUNT":
        return len(CATALOG)
    raise AttributeError(name)
