"""Treinta widgets emulados, como saldrían de Muse Code. No van dentro del prompt.

Los cuatro de oro siguen en fewshots.py y son los únicos few-shots del prompt.
Estos pasan por el mismo verificador. RRM-80 puede reemplazar un draw; la forma no cambia.
"""

from rrm.liveart.offline import _by_name


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

CATALOG = [
    _row(
        "rope-angle", "rope", "El ángulo guarda la posición",
        "RoPE rotates each position by an angle instead of adding a sinusoid.",
        "2302.13971",
        [_knob("theta", "ángulo", 0.2, 4, 1, 0.1)],
        "  var ang = state.theta * 0.8;\n"
        "  var cx = w * 0.5, cy = h * 0.55, r = h * 0.28;\n"
        "  ctx.strokeStyle = \"#1f4b99\";\n"
        "  ctx.lineWidth = 2;\n"
        "  ctx.beginPath();\n"
        "  ctx.moveTo(cx, cy);\n"
        "  ctx.lineTo(cx + Math.cos(ang) * r, cy - Math.sin(ang) * r);\n"
        "  ctx.stroke();\n",
    ),
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
        "noise-beta", "noise_schedule", "Beta abre la nube de ruido",
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
        "guide-push", "guidance", "La escala empuja hacia el texto",
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
        "guide-width", "guidance", "Más guía, más peso del texto",
        "The guidance scale w pushes the sample away from the unconditional prediction.",
        "2205.01138",
        [_knob("scale", "guía", 0, 5, 1.5, 0.1)],
        "  var bw = 20 + state.scale * 18;\n"
        "  ctx.fillStyle = \"#1f4b99\";\n"
        "  ctx.fillRect(w * 0.5 - bw / 2, h * 0.3, bw, h * 0.35);\n",
    ),
    _row(
        "detr-match", "detr_match", "El peso de la clase mueve el emparejamiento",
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
        "skip-mix", "residual", "El atajo mezcla entrada y salida",
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
        "nucleus-line", "nucleus", "La raya corta la masa acumulada",
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
        "gqa-share", "gqa", "Menos grupos, más consultas por llave",
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
        "smooth-eps", "label_smoothing", "Epsilon aplana la etiqueta",
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
        "warm-steps", "warmup", "Alargar el calentamiento retrasa el paso",
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
        "pe-freqs", "positional_encoding", "La base cambia el ritmo por dimensión",
        "PE(pos, 2i) = sin(pos / 10000^{2i/d}) and a larger base slows the higher dimensions.",
        "1706.03762",
        [_knob("base", "base", 10, 100000, 10000, 10), _knob("dim", "par i", 0, 7, 4, 1)],
        "  var i, freq, bw = (w - 16) / 8, bh;\n"
        "  for (i = 0; i < 8; i++) {\n"
        "    freq = 1 / Math.pow(state.base, (2 * i) / 64);\n"
        "    bh = freq * h * 0.55;\n"
        "    ctx.fillStyle = i === state.dim ? \"#c4512c\" : \"#1f4b99\";\n"
        "    ctx.fillRect(8 + i * bw, h - 16 - bh, bw - 4, bh);\n"
        "  }\n",
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
]


def __getattr__(name):
    if name == "COUNT":
        return len(CATALOG)
    raise AttributeError(name)
