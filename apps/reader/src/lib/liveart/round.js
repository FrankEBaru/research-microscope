// The fifteen topics. Every entry is a redesign posted for this quality pass.
export const ROUND = [
  {
    "source": "round",
    "widget": {
      "id": "adam-valley",
      "topic": "adam",
      "title": "En el valle angosto SGD rebota y Adam no",
      "explain": "Adam (Kingma y Ba, 1412.6980, algoritmo 1) da el paso m̂/(√v̂+ε), con β1 0.9, β2 0.999 y ε 1e-8. El valle f = ½x² + pared·y² es un juguete, no una figura medida: en y el gradiente es 2·pared veces el de x. Con pared 20, SGD rebota; si el lr pasa el umbral de la derecha, se sale. El segundo momento achica ese eje y Adam se queda. Baja la pared a 1 y SGD también baja liso. No es una corrida de entrenamiento.",
      "questions": [
        {
          "q": "Sube el paso a 0.08. ¿Quién se sale del valle?",
          "why": "SGD cruza el umbral y Adam sigue dentro"
        },
        {
          "q": "Baja la pared a 1. ¿SGD sigue rebotando?",
          "why": "en un valle redondo el paso de y ya no es enorme"
        },
        {
          "q": "En el paso 0.04 y pared 20, ¿quién baja liso?",
          "why": "Adam, porque el segundo momento frena la pared"
        },
        {
          "q": "¿Este valle es una curva del paper?",
          "why": "no: es un juguete para ver el paso"
        }
      ],
      "controls": [
        {
          "id": "lr",
          "label": "paso lr",
          "min": 0.02,
          "max": 0.1,
          "value": 0.04,
          "step": 0.01
        },
        {
          "id": "wall",
          "label": "pared",
          "min": 1,
          "max": 20,
          "value": 20,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, lr = state.lr, wall = state.wall;\n  var b1 = 0.9, b2 = 0.999, eps = 0.00000001;\n  var x0 = 28, y0 = 18, pw = w * 0.62, ph = h - 36;\n  function X(x) { return x0 + (x + 1.5) / 3 * pw; }\n  function Y(y) { return y0 + (1.15 - y) / 2.3 * ph; }\n  var levels = [0.5, 1.5, 3, 6, 9], li, a, c, ct, st, px, py;\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.strokeStyle = \"#e4d6c4\";\n  ctx.lineWidth = 1;\n  for (li = 0; li < levels.length; li++) {\n    c = levels[li];\n    ctx.beginPath();\n    for (a = 0; a <= 48; a++) {\n      ct = Math.cos(a / 48 * 6.2832);\n      st = Math.sin(a / 48 * 6.2832);\n      px = Math.sqrt(2 * c) * ct;\n      py = Math.sqrt(c / wall) * st;\n      if (a === 0) ctx.moveTo(X(px), Y(py)); else ctx.lineTo(X(px), Y(py));\n    }\n    ctx.stroke();\n  }\n  function path(kind) {\n    var x = -1.15, y = 0.55, mx = 0, my = 0, vx = 0, vy = 0;\n    var step, gx, gy, out = 0, mhx, mhy, vhx, vhy, ymin = y;\n    ctx.beginPath();\n    ctx.moveTo(X(x), Y(y));\n    for (step = 1; step <= 26; step++) {\n      gx = x;\n      gy = 2 * wall * y;\n      if (kind === 0) { x = x - lr * gx; y = y - lr * gy; }\n      else {\n        mx = b1 * mx + (1 - b1) * gx;\n        my = b1 * my + (1 - b1) * gy;\n        vx = b2 * vx + (1 - b2) * gx * gx;\n        vy = b2 * vy + (1 - b2) * gy * gy;\n        mhx = mx / (1 - Math.pow(b1, step));\n        mhy = my / (1 - Math.pow(b1, step));\n        vhx = vx / (1 - Math.pow(b2, step));\n        vhy = vy / (1 - Math.pow(b2, step));\n        x = x - lr * mhx / (Math.sqrt(vhx) + eps);\n        y = y - lr * mhy / (Math.sqrt(vhy) + eps);\n      }\n      if (y < ymin) ymin = y;\n      if (x > 1.45 || x < -1.45 || y > 1.1 || y < -1.1) {\n        var cx = x, cy = y;\n        if (cx > 1.45) cx = 1.45;\n        if (cx < -1.45) cx = -1.45;\n        if (cy > 1.1) cy = 1.1;\n        if (cy < -1.1) cy = -1.1;\n        ctx.lineTo(X(cx), Y(cy));\n        out = 1;\n        break;\n      }\n      ctx.lineTo(X(x), Y(y));\n    }\n    ctx.stroke();\n    if (kind === 1 && ymin < -0.05 && y > ymin + 0.08) adamBack = 1;\n    return out;\n  }\n  var adamBack = 0;\n  ctx.strokeStyle = \"#c4512c\";\n  ctx.lineWidth = 2;\n  var sgdOut = path(0);\n  ctx.strokeStyle = \"#1f4b99\";\n  ctx.lineWidth = 2;\n  path(1);\n  var lx = x0 + pw + 14;\n  ctx.fillStyle = \"#c4512c\";\n  ctx.fillRect(lx, 40, 10, 10);\n  ctx.fillStyle = \"#1f4b99\";\n  ctx.fillRect(lx, 60, 10, 10);\n  ctx.font = \"13px sans-serif\";\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.fillText(\"SGD\", lx + 16, 50);\n  ctx.fillText(\"Adam\", lx + 16, 70);\n  ctx.fillStyle = sgdOut ? \"#c4512c\" : \"#1d1a16\";\n  if (sgdOut) ctx.fillText(\"SGD se sale\", lx, 98);\n  else if (wall < 8) ctx.fillText(\"pared suave\", lx, 98);\n  else ctx.fillText(\"SGD rebota\", lx, 98);\n  ctx.fillStyle = \"#8a8175\";\n  ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"lr \" + Math.round(lr * 100) / 100, lx, 118);\n  ctx.fillText(\"umbral \" + (Math.round(100 / wall) / 100), lx, 134);\n  if (adamBack) {\n    ctx.fillStyle = \"#1f4b99\";\n    ctx.fillText(\"Adam se pasa y vuelve\", lx, 154);\n  }\n  ctx.fillText(\"f = 1/2 x^2 + pared y^2\", x0, 16);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "attn-walk",
      "topic": "attention_scale",
      "title": "¿Por qué dividir entre √d_k, y no entre d_k?",
      "explain": "Izquierda: qué tan dispersos quedan los puntajes q·k según d_k. Sin dividir crecen como √d_k (varianza d_k, nota al pie del paper); entre d_k se aplastan; entre √d_k quedan en 1 para cualquier d_k. Derecha: el softmax de 8 claves con esa escala; el contorno es el mismo caso sin dividir. Muy afilado, casi no pasa gradiente; muy plano, no elige. Las 8 claves son de juguete; d_k = 64 es el del paper.",
      "questions": [
        {
          "q": "¿Por qué el puntaje q·k crece cuando sube d_k?",
          "why": "Sube d_k a 1024 con la escala en 0: la curva izquierda llega a 32 y el softmax se vuelve una sola barra."
        },
        {
          "q": "¿Qué tiene de malo un softmax casi one-hot si elige bien?",
          "why": "Con escala 0 y d_k 1024 el medidor de gradiente cae a casi 0: el modelo casi no aprende de esas claves."
        },
        {
          "q": "¿Por qué la raíz y no d_k completo?",
          "why": "Pon la escala en 1: con d_k grande todo queda plano y no elige. Solo en 0.5 la dispersión no depende de d_k."
        },
        {
          "q": "¿Dividir cambia cuál clave gana?",
          "why": "Mueve la escala de 0 a 1: la barra coral siempre es la más alta. Cambia cuánto gana, no quién."
        }
      ],
      "controls": [
        {
          "id": "dk",
          "label": "log2 d_k",
          "min": 0,
          "max": 10,
          "value": 6,
          "step": 1
        },
        {
          "id": "p",
          "label": "escala: dividir entre d_k^p",
          "min": 0,
          "max": 1,
          "value": 0.5,
          "step": 0.05
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, d = Math.pow(2, state.dk), p = state.p, i, k;\n  var z = [1.9, 1.1, 0.6, 0.2, -0.1, -0.5, -0.9, -1.4], n = 8, s = [], e = [], sum = 0, mx = -1e9;\n  var spread = Math.pow(d, 0.5 - p);\n  for (i = 0; i < n; i++) { s[i] = z[i] * spread; if (s[i] > mx) mx = s[i]; }\n  for (i = 0; i < n; i++) { e[i] = Math.exp(s[i] - mx); sum += e[i]; }\n  var s0 = [], e0 = [], sum0 = 0, m0 = -1e9;\n  for (i = 0; i < n; i++) { s0[i] = z[i] * Math.sqrt(d); if (s0[i] > m0) m0 = s0[i]; }\n  for (i = 0; i < n; i++) { e0[i] = Math.exp(s0[i] - m0); sum0 += e0[i]; }\n  for (i = 0; i < n; i++) e0[i] = e0[i] / sum0;\n  var pm = 0, g = 0;\n  for (i = 0; i < n; i++) { e[i] = e[i] / sum; if (e[i] > pm) pm = e[i]; g += e[i] * (1 - e[i]); }\n  g = g / (1 - 1 / n);\n  function r2(v) { return Math.round(v * 100) / 100; }\n  ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(0, 0, w, h);\n  ctx.fillStyle = \"#1d1a16\"; ctx.font = \"15px sans-serif\"; ctx.textAlign = \"left\";\n  ctx.fillText(\"softmax( q·k / d_k^\" + r2(p) + \" )     d_k = \" + d + \"  →  se divide entre \" + r2(Math.pow(d, p)), 14, 22);\n  var x0 = 44, y0 = h - 44, pw = w * 0.42, ph = h - 110, top = 52;\n  function X(lg) { return x0 + lg / 10 * pw; }\n  function Y(v) { var l = Math.log(v) / Math.log(2); if (l > 5) l = 5; if (l < -5) l = -5; return top + (5 - l) / 10 * ph; }\n  ctx.strokeStyle = \"#cfc5b5\"; ctx.lineWidth = 1; ctx.strokeRect(x0, top, pw, ph);\n  ctx.strokeStyle = \"#e3dacb\"; ctx.beginPath(); ctx.moveTo(x0, Y(1)); ctx.lineTo(x0 + pw, Y(1)); ctx.stroke();\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#6b6358\";\n  ctx.fillText(\"32\", x0 - 22, Y(32) + 4); ctx.fillText(\"1\", x0 - 14, Y(1) + 4); ctx.fillText(\"1/32\", x0 - 32, Y(1 / 32) + 4);\n  ctx.fillText(\"d_k = 1\", x0, y0 + 26); ctx.textAlign = \"right\"; ctx.fillText(\"1024\", x0 + pw, y0 + 26); ctx.textAlign = \"left\";\n  ctx.save(); ctx.translate(14, top + ph / 2 + 40); ctx.rotate(-Math.PI / 2); ctx.fillText(\"dispersión de los puntajes\", 0, 0); ctx.restore();\n  var refs = [[0, \"sin dividir\"], [0.5, \"÷ √d_k (paper)\"], [1, \"÷ d_k\"]];\n  for (k = 0; k < 3; k++) {\n    var pk = refs[k][0];\n    ctx.strokeStyle = \"#b7aa9a\"; ctx.lineWidth = 1; ctx.beginPath();\n    ctx.moveTo(X(0), Y(1)); ctx.lineTo(X(10), Y(Math.pow(1024, 0.5 - pk))); ctx.stroke();\n    ctx.fillStyle = \"#8a7f70\"; ctx.textAlign = \"right\";\n    ctx.fillText(refs[k][1], X(10) - 4, Y(Math.pow(1024, 0.5 - pk)) + (k === 0 ? 14 : (k === 2 ? -6 : -6)));\n    ctx.textAlign = \"left\";\n  }\n  ctx.strokeStyle = \"#1f4b99\"; ctx.lineWidth = 3; ctx.beginPath();\n  ctx.moveTo(X(0), Y(1)); ctx.lineTo(X(10), Y(Math.pow(1024, 0.5 - p))); ctx.stroke();\n  ctx.strokeStyle = \"#c4512c\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(X(6), top); ctx.lineTo(X(6), y0); ctx.stroke();\n  ctx.fillStyle = \"#c4512c\"; ctx.fillText(\"64 = paper (fijo)\", X(6) + 3, y0 - 4);\n  ctx.fillStyle = \"#1f4b99\"; ctx.beginPath(); ctx.arc(X(state.dk), Y(spread), 6, 0, 2 * Math.PI); ctx.fill();\n  var bx = w * 0.56, bw = (w - bx - 16) / n, by = top + ph * 0.72, bh = ph * 0.62;\n  ctx.fillStyle = \"#1d1a16\"; ctx.font = \"13px sans-serif\"; ctx.fillText(\"pesos del softmax (8 claves)\", bx, top + 4);\n  ctx.strokeStyle = \"#cfc5b5\"; ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(w - 12, by); ctx.stroke();\n  for (i = 0; i < n; i++) {\n    ctx.fillStyle = i === 0 ? \"#c4512c\" : \"#1f4b99\";\n    ctx.fillRect(bx + i * bw + 3, by - e[i] * bh, bw - 6, Math.max(2, e[i] * bh));\n    if (p > 0.02) { ctx.strokeStyle = \"#8a7f70\"; ctx.lineWidth = 1; ctx.strokeRect(bx + i * bw + 3.5, by - e0[i] * bh + 0.5, bw - 7, Math.max(1, e0[i] * bh)); }\n  }\n  var same = 1; for (i = 0; i < n; i++) if (Math.abs(e0[i] - e[i]) > 0.01) same = 0;\n  if (p > 0.02) { ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#6b6358\"; ctx.textAlign = \"right\"; ctx.fillText(same ? \"contorno = barras: aquí dividir no cambia nada\" : \"contorno: sin dividir, mismo d_k\", w - 12, top + 20); ctx.textAlign = \"left\"; }\n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#c4512c\"; ctx.fillText(\"máx \" + r2(pm), bx, by + 18);\n  var reg = pm > 0.9 ? \"casi one-hot: casi no pasa gradiente\" : (pm < 1.6 / n ? \"casi plano: pasa gradiente, pero no elige\" : \"reparte y elige\");\n  ctx.fillStyle = pm > 0.9 || pm < 1.6 / n ? \"#c4512c\" : \"#2e7d32\"; ctx.font = \"13px sans-serif\";\n  ctx.fillText(reg, bx, by + 38);\n  var my = by + 52, mw = w - bx - 16;\n  ctx.fillStyle = \"#6b6358\"; ctx.font = \"11px sans-serif\"; ctx.fillText(\"gradiente que llega a las claves (Σ p(1−p), 1 = plano)\", bx, my);\n  ctx.fillStyle = \"#e3dacb\"; ctx.fillRect(bx, my + 6, mw, 10);\n  ctx.fillStyle = g < 0.15 ? \"#c4512c\" : \"#2e7d32\"; ctx.fillRect(bx, my + 6, Math.max(2, mw * g), 10);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "int8-outlier",
      "topic": "quant",
      "title": "Un solo valor grande deja sin niveles a los demás",
      "explain": "absmax reparte 255 niveles entre −máx y +máx: el paso es máx/127. Las líneas son esos niveles; cada valor chico cae en la más cercana (punto azul) y la raya coral es el error. Un outlier agranda el paso y los chicos se quedan con pocos niveles. LLM.int8() deja los valores > 6 en 16 bits (≈0.1% de las dimensiones). Los 15 valores chicos son de juguete; 6.0 y «hasta 20x» son del paper.",
      "questions": [
        {
          "q": "¿Por qué un solo número grande arruina a los chicos?",
          "why": "Sube el outlier de 1 a 120: las líneas de nivel se separan, el error crece decenas de veces y los chicos empiezan a caer en 0."
        },
        {
          "q": "Con 8 bits hay 255 niveles: ¿no alcanzan?",
          "why": "Mira el contador: con outlier 20 los 15 chicos usan solo unos pocos de los 255 niveles; el resto se gasta en el rango del outlier."
        },
        {
          "q": "¿Y si tiro el outlier o lo pongo en 0?",
          "why": "Modo 1: los chicos quedan finos, pero el outlier pierde todo su valor. El paper mide que eso empeora la perplejidad 600–1000%."
        },
        {
          "q": "¿Qué hace LLM.int8() con el outlier?",
          "why": "Modo 2: lo que pasa de 6 va aparte en 16 bits, exacto, y el paso vuelve a ser fino para el 99.9% restante."
        }
      ],
      "controls": [
        {
          "id": "mag",
          "label": "tamaño del outlier",
          "min": 1,
          "max": 120,
          "value": 20,
          "step": 1
        },
        {
          "id": "mode",
          "label": "modo 0 absmax·1 tirar·2 int8",
          "min": 0,
          "max": 2,
          "value": 0,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, mag = state.mag, mode = Math.round(state.mode), n = 15, i, k;\n  var xs = [], qv = [], amax = 0, used = [], nu = 0, es = 0;\n  for (i = 0; i < n; i++) xs[i] = Math.sin(i * 1.7 + 0.4) * 0.9;\n  var big = mode === 2 && mag > 6, gone = mode === 1;\n  for (i = 0; i < n; i++) amax = Math.max(amax, Math.abs(xs[i]));\n  if (!big && !gone) amax = Math.max(amax, mag);\n  var step = amax / 127;\n  for (i = 0; i < n; i++) {\n    k = Math.round(xs[i] / step); qv[i] = k * step; es += Math.abs(qv[i] - xs[i]);\n    var f = 0, j; for (j = 0; j < nu; j++) if (used[j] === k) f = 1;\n    if (!f) { used[nu] = k; nu++; }\n  }\n  es = es / n;\n  var s0 = 0, e0 = 0, zc = 0; for (i = 0; i < n; i++) s0 = Math.max(s0, Math.abs(xs[i])); s0 = s0 / 127;\n  for (i = 0; i < n; i++) { e0 += Math.abs(Math.round(xs[i] / s0) * s0 - xs[i]); if (qv[i] === 0 && Math.abs(xs[i]) > 0.01) zc++; }\n  e0 = e0 / n;\n  var oq = gone ? 0 : (big ? mag : Math.round(mag / step) * step), oe = Math.abs(oq - mag);\n  function r3(v) { return Math.round(v * 1000) / 1000; }\n  ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(0, 0, w, h);\n  var x0 = 40, pw = w * 0.66, top = 58, ph = h - 120, mid = top + ph / 2, sc = ph / 2 / 1.1;\n  function Y(v) { return mid - v * sc; }\n  ctx.fillStyle = \"#1d1a16\"; ctx.font = \"15px sans-serif\"; ctx.textAlign = \"left\";\n  ctx.fillText(\"paso = máx/127 = \" + r3(step) + \"     los 15 chicos usan \" + nu + \" de 255 niveles\", 14, 22);\n  var reg = zc > 0 ? zc + \" de 15 chicos ya valen 0 en 8 bits\" : (step > 0.05 ? \"niveles gruesos: los chicos pierden detalle\" : \"niveles finos: cada valor cabe\");\n  ctx.font = \"13px sans-serif\"; ctx.fillStyle = step > 0.05 ? \"#c4512c\" : \"#2e7d32\"; ctx.fillText(reg, 14, 42);\n  ctx.strokeStyle = \"#ddd3c3\"; ctx.lineWidth = 1;\n  var kmax = Math.floor(1.1 / step);\n  if (kmax <= 60) { for (k = -kmax; k <= kmax; k++) { ctx.beginPath(); ctx.moveTo(x0, Y(k * step)); ctx.lineTo(x0 + pw, Y(k * step)); ctx.stroke(); } }\n  else { ctx.fillStyle = \"#e9e2d5\"; ctx.fillRect(x0, top, pw, ph); ctx.fillStyle = \"#8a7f70\"; ctx.font = \"11px sans-serif\"; ctx.fillText(\"niveles tan juntos que no se ven\", x0 + 6, top + 14); }\n  ctx.strokeStyle = \"#b7aa9a\"; ctx.beginPath(); ctx.moveTo(x0, Y(0)); ctx.lineTo(x0 + pw, Y(0)); ctx.stroke();\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#6b6358\"; ctx.textAlign = \"right\";\n  ctx.fillText(\"+1\", x0 - 4, Y(1) + 4); ctx.fillText(\"0\", x0 - 4, Y(0) + 4); ctx.fillText(\"−1\", x0 - 4, Y(-1) + 4); ctx.textAlign = \"left\";\n  var gap = pw / n;\n  for (i = 0; i < n; i++) {\n    var cx = x0 + gap * (i + 0.5);\n    ctx.strokeStyle = \"#c4512c\"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(cx, Y(xs[i])); ctx.lineTo(cx, Y(qv[i])); ctx.stroke();\n    ctx.fillStyle = \"#9a8f80\"; ctx.beginPath(); ctx.arc(cx, Y(xs[i]), 4, 0, 2 * Math.PI); ctx.fill();\n    ctx.fillStyle = \"#1f4b99\"; ctx.beginPath(); ctx.arc(cx, Y(qv[i]), 4, 0, 2 * Math.PI); ctx.fill();\n  }\n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#1d1a16\";\n  ctx.fillText(\"error medio de los chicos: \" + r3(es) + \"   (\" + Math.round(es / e0) + \"× el error sin outlier)\", x0, top + ph + 22);\n  ctx.fillStyle = \"#6b6358\"; ctx.font = \"11px sans-serif\";\n  ctx.fillText(\"gris: valor real   azul: valor en 8 bits   coral: error   líneas: niveles\", x0, h - 8);\n  var bx = x0 + pw + 30, bw2 = w - bx - 16, by = top + ph, bh = ph, omax = 120;\n  function OY(v) { return by - v / omax * bh; }\n  ctx.strokeStyle = \"#cfc5b5\"; ctx.lineWidth = 1; ctx.strokeRect(bx, top, bw2, ph);\n  ctx.fillStyle = \"#1d1a16\"; ctx.font = \"12px sans-serif\"; ctx.fillText(\"el outlier (otra escala)\", bx, top - 6);\n  ctx.strokeStyle = \"#2e7d32\"; ctx.beginPath(); ctx.moveTo(bx, OY(6)); ctx.lineTo(bx + bw2, OY(6)); ctx.stroke();\n  ctx.fillStyle = \"#2e7d32\"; ctx.font = \"11px sans-serif\"; \n  ctx.fillStyle = \"#9a8f80\"; ctx.fillRect(bx + bw2 * 0.15, OY(mag), bw2 * 0.3, by - OY(mag));\n  ctx.fillStyle = big ? \"#2e7d32\" : \"#1f4b99\"; ctx.fillRect(bx + bw2 * 0.55, OY(oq), bw2 * 0.3, Math.max(2, by - OY(oq)));\n  ctx.globalAlpha = 0.85; ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(bx + 1, top + 1, bw2 - 2, mag > 20 ? 52 : 36); ctx.globalAlpha = 1;\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#1d1a16\"; ctx.fillText(\"real \" + mag, bx + 2, top + 14);\n  if (mag > 20) { ctx.fillStyle = \"#8a7f70\"; ctx.fillText(\"> 20x: más que el paper\", bx + 2, top + 46); }\n  var tag = gone ? \"tirado: error \" + mag : (big ? \"16 bits: exacto\" : \"8 bits: error \" + r3(oe));\n  ctx.fillStyle = gone ? \"#c4512c\" : (big ? \"#2e7d32\" : \"#1f4b99\"); ctx.fillText(tag, bx + 2, top + 30);\n  ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(bx + bw2 - 50, OY(6) + 2, 48, 13);\n  ctx.fillStyle = \"#2e7d32\"; ctx.textAlign = \"right\"; ctx.fillText(\"umbral 6\", bx + bw2 - 3, OY(6) + 12); ctx.textAlign = \"left\";\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "rope-shift",
      "topic": "rope",
      "title": "Desplazar los dos tokens no mueve q·k",
      "explain": "RoPE (Su et al., 2104.09864) gira q y k con la posición absoluta. En este juguete de tres pares, q·k es la suma de cosenos de (m−n): desplazar los dos el mismo tramo mueve las flechas y deja la recta plana. Aleja n de m y el producto cae; la marca «lejos» aparece cuando baja de 1. No es el RoPE de un modelo completo, solo tres frecuencias fijas.",
      "questions": [
        {
          "q": "Pon desplaza en 32. ¿q·k cambió?",
          "why": "las flechas giran y el punto corre sobre una recta plana"
        },
        {
          "q": "Pon n en 20, con m en 3. ¿Qué le pasa al producto?",
          "why": "la distancia m-n tumba q·k y sale la marca lejos"
        },
        {
          "q": "Mira la flecha de la izquierda y la de la derecha. ¿Cuál da más vueltas al desplazar?",
          "why": "la rápida cierra vueltas; la lenta casi no se mueve"
        },
        {
          "q": "Con desplaza en 32, ¿q·k compara las posiciones o la distancia m−n?",
          "why": "los dos giros se restan y queda m-n"
        }
      ],
      "controls": [
        {
          "id": "theta",
          "label": "desplaza",
          "min": 0,
          "max": 40,
          "value": 0,
          "step": 1
        },
        {
          "id": "m",
          "label": "posición m",
          "min": 0,
          "max": 20,
          "value": 3,
          "step": 1
        },
        {
          "id": "n",
          "label": "posición n",
          "min": 0,
          "max": 20,
          "value": 8,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, m = state.m + state.theta, n = state.n + state.theta;\n  var th = [1, 0.32, 0.1], qa = [0.4, 1.1, 2.1], ka = [1.5, 0.25, 2.5];\n  var i, s = 0, r = Math.min(h * 0.16, w / 11), dist = state.m - state.n;\n  function arrow(cx, cy, a, col) {\n    ctx.strokeStyle = col;\n    ctx.lineWidth = 2;\n    ctx.beginPath();\n    ctx.moveTo(cx, cy);\n    ctx.lineTo(cx + r * Math.cos(a), cy - r * Math.sin(a));\n    ctx.stroke();\n    ctx.fillStyle = col;\n    ctx.beginPath();\n    ctx.arc(cx + r * Math.cos(a), cy - r * Math.sin(a), 3, 0, 6.2832);\n    ctx.fill();\n  }\n  if (dist < 0) dist = -dist;\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  for (i = 0; i < 3; i++) {\n    var cx = w * (0.12 + 0.2 * i), cy = h * 0.30;\n    var aq = qa[i] + m * th[i], ak = ka[i] + n * th[i];\n    ctx.strokeStyle = \"#e0d5c6\";\n    ctx.lineWidth = 1;\n    ctx.beginPath();\n    ctx.arc(cx, cy, r, 0, 6.2832);\n    ctx.stroke();\n    arrow(cx, cy, aq, \"#c4512c\");\n    arrow(cx, cy, ak, \"#1f4b99\");\n    s = s + Math.cos(aq - ak);\n    ctx.fillStyle = \"#8a8175\";\n    ctx.font = \"12px sans-serif\";\n    ctx.fillText(i === 0 ? \"rapida\" : (i === 1 ? \"media\" : \"lenta\"), cx - 18, cy + r + 16);\n  }\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"16px sans-serif\";\n  ctx.fillText(\"q·k \" + Math.round(s * 100) / 100, w * 0.72, h * 0.12);\n  ctx.font = \"13px sans-serif\";\n  ctx.fillStyle = \"#5c564c\";\n  ctx.fillText(\"m-n \" + dist, w * 0.72, h * 0.12 + 20);\n  ctx.fillText(s < 1 ? \"lejos: el producto cae\" : \"cerca: se sostiene\", w * 0.72, h * 0.12 + 38);\n  ctx.fillText(\"desplazar no lo mueve\", w * 0.72, h * 0.12 + 56);\n  var gx = 28, gy = h * 0.62, gw = w - 48, gh = h * 0.26, k, v;\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"11px sans-serif\";\n  ctx.fillText(\"q·k contra el desplazamiento (recta plana)\", gx, gy - 4);\n  ctx.strokeStyle = \"#e0d5c6\";\n  ctx.strokeRect(gx, gy, gw, gh);\n  ctx.strokeStyle = \"#1d1a16\";\n  ctx.lineWidth = 1.5;\n  ctx.beginPath();\n  for (k = 0; k <= 40; k++) {\n    v = 0;\n    for (i = 0; i < 3; i++) v = v + Math.cos(qa[i] - ka[i] + (state.m - state.n) * th[i]);\n    if (k === 0) ctx.moveTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));\n    else ctx.lineTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));\n  }\n  ctx.stroke();\n  ctx.fillStyle = \"#c4512c\";\n  ctx.beginPath();\n  ctx.arc(gx + gw * state.theta / 40, gy + gh * (1 - (s + 3) / 6), 5, 0, 6.2832);\n  ctx.fill();\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "beam-trap",
      "topic": "beam",
      "title": "El haz ancho rescata el camino que empezó peor",
      "explain": "GNMT (Wu et al., 1609.08144) decodifica con beam search. En el abstract normalizan la longitud y penalizan la cobertura; este juguete no lo hace y no es una frase medida. «el» empieza en −0.15 y «el día» termina cerca de −2.3; «un gato» empieza peor y termina cerca de −0.6. Ancho 1 cae en la trampa. Ancho 2 lo rescata. Ancho 3 no cambia el ganador. La barra larga de la izquierda no es la frase mejor.",
      "questions": [
        {
          "q": "Baja el ancho a 1. ¿Qué frase queda?",
          "why": "el codicioso se queda con el día, que empezó mejor"
        },
        {
          "q": "En el ancho 2, ¿por qué gana un gato si un empezó peor?",
          "why": "el haz compara la frase completa, no el primer token"
        },
        {
          "q": "Sube el ancho a 3. ¿Cambia el ganador?",
          "why": "ya entra al haz y un gato sigue ganando"
        },
        {
          "q": "¿La barra más larga de la izquierda es la mejor frase?",
          "why": "no: el empieza mejor y termina peor"
        }
      ],
      "controls": [
        {
          "id": "width",
          "label": "ancho",
          "min": 1,
          "max": 3,
          "value": 2,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, width = Math.round(state.width);\n  var w1 = [\"el\", \"un\", \"ya\"];\n  var s1 = [-0.15, -0.55, -1.8];\n  var w2 = [[\"dia\", \"fin\", \"mar\"], [\"gato\", \"perro\", \"sol\"], [\"no\", \"va\", \"es\"]];\n  var s2 = [[-2.2, -2.5, -2.8], [-0.1, -1.1, -1.6], [-1, -1.2, -1.4]];\n  var order = [0, 1, 2], i, j, tmp, a, b, tot, best = -1000000, phrase = \"\", bi = 0;\n  for (i = 0; i < 3; i++) for (j = i + 1; j < 3; j++) if (s1[order[j]] > s1[order[i]]) {\n    tmp = order[i]; order[i] = order[j]; order[j] = tmp;\n  }\n  for (a = 0; a < width; a++) {\n    i = order[a];\n    for (b = 0; b < 3; b++) {\n      tot = s1[i] + s2[i][b];\n      if (tot > best) { best = tot; phrase = w1[i] + \" \" + w2[i][b]; bi = i; }\n    }\n  }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.font = \"12px sans-serif\";\n  ctx.fillStyle = \"#5c564c\";\n  ctx.fillText(\"primer token (empieza)\", 16, 18);\n  ctx.fillText(\"frase completa (termina)\", w * 0.46, 18);\n  for (a = 0; a < 3; a++) {\n    i = order[a];\n    var y = h * 0.16 + a * h * 0.20, kept = a < width, bestB = 0;\n    for (b = 1; b < 3; b++) if (s2[i][b] > s2[i][bestB]) bestB = b;\n    var total = s1[i] + s2[i][bestB];\n    var bw1 = (s1[i] + 2.2) / 2.2 * 78;\n    ctx.fillStyle = kept ? \"#1f4b99\" : \"#d5cbbd\";\n    ctx.fillRect(16, y, bw1, 18);\n    ctx.fillStyle = \"#1d1a16\";\n    ctx.fillText(w1[i] + \"  \" + s1[i], 22 + bw1, y + 14);\n    var bw2 = Math.max(8, (total + 3.2) / 3.2 * 70);\n    ctx.fillStyle = kept ? (i === bi ? \"#c4512c\" : \"#1f4b99\") : \"#d5cbbd\";\n    ctx.fillRect(w * 0.46, y, bw2, 18);\n    ctx.fillStyle = \"#1d1a16\";\n    ctx.fillText(w1[i] + \" \" + w2[i][bestB] + \"  \" + Math.round(total * 10) / 10, w * 0.46 + bw2 + 8, y + 14);\n  }\n  ctx.strokeStyle = \"#1d1a16\";\n  ctx.lineWidth = 1.5;\n  ctx.strokeRect(8, h * 0.12, w * 0.40, width * h * 0.20 + 8);\n  ctx.font = \"18px sans-serif\";\n  ctx.fillStyle = \"#1d1a16\";\n  if (width === 1) ctx.fillText(\"ancho 1 cae en \" + phrase, 16, h - 18);\n  else if (width === 2) ctx.fillText(\"ancho 2 rescata \" + phrase, 16, h - 18);\n  else ctx.fillText(\"ancho 3 no mejora: \" + phrase, 16, h - 18);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "grok-delay",
      "topic": "grok",
      "title": "La validación generaliza mucho después",
      "explain": "Power et al. 2201.02177: primero memoriza los ejemplos; generaliza «1000 times more» pasos después, y con menos datos todavía más tarde. Mueve datos: el salto coral se corre y el azul no. Eje y forma ilustrativos. El weight decay baja cuántos datos hacen falta, no este eje de pasos: no hay una curva que dibujar, por eso no es un control.",
      "questions": [
        {
          "q": "¿En el paso 42, por qué el entrenamiento ya está alto y la validación no?",
          "why": "memoriza pronto; generalizar va mucho después"
        },
        {
          "q": "¿Qué le pasa al salto coral si bajas datos de 0.4 a 0.2?",
          "why": "se sale del eje: con pocos datos no alcanza"
        },
        {
          "q": "¿La curva azul también se corre cuando hay menos datos?",
          "why": "no: el entrenamiento sigue igual de rápido"
        },
        {
          "q": "¿Este eje es la medición de 1000 veces más pasos?",
          "why": "no: el 1000x es del paper; el eje es ilustrativo"
        }
      ],
      "controls": [
        {
          "id": "step",
          "label": "paso",
          "min": 0,
          "max": 100,
          "value": 42,
          "step": 1
        },
        {
          "id": "data",
          "label": "datos",
          "min": 0.2,
          "max": 1,
          "value": 0.4,
          "step": 0.05
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, step = Math.round(state.step), data = state.data;\n  var N = 100, i, tr, va, jump, msg, L = 36, R = w * 0.72, T = 48, B = h * 0.78;\n  if (data < 0.2) data = 0.2;\n  jump = 24 / data;\n  function trainAt(s) { return 1 - Math.exp(-s / 8); }\n  function valAt(s) {\n    if (s < jump) return 0.12;\n    return 0.12 + (1 - Math.exp(-(s - jump) / 6)) * 0.86;\n  }\n  function X(v) { return L + (v / N) * (R - L); }\n  function Y(v) { return B - v * (B - T); }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  if (jump <= N) {\n    ctx.strokeStyle = \"#c4512c\";\n    ctx.lineWidth = 2;\n    ctx.beginPath();\n    ctx.moveTo(X(jump), T);\n    ctx.lineTo(X(jump), B);\n    ctx.stroke();\n    ctx.fillStyle = \"#c4512c\";\n    ctx.font = \"12px sans-serif\";\n    ctx.fillText(\"salto\", X(jump) - 14, T - 8);\n  }\n  ctx.strokeStyle = \"#1f4b99\";\n  ctx.lineWidth = 2.5;\n  ctx.beginPath();\n  for (i = 0; i <= N; i++) {\n    tr = trainAt(i);\n    if (i === 0) ctx.moveTo(X(i), Y(tr));\n    else ctx.lineTo(X(i), Y(tr));\n  }\n  ctx.stroke();\n  ctx.strokeStyle = \"#c4512c\";\n  ctx.beginPath();\n  for (i = 0; i <= N; i++) {\n    va = valAt(i);\n    if (i === 0) ctx.moveTo(X(i), Y(va));\n    else ctx.lineTo(X(i), Y(va));\n  }\n  ctx.stroke();\n  ctx.strokeStyle = \"#2e7d32\";\n  ctx.lineWidth = 2;\n  ctx.beginPath();\n  ctx.moveTo(X(step), T);\n  ctx.lineTo(X(step), B);\n  ctx.stroke();\n  tr = trainAt(step);\n  va = valAt(step);\n  msg = \"de pronto generaliza\";\n  if (va < 0.3) msg = jump > N ? \"con estos datos no alcanza\" : \"entrena ya, valida no\";\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"16px sans-serif\";\n  ctx.fillText(msg, 16, 24);\n  ctx.fillStyle = \"#8a8175\";\n  ctx.font = \"11px sans-serif\";\n  ctx.fillText(\"exactitud\", 8, T - 6);\n  ctx.fillText(\"paso, lineal\", R - 78, B + 16);\n  ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"memoriza primero\", R + 16, h * 0.20);\n  ctx.fillText(\"eje ilustrativo\", R + 16, h * 0.28);\n  ctx.fillText(\"paper: valida ~1000x\", R + 16, h * 0.36);\n  ctx.fillText(jump > N ? \"salto fuera del eje\" : \"salto en \" + Math.round(jump), R + 16, h * 0.48);\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"13px sans-serif\";\n  ctx.fillText(\"azul entrena  \" + Math.round(tr * 100) + \"%\", 16, h * 0.92);\n  ctx.fillStyle = \"#c4512c\";\n  ctx.fillText(\"coral valida  \" + Math.round(va * 100) + \"%\", w * 0.42, h * 0.92);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "denoise-strip",
      "topic": "noise_schedule",
      "title": "Ho disuelve el dibujo en mil pasos",
      "explain": "Ho 2006.11239, proceso directo: cada paso mete ruido, no limpia. x_t = √ᾱ x0 + √(1−ᾱ) ε, ᾱ producto de (1−β), β lineal de 0.0001 al beta final, en 1000 pasos. El ε pintado es un seno fijo, no la gaussiana. En t=500 la señal no es 50%: mira el número y sube el beta final.",
      "questions": [
        {
          "q": "¿Por qué en t=200 el plus sigue y la señal marca 81%?",
          "why": "recién va el producto de (1−β); todavía queda ᾱ"
        },
        {
          "q": "¿En t=500 queda la mitad de la señal?",
          "why": "no: el número del lienzo no es 50"
        },
        {
          "q": "¿Subir el beta final borra antes, en el mismo t?",
          "why": "el producto de (1−β) cae más rápido"
        },
        {
          "q": "¿Este dibujo es el modelo limpiando, o el proceso que ensucia?",
          "why": "el directo, que ensucia; limpiar es el inverso"
        }
      ],
      "controls": [
        {
          "id": "step",
          "label": "paso t",
          "min": 0,
          "max": 1000,
          "value": 200,
          "step": 20
        },
        {
          "id": "beta",
          "label": "beta final",
          "min": 0.005,
          "max": 0.05,
          "value": 0.02,
          "step": 0.001
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, step = Math.round(state.step), bT = state.beta;\n  var T = 1000, b1 = 0.0001, s, acc = 1, bs, ab = [];\n  ab[0] = 1;\n  for (s = 1; s <= T; s++) {\n    bs = b1 + (bT - b1) * (s - 1) / (T - 1);\n    acc = acc * (1 - bs);\n    ab[s] = acc;\n  }\n  function grid(x, y, cellpx, tt, hot) {\n    var i, j, bit, eps, sig, noi, v, n;\n    sig = Math.sqrt(ab[tt]);\n    noi = Math.sqrt(Math.max(0, 1 - ab[tt]));\n    for (i = 0; i < 8; i++) for (j = 0; j < 8; j++) {\n      bit = (i === 3 || i === 4 || j === 3 || j === 4) ? 1 : 0;\n      n = Math.sin(i * 12.9898 + j * 78.233) * 43758.5453;\n      eps = (n - Math.floor(n)) * 2 - 1;\n      v = sig * bit + noi * eps;\n      ctx.fillStyle = v > 0.45 ? \"#1f4b99\" : (v > 0.12 ? \"#e7a090\" : \"#efe6d8\");\n      ctx.fillRect(x + j * cellpx, y + i * cellpx, cellpx - 1, cellpx - 1);\n    }\n    if (hot) {\n      ctx.strokeStyle = \"#2e7d32\";\n      ctx.lineWidth = 2;\n      ctx.strokeRect(x - 2, y - 2, cellpx * 8 + 3, cellpx * 8 + 3);\n    }\n  }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  if (step < 0) step = 0;\n  if (step > T) step = T;\n  var sig = Math.sqrt(ab[step]);\n  var noi = Math.sqrt(Math.max(0, 1 - ab[step]));\n  var cell = Math.floor(Math.min((h - 48) / 8, (w * 0.46) / 8));\n  if (cell < 8) cell = 8;\n  grid(16, 24, cell, step, 0);\n  var rx = 32 + cell * 8;\n  var marks = [0, 200, 400, 700, 1000], f, fr, near = 0, dist = 9999;\n  var pitch = (w - rx - 16) / 5;\n  var scell = Math.floor(Math.min(pitch / 8, 14));\n  if (scell < 3) scell = 3;\n  for (f = 0; f < 5; f++) if (Math.abs(marks[f] - step) < dist) { dist = Math.abs(marks[f] - step); near = f; }\n  for (f = 0; f < 5; f++) {\n    fr = marks[f];\n    grid(rx + f * pitch, 28, scell, fr, f === near);\n    ctx.fillStyle = \"#5c564c\";\n    ctx.font = \"11px sans-serif\";\n    ctx.fillText(\"\" + fr, rx + f * pitch, 36 + scell * 8);\n  }\n  var ps = Math.round(sig * 100), pn = Math.round(noi * 100), s2 = Math.round(sig * sig * 100);\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"azul alto   rosa medio   crema bajo\", rx, h * 0.36);\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"15px sans-serif\";\n  ctx.fillText(\"t \" + step + \" / 1000\", rx, h * 0.44);\n  ctx.fillText(\"√a \" + ps + \"%    ruido \" + pn + \"%\", rx, h * 0.52);\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"13px sans-serif\";\n  ctx.fillText(\"cuadrados \" + s2 + \"+\" + (100 - s2) + \"=100\", rx, h * 0.60);\n  var mid = Math.round(Math.sqrt(ab[500]) * 100);\n  ctx.fillText(\"ensucia, no limpia; e fijo, no gaussiana\", rx, h * 0.68);\n  ctx.fillText(\"en t=500 queda \" + mid + \"%, no 50\", rx, h * 0.76);\n  ctx.fillStyle = \"#e4d6c4\";\n  ctx.fillRect(rx, h * 0.84, w - rx - 20, 8);\n  ctx.fillStyle = \"#1f4b99\";\n  ctx.fillRect(rx, h * 0.84, Math.max(2, (w - rx - 20) * sig), 8);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "kl-policy",
      "topic": "kl_rlhf",
      "title": "Sin el KL, ja se queda con el premio",
      "explain": "InstructGPT (Ouyang et al., 2203.02155, ec. 2) maximiza premio menos β por el log-ratio contra la supervisada; ellos usan β 0.02 y PPO. Estas barras son la forma cerrada de ese término, no esa corrida. El premio de cada token está bajo su nombre; ja vale 2.4 y en la referencia pesa 0.04. Con β 0.7, ja no pasa de la mitad. Bájalo de 0.4 y se queda el premio.",
      "questions": [
        {
          "q": "Baja beta a 0.2. ¿Qué token se queda la masa?",
          "why": "ja pasa del 50% y el KL deja de repartir"
        },
        {
          "q": "En beta 0.7, ¿por qué ja no se lo lleva todo si su premio es 2.4?",
          "why": "la referencia casi no dice ja y el KL lo cobra"
        },
        {
          "q": "Sube beta a 4. ¿A quién se parece la política?",
          "why": "a la referencia: ja vuelve a ser la barra chica"
        },
        {
          "q": "¿Estas barras son una corrida de PPO del paper?",
          "why": "no: son la forma cerrada, con premios de juguete"
        }
      ],
      "controls": [
        {
          "id": "beta",
          "label": "beta",
          "min": 0.12,
          "max": 4,
          "value": 0.7,
          "step": 0.02
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, beta = state.beta;\n  var name = [\"si\", \"ok\", \"eh\", \"bueno\", \"ja\"];\n  var ref = [0.42, 0.28, 0.16, 0.1, 0.04];\n  var reward = [0.1, 0.3, 0.5, 0.6, 2.4];\n  var raw = [], z = 0, i, p = [], kl = 0, ja;\n  for (i = 0; i < 5; i++) { raw[i] = ref[i] * Math.exp(reward[i] / beta); z = z + raw[i]; }\n  for (i = 0; i < 5; i++) { p[i] = raw[i] / z; kl = kl + p[i] * Math.log(p[i] / ref[i]); }\n  ja = Math.round(p[4] * 100);\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  var bw = (w - 40) / 5, bh = h * 0.26;\n  ctx.font = \"12px sans-serif\";\n  ctx.fillStyle = \"#5c564c\";\n  ctx.fillText(\"referencia\", 12, 18);\n  ctx.fillText(\"política  π ∝ ref · exp(premio / β)\", 12, h * 0.46);\n  for (i = 0; i < 5; i++) {\n    var x = 18 + i * bw;\n    ctx.fillStyle = \"#e4d6c4\";\n    ctx.fillRect(x, 28, bw - 12, bh);\n    ctx.fillStyle = \"#8a8175\";\n    ctx.fillRect(x, 28 + bh * (1 - ref[i] / 0.5), bw - 12, bh * ref[i] / 0.5);\n    ctx.fillStyle = \"#d9e3f5\";\n    ctx.fillRect(x, h * 0.48, bw - 12, bh);\n    ctx.fillStyle = i === 4 ? \"#c4512c\" : \"#1f4b99\";\n    ctx.fillRect(x, h * 0.48 + bh * (1 - Math.min(p[i], 0.95) / 0.95), bw - 12, bh * Math.min(p[i], 0.95) / 0.95);\n    ctx.fillStyle = i === 4 ? \"#c4512c\" : \"#1d1a16\";\n    ctx.fillText(name[i], x, h * 0.48 + bh + 16);\n    ctx.fillStyle = \"#8a8175\";\n    ctx.fillText(\"\" + reward[i], x, h * 0.48 + bh + 30);\n  }\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"14px sans-serif\";\n  ctx.fillText(\"KL \" + Math.round(kl * 100) / 100, w - 92, 18);\n  ctx.fillText(\"ja \" + ja + \"%\", w - 92, 38);\n  ctx.font = \"14px sans-serif\";\n  ctx.fillStyle = ja > 50 ? \"#c4512c\" : \"#1d1a16\";\n  var note = \"el KL todavía reparte\";\n  if (ja > 50) note = \"ja se queda el premio\";\n  else if (ja < 15) note = \"se parece a la referencia\";\n  ctx.fillText(note, w * 0.42, h * 0.46);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "moe-drop",
      "topic": "moe",
      "title": "El experto lleno deja tokens afuera",
      "explain": "Fedus et al. 2101.03961: cada token va al experto de mayor puntaje. Cupo = (tokens / expertos) × factor. Si se llena, «computation is skipped» y el token sigue por el atajo. Un factor grande deja hueco y gasta de más. Los puntajes son un ejemplo.",
      "questions": [
        {
          "q": "¿Por qué t2, t4 y t6 no entran a un experto con factor 1?",
          "why": "E0 ya va 2/2; el cupo es (8/4) por 1"
        },
        {
          "q": "¿A dónde van los que no cupieron, se pierden?",
          "why": "no: el lienzo los pone en el atajo, sin experto"
        },
        {
          "q": "¿k=2 devuelve a t2 y t4, o también deja a alguien nuevo en el atajo?",
          "why": "vuelven t2 y t4; t7 cae porque el segundo puesto llenó E3"
        },
        {
          "q": "¿Por qué un factor de 2 deja casillas vacías?",
          "why": "el cupo crece y sobra buffer, que también cuesta"
        }
      ],
      "controls": [
        {
          "id": "k",
          "label": "k",
          "min": 1,
          "max": 2,
          "value": 1,
          "step": 1
        },
        {
          "id": "factor",
          "label": "factor",
          "min": 0.5,
          "max": 2.5,
          "value": 1,
          "step": 0.25
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, top = Math.round(state.k), factor = state.factor;\n  var cap = Math.round((8 / 4) * factor);\n  var L = [2.2, 0.2, 0, -0.4, 1.8, 0.4, 0.1, -0.2, 1.6, 0.3, 0.5, 0, 0.2, 2, 0.1, 0.3, 1.4, 0.2, 0.6, -0.1, 0.1, 0.2, 1.8, 0.4, 1.1, 0.5, 0.2, 0.3, 0, 0.3, 0.2, 1.7];\n  var count = [0, 0, 0, 0], slot = [], drop = [], ti, e, k, b1, b2, got, di, fans = \"\";\n  if (cap < 1) cap = 1;\n  for (ti = 0; ti < 16; ti++) slot[ti] = -1;\n  for (ti = 0; ti < 8; ti++) {\n    b1 = 0; b2 = 1;\n    if (L[ti * 4 + 1] > L[ti * 4]) { b1 = 1; b2 = 0; }\n    for (e = 2; e < 4; e++) {\n      if (L[ti * 4 + e] > L[ti * 4 + b1]) { b2 = b1; b1 = e; }\n      else if (L[ti * 4 + e] > L[ti * 4 + b2]) b2 = e;\n    }\n    if (b1 === 0) fans = fans + \" t\" + ti;\n    got = 0;\n    var pick = [b1, b2];\n    for (k = 0; k < top; k++) {\n      e = pick[k];\n      if (count[e] < cap) { count[e] += 1; slot[ti * 2 + k] = e; got = 1; }\n    }\n    if (!got) drop.push(ti);\n  }\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  var used = [0, 0, 0, 0];\n  var colw = (w - 28) / 4;\n  var boxH = h * 0.58;\n  ctx.font = \"14px sans-serif\";\n  for (e = 0; e < 4; e++) {\n    var x = 12 + e * colw;\n    ctx.fillStyle = \"#1d1a16\";\n    ctx.fillText(\"E\" + e, x, h * 0.06);\n    ctx.fillStyle = count[e] >= cap ? \"#c4512c\" : \"#5c564c\";\n    ctx.fillText(count[e] + \"/\" + cap, x + 36, h * 0.06);\n    ctx.strokeStyle = \"#e0d5c6\";\n    ctx.strokeRect(x, h * 0.1, colw - 12, boxH);\n  }\n  var slotH = Math.min(28, (boxH - 16) / 6);\n  for (ti = 0; ti < 8; ti++) {\n    for (k = 0; k < top; k++) {\n      e = slot[ti * 2 + k];\n      if (e >= 0) {\n        var x = 18 + e * colw;\n        var y = h * 0.12 + used[e] * (slotH + 4);\n        used[e] += 1;\n        ctx.fillStyle = k === 0 ? \"#1f4b99\" : \"#b9c8e6\";\n        ctx.fillRect(x, y, colw - 28, slotH);\n        ctx.fillStyle = k === 0 ? \"#f6f3ec\" : \"#1d1a16\";\n        ctx.font = \"13px sans-serif\";\n        ctx.fillText(\"t\" + ti, x + 8, y + slotH * 0.72);\n      }\n    }\n  }\n  ctx.font = \"14px sans-serif\";\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.fillText(\"piden E0:\" + fans, 12, h * 0.76);\n  if (top > 1) ctx.fillText(\"claro: segunda\", w * 0.72, h * 0.76);\n  ctx.fillText(\"cupo (8/4) x \" + Math.round(factor * 100) / 100 + \" = \" + cap, 12, h * 0.84);\n  if (drop.length) {\n    ctx.fillStyle = \"#c4512c\";\n    ctx.fillText(\"atajo\", 12, h * 0.93);\n    for (di = 0; di < drop.length; di++) {\n      ctx.fillStyle = \"#c4512c\";\n      ctx.fillRect(64 + di * 44, h * 0.875, 36, 20);\n      ctx.fillStyle = \"#f6f3ec\";\n      ctx.fillText(\"t\" + drop[di], 70 + di * 44, h * 0.915);\n    }\n  } else {\n    ctx.fillStyle = \"#2e7d32\";\n    ctx.fillText(\"nadie al atajo; sobra hueco\", 12, h * 0.93);\n  }\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "online-softmax",
      "topic": "online_softmax",
      "title": "Softmax por bloques: tres números en memoria y el resultado exacto",
      "explain": "Los puntajes llegan por bloques. De todo lo visto solo se guardan el máximo m, la suma ℓ = Σe^(s−m) y la salida o (promedio pesado de los valores). Si un bloque trae un máximo mayor, lo guardado se multiplica por e^(m_viejo − m_nuevo) (en coral). Al leer todo, los pesos y o caen exactos sobre el softmax completo (contorno), con cualquier tamaño de bloque. Puntajes y valores: de juguete.",
      "questions": [
        {
          "q": "¿Cómo se calcula un softmax sin ver todos los puntajes?",
          "why": "Baja a 1 bloque leído: con m, ℓ y o ya hay un softmax parcial (verde), que se corrige al llegar más."
        },
        {
          "q": "¿Por qué se multiplica la suma vieja cuando aparece un máximo mayor?",
          "why": "Sube el puntaje tardío a 20: al llegar ese bloque el factor coral cae a casi 0, porque lo viejo se medía contra un máximo más chico."
        },
        {
          "q": "¿El resultado por bloques es aproximado?",
          "why": "Lee todos los bloques y cambia el tamaño de bloque: la diferencia impresa con el softmax completo es 0 siempre."
        },
        {
          "q": "¿Para qué restar el máximo?",
          "why": "Con el puntaje tardío en 30, e^30 ≈ 1e13 no cabe en fp16 (máx 65504). Restando m, todo queda entre 0 y 1."
        }
      ],
      "controls": [
        {
          "id": "blocks",
          "label": "bloques leídos",
          "min": 1,
          "max": 8,
          "value": 8,
          "step": 1
        },
        {
          "id": "lb",
          "label": "log2 tamaño de bloque",
          "min": 1,
          "max": 3,
          "value": 2,
          "step": 1
        },
        {
          "id": "late",
          "label": "puntaje tardío (pos. 13)",
          "min": 0,
          "max": 30,
          "value": 6,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, B = Math.pow(2, Math.round(state.lb)), n = 16, i, b;\n  var s = [1.2, 2.6, 0.4, 1.9, 3.1, 0.8, 2.2, 1.5, 0.3, 2.8, 1.1, 0.6, 2.0, 1.0, 1.7, 0.9], v = [0.2, 0.9, 0.1, 0.5, 0.7, 0.3, 0.8, 0.4, 0.6, 0.1, 0.9, 0.2, 0.5, 0.3, 0.7, 0.4];\n  s[12] = state.late;\n  var nb = n / B, nr = Math.min(Math.round(state.blocks), nb), seen = nr * B;\n  var M = -1e9, Z = 0, O = 0;\n  for (i = 0; i < n; i++) M = Math.max(M, s[i]);\n  for (i = 0; i < n; i++) { Z += Math.exp(s[i] - M); O += Math.exp(s[i] - M) * v[i]; }\n  O = O / Z;\n  var m = -1e9, l = 0, o = 0, fac = 1, lastfac = 1, jumped = -1;\n  for (b = 0; b < nr; b++) {\n    var mo = m, mb = -1e9;\n    for (i = b * B; i < b * B + B; i++) mb = Math.max(mb, s[i]);\n    m = Math.max(mo, mb);\n    fac = b === 0 ? 1 : Math.exp(mo - m);\n    if (b > 0 && fac < 0.999) jumped = b;\n    var lb2 = 0, ob = 0;\n    for (i = b * B; i < b * B + B; i++) { lb2 += Math.exp(s[i] - m); ob += Math.exp(s[i] - m) * v[i]; }\n    o = (o * l * fac + ob) / (l * fac + lb2);\n    l = l * fac + lb2; lastfac = fac;\n  }\n  function r3(x) { return Math.round(x * 1000) / 1000; }\n  ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(0, 0, w, h);\n  var x0 = 16, gw = w - 32, bw = gw / n, top = 30, sh = 70, smax = Math.max(4, state.late);\n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#1d1a16\"; ctx.textAlign = \"left\";\n  ctx.fillText(\"puntajes, en bloques de \" + B + \"   (leídos: \" + seen + \" de 16)\", x0, top - 10);\n  for (i = 0; i < n; i++) {\n    var bi = Math.floor(i / B), x = x0 + i * bw;\n    ctx.fillStyle = bi % 2 ? \"#ebe4d6\" : \"#f1ece2\"; ctx.fillRect(x, top, bw, sh);\n    if (bi === nr - 1) { ctx.fillStyle = \"#e6d3a8\"; ctx.fillRect(x, top, bw, sh); }\n    ctx.globalAlpha = i < seen ? 1 : 0.25;\n    ctx.fillStyle = i === 12 ? \"#c4512c\" : \"#1f4b99\";\n    var hh = Math.max(2, Math.min(s[i], smax) / smax * (sh - 6));\n    ctx.fillRect(x + 3, top + sh - hh, bw - 6, hh);\n    ctx.globalAlpha = 1;\n  }\n  var my = top + sh + 26;\n  ctx.fillStyle = \"#1d1a16\"; ctx.font = \"14px sans-serif\";\n  ctx.fillText(\"en memoria:   m = \" + r3(m) + \"     ℓ = \" + r3(l) + \"     o = \" + r3(o), x0, my);\n  ctx.font = \"13px sans-serif\";\n  if (nr > 1) {\n    ctx.fillStyle = lastfac < 0.999 ? \"#c4512c\" : \"#6b6358\";\n    ctx.fillText(lastfac < 0.999 ? \"último bloque: el máximo subió → lo guardado × e^(m_viejo − m) = \" + r3(lastfac) : \"último bloque: el máximo no cambió → factor 1\", x0, my + 20);\n  } else { ctx.fillStyle = \"#6b6358\"; ctx.fillText(\"primer bloque: m y ℓ salen solo de él\", x0, my + 20); }\n  ctx.fillStyle = state.late > 11 ? \"#c4512c\" : \"#6b6358\"; ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"sin restar m, el tardío daría e^\" + state.late + \" ≈ \" + (state.late > 11 ? \"1e\" + Math.round(state.late / Math.log(10)) + \": fp16 llega a 65504, se desborda\" : Math.round(Math.exp(state.late)) + \": cabe en fp16\"), x0, my + 38);\n  var py = h - 30, ph = h - my - 92, d = 0;\n  for (i = 0; i < n; i++) {\n    var x2 = x0 + i * bw, full = Math.exp(s[i] - M) / Z, part = i < seen ? Math.exp(s[i] - m) / l : 0;\n    ctx.fillStyle = \"#2e7d32\"; ctx.fillRect(x2 + 4, py - part * ph, bw - 8, Math.max(i < seen ? 2 : 0, part * ph));\n    ctx.strokeStyle = \"#6b6358\"; ctx.lineWidth = 1; ctx.strokeRect(x2 + 2, py - full * ph, bw - 4, Math.max(1, full * ph));\n    d = Math.max(d, Math.abs(full - part));\n  }\n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#1d1a16\";\n  ctx.fillText(\"pesos: verde = con lo leído; contorno = softmax de los 16\", x0, py - ph - 6);\n  var done = seen === n;\n  ctx.font = \"13px sans-serif\"; ctx.fillStyle = done ? \"#2e7d32\" : \"#c4512c\";\n  ctx.fillText(done ? \"exacto: diferencia máx = \" + r3(d) + \"   o = \" + r3(o) + \" = o completo \" + r3(O) : \"faltan bloques: el verde todavía no es el final\", x0, h - 10);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "spec-best",
      "topic": "spec_cost",
      "title": "Speculative decoding: cuántos tokens proponer",
      "explain": "El borrador propone γ tokens; cada uno sobrevive con probabilidad α hasta el primer rechazo, y el modelo grande siempre agrega uno. Verde: tokens por llamada al modelo grande, con techo 1/(1−α). Gris: costo de una ronda, 1 + γc. Azul: su cociente, el speedup del paper. Abajo de 1× es más lento. La salida tiene la misma distribución que el modelo grande solo. α = 0.75 es el de T5-small en EnDe; c es de juguete.",
      "questions": [
        {
          "q": "¿Por qué no proponer 50 tokens de borrador?",
          "why": "Mueve γ a 12: el verde ya tocó su techo 1/(1−α) y el gris sigue subiendo, así que el azul baja desde el punto óptimo."
        },
        {
          "q": "¿Qué es c y por qué importa tanto?",
          "why": "c es lo que cuesta un token del borrador, medido en llamadas al grande. Súbelo a 0.5: el óptimo se va a γ = 1 o 2."
        },
        {
          "q": "¿Puede salir más lento que no usarlo?",
          "why": "Pon α por debajo de c: toda la curva azul queda en la franja roja. El paper: si α > c, existe un γ que mejora."
        },
        {
          "q": "¿Cambia el texto que genera el modelo?",
          "why": "No: el paper acepta solo lo que deja la misma distribución que el modelo grande; cambia el tiempo, no la salida."
        }
      ],
      "controls": [
        {
          "id": "alpha",
          "label": "acuerdo α",
          "min": 0.05,
          "max": 0.95,
          "value": 0.75,
          "step": 0.01
        },
        {
          "id": "c",
          "label": "costo del borrador c",
          "min": 0.01,
          "max": 1,
          "value": 0.05,
          "step": 0.01
        },
        {
          "id": "gamma",
          "label": "tokens propuestos γ",
          "min": 1,
          "max": 12,
          "value": 7,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, a = state.alpha, c = state.c, G = Math.round(state.gamma), g;\n  function tok(g) { return (1 - Math.pow(a, g + 1)) / (1 - a); }\n  function cost(g) { return 1 + g * c; }\n  function spd(g) { return tok(g) / cost(g); }\n  var best = 1; for (g = 1; g <= 12; g++) if (tok(g) / cost(g) > tok(best) / cost(best)) best = g;\n  function r2(v) { return Math.round(v * 100) / 100; }\n  var x0 = 48, y0 = h - 42, gw = w * 0.6, gh = h - 92, top = y0 - gh, ymax = 6;\n  function X(g) { return x0 + g / 12 * gw; }\n  function Y(v) { return y0 - Math.min(v, ymax) / ymax * gh; }\n  ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(0, 0, w, h);\n  ctx.fillStyle = \"#f3dcd3\"; ctx.fillRect(x0, Y(1), gw, y0 - Y(1));\n  ctx.fillStyle = \"#c4512c\"; ctx.font = \"11px sans-serif\"; ctx.textAlign = \"left\"; ctx.fillText(\"debajo de 1×: más lento\", x0 + 4, y0 - 6);\n  ctx.strokeStyle = \"#cfc5b5\"; ctx.lineWidth = 1; ctx.strokeRect(x0, top, gw, gh);\n  ctx.fillStyle = \"#6b6358\"; ctx.textAlign = \"right\";\n  for (g = 0; g <= ymax; g += 1) { ctx.fillText(g + \"×\", x0 - 4, Y(g) + 4); }\n  ctx.textAlign = \"center\"; for (g = 0; g <= 12; g += 2) ctx.fillText(\"\" + g, X(g), y0 + 14);\n  ctx.fillText(\"tokens propuestos γ\", x0 + gw / 2, y0 + 30); ctx.textAlign = \"left\";\n  var cap = 1 / (1 - a);\n  if (cap < ymax) { ctx.strokeStyle = \"#2e7d32\"; ctx.lineWidth = 1; for (g = 0; g < 12; g += 0.5) { ctx.beginPath(); ctx.moveTo(X(g), Y(cap)); ctx.lineTo(X(g + 0.25), Y(cap)); ctx.stroke(); }\n    ctx.fillStyle = \"#2e7d32\"; ctx.fillText(\"techo 1/(1−α) = \" + r2(cap), X(0.3), Y(cap) - 4); }\n  function curve(f, col, lw) { ctx.strokeStyle = col; ctx.lineWidth = lw; ctx.beginPath(); for (g = 0; g <= 12; g++) { if (g === 0) ctx.moveTo(X(g), Y(f(g))); else ctx.lineTo(X(g), Y(f(g))); } ctx.stroke(); }\n  curve(tok, \"#2e7d32\", 1.5); curve(cost, \"#9a8f80\", 1.5);\n  curve(spd, \"#1f4b99\", 3);\n  ctx.fillStyle = \"#2e7d32\"; ctx.beginPath(); ctx.arc(X(best), Y(tok(best) / cost(best)), 7, 0, 2 * Math.PI); ctx.fill();\n  ctx.strokeStyle = \"#1d1a16\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(X(G), top); ctx.lineTo(X(G), y0); ctx.stroke();\n  ctx.fillStyle = \"#1d1a16\"; ctx.beginPath(); ctx.arc(X(G), Y(tok(G) / cost(G)), 4, 0, 2 * Math.PI); ctx.fill();\n  ctx.font = \"15px sans-serif\"; ctx.fillStyle = \"#1d1a16\";\n  if (spd(best) > 1) ctx.fillText(\"mejor γ = \" + best + \"  →  \" + r2(spd(best)) + \"× más rápido\", x0, 22);\n  else { ctx.fillStyle = \"#c4512c\"; ctx.fillText(\"ningún γ gana: mejor no especular (γ = 0, 1×)\", x0, 22); }\n  var lx = x0 + gw + 22; ctx.font = \"13px sans-serif\";\n  ctx.fillText(\"tu γ = \" + G, lx, top + 8);\n  ctx.fillStyle = \"#2e7d32\"; ctx.fillText(\"tokens por llamada: \" + r2(tok(G)), lx, top + 32);\n  ctx.fillStyle = \"#6b6358\"; ctx.font = \"11px sans-serif\"; ctx.fillText(\"(\" + r2(tok(G) - 1) + \" del borrador + 1 del grande)\", lx, top + 48);\n  ctx.font = \"13px sans-serif\"; ctx.fillStyle = \"#9a8f80\"; ctx.fillText(\"costo de la ronda: \" + r2(cost(G)), lx, top + 72);\n  ctx.fillStyle = \"#6b6358\"; ctx.font = \"11px sans-serif\"; ctx.fillText(\"(1 llamada + \" + G + \" × \" + r2(c) + \")\", lx, top + 88);\n  var sp = tok(G) / cost(G);\n  ctx.font = \"15px sans-serif\"; ctx.fillStyle = sp < 1 ? \"#c4512c\" : \"#1f4b99\"; ctx.fillText(\"speedup: \" + r2(sp) + \"×\", lx, top + 118);\n  ctx.font = \"12px sans-serif\";\n  ctx.fillStyle = a > c ? \"#2e7d32\" : \"#c4512c\";\n  ctx.fillText(a > c ? \"α > c: sí hay un γ que gana\" : \"α ≤ c: ningún γ gana\", lx, top + 148);\n  if (G !== best) { ctx.fillStyle = \"#6b6358\"; ctx.fillText(G > best ? \"te pasaste: el gris crece más\" : \"te quedaste corto\", lx, top + 168); ctx.fillText(\"que el verde\", lx, top + 184); }\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "chinchilla",
      "topic": "chinchilla",
      "title": "Con el mismo cómputo, ¿modelo más grande o más datos?",
      "explain": "Pérdida ajustada del paper: L = 1.69 + 406.4/N^0.34 + 410.7/D^0.28, con cómputo C ≈ 6ND. Izquierda: con C fijo, más parámetros N dejan menos tokens D; la curva tiene un fondo (verde). Derecha: cómo crecen el N y el D óptimos con C, casi al mismo ritmo. El punto negro es tu modelo. Gopher (280B, 300B tokens) y Chinchilla (70B, 1.4T) usaron el mismo C; sus pérdidas aquí salen del ajuste, no de medirlas.",
      "questions": [
        {
          "q": "Con más cómputo, ¿crezco el modelo o los datos?",
          "why": "Mira la derecha y mueve C: las rectas de N* y D* suben casi paralelas. El paper: escalar los dos en igual proporción."
        },
        {
          "q": "¿Por qué hay un mejor tamaño para un cómputo fijo?",
          "why": "A la izquierda del fondo el modelo es chico; a la derecha le faltan tokens. Mueve tu N lejos del verde y mira cuánto sube la pérdida."
        },
        {
          "q": "¿Gopher estaba demasiado grande?",
          "why": "Con C en el de Gopher, pon tu N en 280B: queda a la derecha del fondo. 70B (Chinchilla) cae más cerca del óptimo."
        },
        {
          "q": "¿La pérdida baja a cero con cómputo infinito?",
          "why": "No: la línea punteada E = 1.69 es el piso del ajuste. Sube C a 1e25 y la curva se acerca, pero no lo cruza."
        }
      ],
      "controls": [
        {
          "id": "logc",
          "label": "log10 cómputo C (FLOPs)",
          "min": 19,
          "max": 25,
          "value": 23.7,
          "step": 0.1
        },
        {
          "id": "logn",
          "label": "log10 tu modelo N",
          "min": 7,
          "max": 12.5,
          "value": 11.45,
          "step": 0.05
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, C = Math.pow(10, state.logc), E = 1.69, A = 406.4, B = 410.7, al = 0.34, be = 0.28;\n  var G = Math.pow(al * A / (be * B), 1 / (al + be)), a = be / (al + be), b = al / (al + be), k;\n  function L(n) { var d = C / (6 * n); return E + A / Math.pow(n, al) + B / Math.pow(d, be); }\n  function lg(v) { return Math.log(v) / Math.log(10); }\n  function sci(v) { var e = Math.floor(lg(v)); return Math.round(v / Math.pow(10, e) * 10) / 10 + \"e\" + e; }\n  function r3(v) { return Math.round(v * 1000) / 1000; }\n  var Nopt = G * Math.pow(C / 6, a), Dopt = Math.pow(C / 6, b) / G, Nme = Math.pow(10, state.logn), Dme = C / (6 * Nme);\n  ctx.fillStyle = \"#f6f3ec\"; ctx.fillRect(0, 0, w, h);\n  var x0 = 52, y0 = h - 62, gw = w * 0.5, gh = h - 124, top = y0 - gh, nlo = 7, nhi = 12.5, lo = 1.6, hi = 4.2;\n  function X(ln) { return x0 + (ln - nlo) / (nhi - nlo) * gw; }\n  function Y(v) { return y0 - (v - lo) / (hi - lo) * gh; }\n  ctx.strokeStyle = \"#cfc5b5\"; ctx.lineWidth = 1; ctx.strokeRect(x0, top, gw, gh);\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#6b6358\"; ctx.textAlign = \"center\";\n  for (k = 7; k <= 12; k++) ctx.fillText(\"1e\" + k, X(k), y0 + 14);\n  ctx.fillText(\"parámetros N (log)\", x0 + gw / 2, y0 + 28);\n  ctx.textAlign = \"right\"; for (k = 2; k <= 4; k++) ctx.fillText(\"\" + k, x0 - 4, Y(k) + 4);\n  ctx.save(); ctx.translate(14, top + gh / 2 + 20); ctx.rotate(-Math.PI / 2); ctx.textAlign = \"left\"; ctx.fillText(\"pérdida\", 0, 0); ctx.restore();\n  ctx.textAlign = \"left\";\n  ctx.strokeStyle = \"#9a8f80\"; for (k = 0; k < 40; k++) { ctx.beginPath(); ctx.moveTo(x0 + k * gw / 40, Y(E)); ctx.lineTo(x0 + (k + 0.5) * gw / 40, Y(E)); ctx.stroke(); }\n  ctx.fillStyle = \"#8a7f70\"; ctx.fillText(\"piso E = 1.69\", x0 + 6, Y(E) - 4);\n  ctx.strokeStyle = \"#1f4b99\"; ctx.lineWidth = 2.5; ctx.beginPath();\n  var on = false;\n  for (k = 0; k <= 160; k++) { var ln = nlo + (nhi - nlo) * k / 160, v = L(Math.pow(10, ln));\n    if (v < hi) { if (!on) { ctx.moveTo(X(ln), Y(v)); on = true; } else ctx.lineTo(X(ln), Y(v)); } else on = false; }\n  ctx.stroke();\n  ctx.font = \"11px sans-serif\"; ctx.fillStyle = \"#6b6358\";\n  ctx.fillText(\"← modelo chico\", x0 + 4, top + 14); ctx.textAlign = \"right\"; ctx.fillText(\"pocos tokens →\", x0 + gw - 4, top + 14); ctx.textAlign = \"left\";\n  var refs = [[lg(7e10), \"70B\"], [lg(2.8e11), \"280B\"]];\n  for (k = 0; k < 2; k++) { var rv = L(Math.pow(10, refs[k][0])); if (rv < hi) {\n    ctx.strokeStyle = \"#8a7f70\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(X(refs[k][0]), Y(rv) - 8); ctx.lineTo(X(refs[k][0]), Y(rv) + 8); ctx.stroke();\n    ctx.fillStyle = \"#8a7f70\"; ctx.fillText(refs[k][1], X(refs[k][0]) - 10, Y(rv) + 20); } }\n  if (L(Nopt) < hi) { ctx.fillStyle = \"#2e7d32\"; ctx.beginPath(); ctx.arc(X(lg(Nopt)), Y(L(Nopt)), 7, 0, 2 * Math.PI); ctx.fill(); }\n  var lme = L(Nme);\n  if (lme < hi) { ctx.fillStyle = \"#1d1a16\"; ctx.beginPath(); ctx.arc(X(state.logn), Y(lme), 5, 0, 2 * Math.PI); ctx.fill(); }\n  ctx.font = \"14px sans-serif\"; ctx.fillStyle = \"#1d1a16\";\n  ctx.fillText(\"C = \" + sci(C) + \" FLOPs\", x0, 20);\n  ctx.fillStyle = \"#2e7d32\"; ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"óptimo: N* = \" + sci(Nopt) + \", D* = \" + sci(Dopt) + \" tokens (\" + Math.round(Dopt / Nopt) + \" por parámetro)\", x0, 38);\n  var rx = x0 + gw + 60, rw = w - rx - 14, ry0 = y0, rh = gh, clo = 19, chi = 25, vlo = 7, vhi = 14;\n  function RX(lc) { return rx + (lc - clo) / (chi - clo) * rw; }\n  function RY(lv) { return ry0 - (lv - vlo) / (vhi - vlo) * rh; }\n  ctx.strokeStyle = \"#cfc5b5\"; ctx.lineWidth = 1; ctx.strokeRect(rx, top, rw, rh);\n  ctx.fillStyle = \"#6b6358\"; ctx.font = \"11px sans-serif\"; ctx.textAlign = \"center\";\n  ctx.fillText(\"1e19\", RX(19), ry0 + 14); ctx.fillText(\"1e22\", RX(22), ry0 + 14); ctx.fillText(\"1e25\", RX(25), ry0 + 14);\n  ctx.fillText(\"cómputo C\", rx + rw / 2, ry0 + 28);\n  ctx.textAlign = \"right\"; ctx.fillText(\"1e7\", rx - 3, RY(7) + 4); ctx.fillText(\"1e14\", rx - 3, RY(14) + 4); ctx.textAlign = \"left\";\n  function line(f, col, label) { ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.beginPath();\n    ctx.moveTo(RX(clo), RY(lg(f(Math.pow(10, clo))))); ctx.lineTo(RX(chi), RY(lg(f(Math.pow(10, chi))))); ctx.stroke();\n    ctx.fillStyle = col; ctx.textAlign = \"right\"; ctx.fillText(label, RX(chi) - 4, RY(lg(f(Math.pow(10, chi)))) + (col === \"#c4512c\" ? -6 : 14)); ctx.textAlign = \"left\"; }\n  function fN(c) { return G * Math.pow(c / 6, a); }\n  function fD(c) { return Math.pow(c / 6, b) / G; }\n  line(fD, \"#c4512c\", \"D* tokens\"); line(fN, \"#2e7d32\", \"N* parámetros\");\n  ctx.strokeStyle = \"#1d1a16\"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(RX(state.logc), top); ctx.lineTo(RX(state.logc), ry0); ctx.stroke();\n  ctx.fillStyle = \"#1d1a16\"; ctx.font = \"12px sans-serif\"; ctx.fillText(\"óptimo vs cómputo\", rx, top - 20);\n  ctx.fillStyle = \"#6b6358\"; ctx.font = \"11px sans-serif\"; ctx.fillText(\"pendientes \" + Math.round(a * 100) / 100 + \" / \" + Math.round(b * 100) / 100 + \" (paper 0.46/0.54)\", rx, top - 6);\n  ctx.font = \"12px sans-serif\"; ctx.fillStyle = \"#1d1a16\";\n  var gap = lme - L(Nopt);\n  ctx.fillText(\"tu modelo: N = \" + sci(Nme) + \", D = \" + sci(Dme) + \" → pérdida \" + r3(lme) + (gap > 0.0005 ? \"  (+\" + r3(gap) + \" sobre el óptimo)\" : \"  (en el óptimo)\"), x0, h - 8);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "pe-sincos",
      "topic": "positional_encoding",
      "title": "Lo cercano se parece: el pico cae en p",
      "explain": "El encoding del Transformer (Vaswani et al., 1706.03762) es seno de pos/10000^(2i/d) y el coseno en la impar. El paper lo plantea como hipótesis: lo cercano se parece porque el producto depende de la diferencia. En p vale 1 y a 4 pasos sigue alto con la base 10000. La fila 0 no depende de la base. Bájala de 100 y el pico se angosta. La curva es ese producto, no una medición.",
      "questions": [
        {
          "q": "Mueve la posición. ¿El pico de abajo la sigue?",
          "why": "el parecido vale 1 en p y cae al alejarse"
        },
        {
          "q": "Baja la base a 20. ¿Qué le pasa a las ondas de abajo y al pico?",
          "why": "se aceleran y el parecido a 4 pasos se desploma"
        },
        {
          "q": "¿La fila marcada 0 fija cambia cuando mueves la base?",
          "why": "no: su frecuencia es 1 para cualquier base"
        },
        {
          "q": "Con la base en 10000, ¿por qué a 4 pasos el parecido sigue en 0.75 si las ondas oscilan?",
          "why": "el producto depende de la diferencia, no de la posición suelta"
        }
      ],
      "controls": [
        {
          "id": "base",
          "label": "base",
          "min": 20,
          "max": 100000,
          "value": 10000,
          "step": 20
        },
        {
          "id": "pos",
          "label": "posición",
          "min": 0,
          "max": 60,
          "value": 18,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, base = state.base, p = state.pos, d = 64, N = 64;\n  var rows = [0, 4, 10, 16], r, i, q, y0, y, f, rh, peak, near;\n  function X(q) { return 36 + (q / N) * (w - 52); }\n  function freq(k) { return 1 / Math.pow(base, (2 * k) / d); }\n  function sim(a, b) {\n    var acc = 0, k, fr;\n    for (k = 0; k < d / 2; k++) {\n      fr = freq(k);\n      acc = acc + Math.sin(a * fr) * Math.sin(b * fr) + Math.cos(a * fr) * Math.cos(b * fr);\n    }\n    return acc / (d / 2);\n  }\n  peak = sim(p, p);\n  near = sim(p, p + 4);\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.font = \"12px sans-serif\";\n  ctx.fillStyle = \"#1f4b99\";\n  ctx.fillText(\"seno\", w - 110, 14);\n  ctx.fillStyle = \"#c4512c\";\n  ctx.fillText(\"coseno\", w - 62, 14);\n  rh = (h * 0.52) / rows.length;\n  for (r = 0; r < rows.length; r++) {\n    y0 = 22 + r * rh + rh * 0.55;\n    f = freq(rows[r]);\n    ctx.font = \"11px sans-serif\";\n    ctx.fillStyle = \"#8a8175\";\n    ctx.fillText(rows[r] === 0 ? \"0 fija\" : \"\" + rows[r], 2, y0 + 3);\n    ctx.lineWidth = 1.5;\n    ctx.strokeStyle = \"#1f4b99\";\n    ctx.beginPath();\n    for (i = 0; i <= N; i++) {\n      y = y0 - Math.sin(i * f) * rh * 0.32;\n      if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);\n    }\n    ctx.stroke();\n    ctx.lineWidth = 1;\n    ctx.strokeStyle = \"#c4512c\";\n    ctx.beginPath();\n    for (i = 0; i <= N; i++) {\n      y = y0 - Math.cos(i * f) * rh * 0.32;\n      if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);\n    }\n    ctx.stroke();\n    ctx.fillStyle = \"#1f4b99\";\n    ctx.beginPath();\n    ctx.arc(X(p), y0 - Math.sin(p * f) * rh * 0.32, 3, 0, 6.2832);\n    ctx.fill();\n  }\n  ctx.strokeStyle = \"#1d1a16\";\n  ctx.lineWidth = 1;\n  ctx.beginPath();\n  ctx.moveTo(X(p), 18);\n  ctx.lineTo(X(p), h * 0.56);\n  ctx.stroke();\n  var sy = h * 0.64, sh = h * 0.22;\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"parecido \" + Math.round(peak * 100) / 100 + \" en p,  \" + Math.round(near * 100) / 100 + \" a 4 pasos\", 8, sy - 2);\n  ctx.fillStyle = base < 100 ? \"#c4512c\" : \"#5c564c\";\n  ctx.fillText(base < 100 ? \"base chica: el pico se angosta\" : \"base 10000: pico ancho\", w * 0.55, sy - 2);\n  ctx.strokeStyle = \"#1d1a16\";\n  ctx.lineWidth = 1.6;\n  ctx.beginPath();\n  for (i = 0; i <= N; i++) {\n    y = sy + 8 + sh - ((sim(p, i) + 0.15) / 1.3) * sh;\n    if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);\n  }\n  ctx.stroke();\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "resid-stream",
      "topic": "residual",
      "title": "El atajo se lleva el token de capa en capa",
      "explain": "He et al. 1512.03385: y = F(x) + x. El atajo copia la entrada y la capa escribe el cambio. El control es solo 0 o 1: «identity shortcuts are never closed». En 0 ves la red plana, que entrena peor. El tablero y el % son un ejemplo, no ImageNet. Contorno coral: la entrada.",
      "questions": [
        {
          "q": "¿Por qué el contorno coral sigue en L4 si cada capa escribe algo?",
          "why": "escribe el cambio; la entrada se suma, no se reemplaza"
        },
        {
          "q": "¿Qué se apaga si pones el atajo en 0?",
          "why": "la red plana: las dos filas de la entrada"
        },
        {
          "q": "¿Las filas nuevas son la entrada o lo que escribió la capa?",
          "why": "lo que escribió la capa; la entrada es el contorno"
        },
        {
          "q": "¿El 100% es el error del paper en ImageNet?",
          "why": "no: es cuánto del token de este ejemplo sigue ahí"
        }
      ],
      "controls": [
        {
          "id": "depth",
          "label": "capa",
          "min": 0,
          "max": 4,
          "value": 4,
          "step": 1
        },
        {
          "id": "skip",
          "label": "atajo",
          "min": 0,
          "max": 1,
          "value": 1,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, depth = Math.round(state.depth), skip = state.skip;\n  var e = [1, 0.85, 0.25, 0, 0, 0, 0, 0];\n  var D = [\n    0, 0, 0.15, 0.8, 0.1, 0, 0, 0,\n    0, 0, 0, 0, 0.55, 0.7, 0, 0,\n    0, 0, 0, 0, 0, 0.15, 0.75, 0.1,\n    0, 0, 0, 0, 0, 0, 0.1, 0.65\n  ];\n  var cur = [], i, layer, v, x, y;\n  for (i = 0; i < 8; i++) cur[i] = e[i];\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  ctx.font = \"11px sans-serif\";\n  ctx.fillStyle = \"#8a8175\";\n  ctx.fillText(\"fila = dim del token\", 8, 26);\n  var pitch = Math.min(72, (w * 0.58) / 5);\n  var cw = pitch - 8, ch = (h * 0.7) / 8;\n  function paint(col) {\n    for (i = 0; i < 8; i++) {\n      v = cur[i];\n      if (v < 0) v = 0;\n      x = 16 + col * pitch;\n      y = h * 0.08 + i * ch;\n      ctx.fillStyle = v > 0.66 ? \"#1f4b99\" : (v > 0.28 ? \"#7ea0d0\" : (v > 0.06 ? \"#d9e3f5\" : \"#efe6d8\"));\n      ctx.fillRect(x, y, cw, ch - 3);\n      if (i < 2 && cur[i] > 0.2) {\n        ctx.strokeStyle = \"#c4512c\";\n        ctx.lineWidth = 2;\n        ctx.strokeRect(x, y, cw, ch - 3);\n      }\n    }\n    ctx.fillStyle = \"#5c564c\";\n    ctx.font = \"12px sans-serif\";\n    ctx.fillText(col === 0 ? \"emb\" : \"L\" + col, 16 + col * pitch, h * 0.08 + 8 * ch + 16);\n  }\n  paint(0);\n  for (layer = 0; layer < depth; layer++) {\n    for (i = 0; i < 8; i++) cur[i] = skip * cur[i] + D[layer * 8 + i];\n    paint(layer + 1);\n  }\n  var left = depth === 0 ? 100 : Math.round(100 * Math.pow(skip, depth));\n  var tx = 28 + 5 * pitch;\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"16px sans-serif\";\n  ctx.fillText(\"queda \" + left + \"% del token\", tx, h * 0.22);\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"13px sans-serif\";\n  ctx.fillText(skip > 0.5 ? \"y = x + cambio\" : \"red plana, sin suma\", tx, h * 0.32);\n  ctx.fillText(skip > 0.5 ? \"el atajo lo conserva\" : \"sin atajo se apaga\", tx, h * 0.4);\n  ctx.fillText(\"contorno coral: entrada\", tx, h * 0.66);\n  ctx.fillText(\"0 o 1: nunca se cierra\", tx, h * 0.74);\n  ctx.fillText(\"azul lleno = valor alto\", tx, h * 0.82);\n  ctx.fillStyle = \"#e4d6c4\";\n  ctx.fillRect(tx, h * 0.46, w - tx - 20, 14);\n  ctx.fillStyle = left > 40 ? \"#2e7d32\" : \"#c4512c\";\n  ctx.fillRect(tx, h * 0.46, Math.max(2, (w - tx - 20) * left / 100), 14);\n  ctx.fillStyle = \"#5c564c\";\n  ctx.fillText(\"atajo \" + Math.round(skip * 100) / 100, tx, h * 0.58);\n}"
    }
  },
  {
    "source": "round",
    "widget": {
      "id": "kv-grow",
      "topic": "gqa",
      "title": "El cache crece con el texto y con los grupos",
      "explain": "Ainslie et al. 2305.13245: GQA comparte K y V por grupo, «interpolating between multi-head and multi-query». MHA es 8 grupos y MQA es 1. Cache = capas × tokens × grupos × 2; las cabezas que preguntan no cuentan. El cupo y las 4 capas son de juguete, no una GPU.",
      "questions": [
        {
          "q": "¿Por qué 12 tokens y 8 grupos pasan el cupo?",
          "why": "4 x 12 x 8 x 2 = 768, y la raya está en 256"
        },
        {
          "q": "¿Qué baja si pones 1 grupo: el texto o las copias de K y V?",
          "why": "las copias; el texto sigue en 12 tokens"
        },
        {
          "q": "¿MQA y MHA son los extremos de este control?",
          "why": "sí: 1 grupo es MQA y 8 es MHA"
        },
        {
          "q": "¿La raya del cupo es la memoria de una GPU?",
          "why": "no: es un cupo de juguete para ver cuándo se pasa"
        }
      ],
      "controls": [
        {
          "id": "len",
          "label": "tokens",
          "min": 1,
          "max": 24,
          "value": 12,
          "step": 1
        },
        {
          "id": "kv",
          "label": "grupos KV",
          "min": 1,
          "max": 8,
          "value": 8,
          "step": 1
        }
      ],
      "draw": "function draw(ctx, state, t) {\n  var w = state.w, h = state.h, len = Math.round(state.len), heads = Math.round(state.kv);\n  var layers = 4, cells = layers * len * heads * 2, budget = 256, cap = 1536;\n  var layer, tok, x, y, bh;\n  ctx.clearRect(0, 0, w, h);\n  ctx.fillStyle = \"#f6f3ec\";\n  ctx.fillRect(0, 0, w, h);\n  var rowH = h * 0.135;\n  ctx.font = \"13px sans-serif\";\n  ctx.fillStyle = \"#8a8175\";\n  for (layer = 0; layer < layers; layer++) ctx.fillText(\"L\" + (layer + 1), 8, h * 0.1 + layer * rowH);\n  var cw = Math.min(22, (w - 56) / len - 2);\n  if (cw < 4) cw = 4;\n  for (layer = 0; layer < layers; layer++) {\n    y = h * 0.04 + layer * rowH;\n    for (tok = 0; tok < len; tok++) {\n      x = 36 + tok * (cw + 3);\n      bh = 4 + heads * rowH * 0.1;\n      if (bh > rowH * 0.85) bh = rowH * 0.85;\n      ctx.fillStyle = \"#1f4b99\";\n      ctx.fillRect(x, y + rowH * 0.7 - bh, cw, bh * 0.55);\n      ctx.fillStyle = \"#c4512c\";\n      ctx.fillRect(x, y + rowH * 0.7 - bh * 0.45, cw, bh * 0.45);\n    }\n  }\n  var regime = heads <= 1 ? \"MQA\" : (heads >= 8 ? \"MHA\" : \"GQA\");\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"15px sans-serif\";\n  ctx.fillText(\"8 queries comparten \" + heads + (heads === 1 ? \" grupo KV\" : \" grupos KV\"), 28, h * 0.62);\n  ctx.fillText(regime + \"   4 x \" + len + \" x \" + heads + \" x 2 = \" + cells, 28, h * 0.70);\n  ctx.fillStyle = \"#e4d6c4\";\n  ctx.fillRect(28, h * 0.76, w - 48, 12);\n  var mw = (w - 48) * cells / cap;\n  if (mw > w - 48) mw = w - 48;\n  ctx.fillStyle = cells > budget ? \"#c4512c\" : \"#2e7d32\";\n  ctx.fillRect(28, h * 0.76, Math.max(2, mw), 12);\n  var bx = 28 + (w - 48) * budget / cap;\n  ctx.strokeStyle = \"#1d1a16\";\n  ctx.beginPath();\n  ctx.moveTo(bx, h * 0.74);\n  ctx.lineTo(bx, h * 0.82);\n  ctx.stroke();\n  ctx.fillStyle = \"#1d1a16\";\n  ctx.font = \"12px sans-serif\";\n  ctx.fillText(\"cupo\", bx + 6, h * 0.90);\n  ctx.fillStyle = \"#5c564c\";\n  ctx.font = \"13px sans-serif\";\n  ctx.fillText(\"K azul  V coral    MHA = 8 grupos    MQA = 1    cupo de juguete\", 28, h * 0.96);\n}"
    }
  }
];
