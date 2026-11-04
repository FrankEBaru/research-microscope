/* Copied from rrm/liveart gold_widget so the browser bundle can run offline. */
export const GOLD = [
  {
    "id": "positional-encoding",
    "topic": "positional_encoding",
    "title": "La base cambia el ritmo de la onda",
    "explain": "Cada par de dimensiones es una onda. La base cambia qué tan rápido gira: las primeras vuelven seguido y las últimas casi no. Por eso una posición cercana se parece y una lejana no.",
    "questions": [
      {
        "q": "¿Por qué una base más grande hace más lentas las dimensiones altas?",
        "why": "la base está en el exponente de la frecuencia"
      },
      {
        "q": "¿Qué se confunde si todas las ondas van igual de rápido?",
        "why": "la posición deja de separarse entre dimensiones"
      },
      {
        "q": "¿Cómo cabe una frase larga en un seno y un coseno?",
        "why": "las frecuencias bajas dan vueltas despacio"
      },
      {
        "q": "¿Por qué una posición cercana se parece y una lejana no?",
        "why": "el producto de las ondas cae con la distancia"
      }
    ],
    "controls": [
      {
        "id": "base",
        "label": "base",
        "min": 10,
        "max": 100000,
        "value": 10000,
        "step": 10
      },
      {
        "id": "dim",
        "label": "par i",
        "min": 0,
        "max": 8,
        "value": 4,
        "step": 1
      }
    ],
    "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, base = state.base, i = state.dim;\n  var N = 48, p = (t * 8) % N, q, k, u, v, s, x, y, pos;\n  function freq(k) { return 1 / Math.pow(base, (2 * k) / 64); }\n  function pe(q, k) {\n    var f = freq(k);\n    return [Math.sin(q * f), Math.cos(q * f)];\n  }\n  function sim(a, b) {\n    s = 0;\n    for (k = 0; k < 8; k++) { u = pe(a, k); v = pe(b, k); s += u[0] * v[0] + u[1] * v[1]; }\n    return s / 8;\n  }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.strokeStyle = \"#1f4b99\";\n  ctx.lineWidth = 2;\n  ctx.beginPath();\n  for (x = 0; x < w; x++) {\n    pos = (x / (w - 1)) * N;\n    y = h * 0.26 - Math.sin(pos * freq(i) + t * 0.6) * (h * 0.16);\n    if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n  }\n  ctx.stroke();\n  ctx.strokeStyle = \"#c4512c\";\n  ctx.beginPath();\n  for (q = 0; q <= N; q++) {\n    x = (q / N) * (w - 1);\n    y = h * 0.92 - ((sim(p, q) + 1) / 2) * (h * 0.38);\n    if (q === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n  }\n  ctx.stroke();\n  x = (p / N) * (w - 1);\n  ctx.lineWidth = 1;\n  ctx.beginPath();\n  ctx.moveTo(x, h * 0.48);\n  ctx.lineTo(x, h - 4);\n  ctx.stroke();\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"onda\", 8, 14);\n  ctx.fillText(\"parecido\", 8, h * 0.46);\n}"
  },
  {
    "id": "softmax-temperature",
    "topic": "softmax_temperature",
    "title": "La temperatura afila el softmax",
    "explain": "La temperatura parte los logits antes del softmax. Baja, y casi toda la masa cae en la opción más alta; alta, y las opciones se parecen.",
    "questions": [
      {
        "q": "¿Por qué bajar la temperatura vuelve una sola opción casi segura?",
        "why": "el softmax se concentra en el logit mayor"
      },
      {
        "q": "¿Qué queda de la distribución si la temperatura es muy alta?",
        "why": "las opciones se acercan"
      },
      {
        "q": "¿Qué se está moviendo: los logits o las palabras?",
        "why": "el control parte los logits"
      }
    ],
    "controls": [
      {
        "id": "temp",
        "label": "temperatura",
        "min": 0.05,
        "max": 5,
        "value": 1,
        "step": 0.05
      }
    ],
    "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, temp = state.temp;\n  var logits = [1.2, 0.4, -0.2, -0.8];\n  var i, m = logits[0], exps = [], s = 0, p, bw, bh, gap;\n  if (temp < 0.05) temp = 0.05;\n  for (i = 1; i < logits.length; i++) if (logits[i] > m) m = logits[i];\n  for (i = 0; i < logits.length; i++) {\n    exps[i] = Math.exp((logits[i] - m) / temp);\n    s += exps[i];\n  }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  gap = 12;\n  bw = (w - gap * (logits.length + 1)) / logits.length;\n  for (i = 0; i < logits.length; i++) {\n    p = exps[i] / s;\n    bh = p * (h - 36);\n    ctx.fillStyle = i === 0 ? \"#c4512c\" : \"#1f4b99\";\n    ctx.fillRect(gap + i * (bw + gap), h - 16 - bh, bw, bh);\n  }\n}"
  },
  {
    "id": "attention-scale",
    "topic": "attention_scale",
    "title": "Dividir entre la raíz aplana el peso",
    "explain": "El producto QK crece con la dimensión. Dividir entre la raíz de d_k deja el softmax en una zona donde más de una clave todavía pesa.",
    "questions": [
      {
        "q": "¿Por qué se divide entre la raíz de d_k y no entre d_k?",
        "why": "la varianza del producto es d_k, no d_k al cuadrado"
      },
      {
        "q": "¿Qué le pasa al softmax si el producto crece con la dimensión?",
        "why": "una sola clave se queda con el peso"
      },
      {
        "q": "¿Cómo se reparte el peso de una clave con y sin esa división?",
        "why": "el dibujo muestra las dos filas"
      }
    ],
    "controls": [
      {
        "id": "d",
        "label": "d_k",
        "min": 4,
        "max": 256,
        "value": 64,
        "step": 4
      }
    ],
    "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, d = state.d;\n  var raw = [1, 0.4, 0, -0.3];\n  var s = Math.sqrt(d < 1 ? 1 : d);\n  var grown = [], flat = [], i, gap, bw, x;\n  function probs(xs) {\n    var m = xs[0], k, out = [], acc = 0;\n    for (k = 1; k < xs.length; k++) if (xs[k] > m) m = xs[k];\n    for (k = 0; k < xs.length; k++) { out[k] = Math.exp(xs[k] - m); acc += out[k]; }\n    for (k = 0; k < xs.length; k++) out[k] = out[k] / acc;\n    return out;\n  }\n  for (i = 0; i < raw.length; i++) { grown[i] = raw[i] * s; flat[i] = raw[i]; }\n  var top = probs(grown), bot = probs(flat);\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  gap = 8;\n  bw = (w - gap * (raw.length + 1)) / raw.length;\n  for (i = 0; i < raw.length; i++) {\n    x = gap + i * (bw + gap);\n    ctx.fillStyle = \"#c4512c\";\n    ctx.fillRect(x, h * 0.46 - top[i] * (h * 0.40), bw, top[i] * (h * 0.40));\n    ctx.fillStyle = \"#1f4b99\";\n    ctx.fillRect(x, h * 0.96 - bot[i] * (h * 0.40), bw, bot[i] * (h * 0.40));\n  }\n}"
  },
  {
    "id": "stddev",
    "topic": "stddev",
    "title": "Sigma es el ancho de la nube",
    "explain": "La desviación estándar es el ancho de la nube alrededor de la media. Al dividir entre sigma, puntos lejanos y cercanos quedan en la misma escala.",
    "questions": [
      {
        "q": "¿Qué cambia en los puntos si subo la desviación estándar?",
        "why": "la nube se abre alrededor de la media"
      },
      {
        "q": "¿Por qué dividir entre sigma los pone en la misma escala?",
        "why": "se quita el ancho de la nube"
      },
      {
        "q": "¿Qué tan lejos de la media queda un punto cuando sigma es chico?",
        "why": "la misma distancia numérica pesa más"
      }
    ],
    "controls": [
      {
        "id": "sigma",
        "label": "sigma",
        "min": 0.25,
        "max": 4,
        "value": 1,
        "step": 0.05
      }
    ],
    "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, sigma = state.sigma;\n  var pts = [-1.2, -0.4, 0.1, 0.8, 1.5];\n  var mid = h * 0.55, band = sigma * 22, i, x, y;\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.fillStyle = \"#d9e3f5\";\n  ctx.fillRect(0, mid - band, w, band * 2);\n  ctx.strokeStyle = \"#1f4b99\";\n  ctx.lineWidth = 1;\n  ctx.beginPath();\n  ctx.moveTo(0, mid);\n  ctx.lineTo(w, mid);\n  ctx.stroke();\n  ctx.fillStyle = \"#c4512c\";\n  for (i = 0; i < pts.length; i++) {\n    x = (i + 1) * w / (pts.length + 1);\n    y = mid - pts[i] * sigma * 22;\n    ctx.beginPath();\n    ctx.arc(x, y, 4, 0, Math.PI * 2);\n    ctx.fill();\n  }\n}"
  }
];
