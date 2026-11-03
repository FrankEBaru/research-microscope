"""Cinco widgets del top 15, rehechos para la rúbrica de RRM-84.

El dibujo que ya enseñaba se queda. Cada control cruza un régimen y el texto
dice qué es ecuación del paper y qué es juguete. No son few-shots del prompt.
"""


def _knob(kid, label, lo, hi, value, step):
    return {"id": kid, "label": label, "min": lo, "max": hi, "value": value, "step": step}


def _row(wid, topic, title, explain, questions, controls, draw, claim, arxiv):
    return {
        "id": wid,
        "claim": {"text": claim, "latex": "", "context": "", "arxiv": arxiv},
        "widget": {
            "id": wid,
            "topic": topic,
            "title": title,
            "explain": explain,
            "questions": [{"q": q, "why": why} for q, why in questions],
            "controls": list(controls),
            "draw": draw,
        },
    }


_ADAM = """function draw(ctx, state, t) {
  var w = state.w, h = state.h, lr = state.lr, wall = state.wall;
  var b1 = 0.9, b2 = 0.999, eps = 0.00000001;
  var x0 = 28, y0 = 18, pw = w * 0.62, ph = h - 36;
  function X(x) { return x0 + (x + 1.5) / 3 * pw; }
  function Y(y) { return y0 + (1.15 - y) / 2.3 * ph; }
  var levels = [0.5, 1.5, 3, 6, 9], li, a, c, ct, st, px, py;
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
      px = Math.sqrt(2 * c) * ct;
      py = Math.sqrt(c / wall) * st;
      if (a === 0) ctx.moveTo(X(px), Y(py)); else ctx.lineTo(X(px), Y(py));
    }
    ctx.stroke();
  }
  function path(kind) {
    var x = -1.15, y = 0.55, mx = 0, my = 0, vx = 0, vy = 0;
    var step, gx, gy, out = 0, mhx, mhy, vhx, vhy;
    ctx.beginPath();
    ctx.moveTo(X(x), Y(y));
    for (step = 1; step <= 26; step++) {
      gx = x;
      gy = 2 * wall * y;
      if (kind === 0) { x = x - lr * gx; y = y - lr * gy; }
      else {
        mx = b1 * mx + (1 - b1) * gx;
        my = b1 * my + (1 - b1) * gy;
        vx = b2 * vx + (1 - b2) * gx * gx;
        vy = b2 * vy + (1 - b2) * gy * gy;
        mhx = mx / (1 - Math.pow(b1, step));
        mhy = my / (1 - Math.pow(b1, step));
        vhx = vx / (1 - Math.pow(b2, step));
        vhy = vy / (1 - Math.pow(b2, step));
        x = x - lr * mhx / (Math.sqrt(vhx) + eps);
        y = y - lr * mhy / (Math.sqrt(vhy) + eps);
      }
      if (x > 1.45 || x < -1.45 || y > 1.1 || y < -1.1) {
        var cx = x, cy = y;
        if (cx > 1.45) cx = 1.45;
        if (cx < -1.45) cx = -1.45;
        if (cy > 1.1) cy = 1.1;
        if (cy < -1.1) cy = -1.1;
        ctx.lineTo(X(cx), Y(cy));
        out = 1;
        break;
      }
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
  var lx = x0 + pw + 14;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(lx, 40, 10, 10);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(lx, 60, 10, 10);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#1d1a16";
  ctx.fillText("SGD", lx + 16, 50);
  ctx.fillText("Adam", lx + 16, 70);
  ctx.fillStyle = sgdOut ? "#c4512c" : "#1d1a16";
  if (sgdOut) ctx.fillText("SGD se sale", lx, 98);
  else if (wall < 8) ctx.fillText("pared suave", lx, 98);
  else ctx.fillText("SGD rebota", lx, 98);
  ctx.fillStyle = "#8a8175";
  ctx.font = "12px sans-serif";
  ctx.fillText("umbral " + (Math.round(100 / wall) / 100), lx, 118);
  ctx.fillText("f = 1/2 x^2 + pared y^2", x0, 16);
}"""


_ROPE = """function draw(ctx, state, t) {
  var w = state.w, h = state.h, m = state.m + state.theta, n = state.n + state.theta;
  var th = [1, 0.32, 0.1], qa = [0.4, 1.1, 2.1], ka = [1.5, 0.25, 2.5];
  var i, s = 0, r = Math.min(h * 0.16, w / 11), dist = state.m - state.n;
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
  if (dist < 0) dist = -dist;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  for (i = 0; i < 3; i++) {
    var cx = w * (0.12 + 0.2 * i), cy = h * 0.30;
    var aq = qa[i] + m * th[i], ak = ka[i] + n * th[i];
    ctx.strokeStyle = "#e0d5c6";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 6.2832);
    ctx.stroke();
    arrow(cx, cy, aq, "#c4512c");
    arrow(cx, cy, ak, "#1f4b99");
    s = s + Math.cos(aq - ak);
    ctx.fillStyle = "#8a8175";
    ctx.font = "12px sans-serif";
    ctx.fillText(i === 0 ? "rapida" : (i === 1 ? "media" : "lenta"), cx - 18, cy + r + 16);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("q·k " + Math.round(s * 100) / 100, w * 0.72, h * 0.12);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("m-n " + dist, w * 0.72, h * 0.12 + 20);
  ctx.fillText(s < 1 ? "lejos: el producto cae" : "cerca: se sostiene", w * 0.72, h * 0.12 + 38);
  ctx.fillText("desplazar no lo mueve", w * 0.72, h * 0.12 + 56);
  var gx = 28, gy = h * 0.62, gw = w - 48, gh = h * 0.26, k, v;
  ctx.fillStyle = "#5c564c";
  ctx.font = "11px sans-serif";
  ctx.fillText("q·k contra el desplazamiento (recta plana)", gx, gy - 4);
  ctx.strokeStyle = "#e0d5c6";
  ctx.strokeRect(gx, gy, gw, gh);
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (k = 0; k <= 40; k++) {
    v = 0;
    for (i = 0; i < 3; i++) v = v + Math.cos(qa[i] - ka[i] + (state.m - state.n) * th[i]);
    if (k === 0) ctx.moveTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));
    else ctx.lineTo(gx + gw * k / 40, gy + gh * (1 - (v + 3) / 6));
  }
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(gx + gw * state.theta / 40, gy + gh * (1 - (s + 3) / 6), 5, 0, 6.2832);
  ctx.fill();
}"""


_BEAM = """function draw(ctx, state, t) {
  var w = state.w, h = state.h, width = Math.round(state.width);
  var w1 = ["el", "un", "ya"];
  var s1 = [-0.15, -0.55, -1.8];
  var w2 = [["dia", "fin", "mar"], ["gato", "perro", "sol"], ["no", "va", "es"]];
  var s2 = [[-2.2, -2.5, -2.8], [-0.1, -1.1, -1.6], [-1, -1.2, -1.4]];
  var order = [0, 1, 2], i, j, tmp, a, b, tot, best = -1000000, phrase = "", bi = 0;
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
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("primer token (empieza)", 16, 18);
  ctx.fillText("frase completa (termina)", w * 0.46, 18);
  for (a = 0; a < 3; a++) {
    i = order[a];
    var y = h * 0.16 + a * h * 0.20, kept = a < width, bestB = 0;
    for (b = 1; b < 3; b++) if (s2[i][b] > s2[i][bestB]) bestB = b;
    var total = s1[i] + s2[i][bestB];
    var bw1 = (s1[i] + 2.2) / 2.2 * 78;
    ctx.fillStyle = kept ? "#1f4b99" : "#d5cbbd";
    ctx.fillRect(16, y, bw1, 18);
    ctx.fillStyle = "#1d1a16";
    ctx.fillText(w1[i] + "  " + s1[i], 22 + bw1, y + 14);
    var bw2 = Math.max(8, (total + 3.2) / 3.2 * 70);
    ctx.fillStyle = kept ? (i === bi ? "#c4512c" : "#1f4b99") : "#d5cbbd";
    ctx.fillRect(w * 0.46, y, bw2, 18);
    ctx.fillStyle = "#1d1a16";
    ctx.fillText(w1[i] + " " + w2[i][bestB] + "  " + Math.round(total * 10) / 10, w * 0.46 + bw2 + 8, y + 14);
  }
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.5;
  ctx.strokeRect(8, h * 0.12, w * 0.40, width * h * 0.20 + 8);
  ctx.font = "18px sans-serif";
  ctx.fillStyle = "#1d1a16";
  if (width === 1) ctx.fillText("ancho 1 cae en " + phrase, 16, h - 18);
  else if (width === 2) ctx.fillText("ancho 2 rescata " + phrase, 16, h - 18);
  else ctx.fillText("ancho 3 no mejora: " + phrase, 16, h - 18);
}"""


_KL = """function draw(ctx, state, t) {
  var w = state.w, h = state.h, beta = state.beta;
  var name = ["si", "ok", "eh", "bueno", "ja"];
  var ref = [0.42, 0.28, 0.16, 0.1, 0.04];
  var reward = [0.1, 0.3, 0.5, 0.6, 2.4];
  var raw = [], z = 0, i, p = [], kl = 0, ja;
  for (i = 0; i < 5; i++) { raw[i] = ref[i] * Math.exp(reward[i] / beta); z = z + raw[i]; }
  for (i = 0; i < 5; i++) { p[i] = raw[i] / z; kl = kl + p[i] * Math.log(p[i] / ref[i]); }
  ja = Math.round(p[4] * 100);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  var bw = (w - 40) / 5, bh = h * 0.26;
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("referencia", 12, 18);
  ctx.fillText("política  π ∝ ref · exp(premio / β)", 12, h * 0.46);
  for (i = 0; i < 5; i++) {
    var x = 18 + i * bw;
    ctx.fillStyle = "#e4d6c4";
    ctx.fillRect(x, 28, bw - 12, bh);
    ctx.fillStyle = "#8a8175";
    ctx.fillRect(x, 28 + bh * (1 - ref[i] / 0.5), bw - 12, bh * ref[i] / 0.5);
    ctx.fillStyle = "#d9e3f5";
    ctx.fillRect(x, h * 0.48, bw - 12, bh);
    ctx.fillStyle = i === 4 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(x, h * 0.48 + bh * (1 - Math.min(p[i], 0.95) / 0.95), bw - 12, bh * Math.min(p[i], 0.95) / 0.95);
    ctx.fillStyle = i === 4 ? "#c4512c" : "#1d1a16";
    ctx.fillText(name[i], x, h * 0.48 + bh + 16);
  }
  ctx.fillStyle = "#1d1a16";
  ctx.font = "14px sans-serif";
  ctx.fillText("KL " + Math.round(kl * 100) / 100, w - 92, 18);
  ctx.fillText("ja " + ja + "%", w - 92, 38);
  ctx.font = "14px sans-serif";
  ctx.fillStyle = ja > 50 ? "#c4512c" : "#1d1a16";
  var note = "el KL todavía reparte";
  if (ja > 50) note = "ja se queda el premio";
  else if (ja < 15) note = "se parece a la referencia";
  ctx.fillText(note, w * 0.42, h * 0.46);
}"""


_PE = """function draw(ctx, state, t) {
  var w = state.w, h = state.h, base = state.base, p = state.pos, d = 64, N = 64;
  var rows = [0, 4, 10, 16], r, i, q, y0, y, f, rh, peak, near;
  function X(q) { return 36 + (q / N) * (w - 52); }
  function freq(k) { return 1 / Math.pow(base, (2 * k) / d); }
  function sim(a, b) {
    var acc = 0, k, fr;
    for (k = 0; k < d / 2; k++) {
      fr = freq(k);
      acc = acc + Math.sin(a * fr) * Math.sin(b * fr) + Math.cos(a * fr) * Math.cos(b * fr);
    }
    return acc / (d / 2);
  }
  peak = sim(p, p);
  near = sim(p, p + 4);
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#1f4b99";
  ctx.fillText("seno", w - 110, 14);
  ctx.fillStyle = "#c4512c";
  ctx.fillText("coseno", w - 62, 14);
  rh = (h * 0.52) / rows.length;
  for (r = 0; r < rows.length; r++) {
    y0 = 22 + r * rh + rh * 0.55;
    f = freq(rows[r]);
    ctx.font = "11px sans-serif";
    ctx.fillStyle = "#8a8175";
    ctx.fillText(rows[r] === 0 ? "0 fija" : "" + rows[r], 2, y0 + 3);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "#1f4b99";
    ctx.beginPath();
    for (i = 0; i <= N; i++) {
      y = y0 - Math.sin(i * f) * rh * 0.32;
      if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);
    }
    ctx.stroke();
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#c4512c";
    ctx.beginPath();
    for (i = 0; i <= N; i++) {
      y = y0 - Math.cos(i * f) * rh * 0.32;
      if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);
    }
    ctx.stroke();
    ctx.fillStyle = "#1f4b99";
    ctx.beginPath();
    ctx.arc(X(p), y0 - Math.sin(p * f) * rh * 0.32, 3, 0, 6.2832);
    ctx.fill();
  }
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(X(p), 18);
  ctx.lineTo(X(p), h * 0.56);
  ctx.stroke();
  var sy = h * 0.64, sh = h * 0.22;
  ctx.fillStyle = "#5c564c";
  ctx.font = "12px sans-serif";
  ctx.fillText("parecido " + Math.round(peak * 100) / 100 + " en p,  " + Math.round(near * 100) / 100 + " a 4 pasos", 8, sy - 2);
  ctx.fillStyle = base < 100 ? "#c4512c" : "#5c564c";
  ctx.fillText(base < 100 ? "base chica: el pico se angosta" : "base 10000: pico ancho", w * 0.55, sy - 2);
  ctx.strokeStyle = "#1d1a16";
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  for (i = 0; i <= N; i++) {
    y = sy + 8 + sh - ((sim(p, i) + 0.15) / 1.3) * sh;
    if (i === 0) ctx.moveTo(X(i), y); else ctx.lineTo(X(i), y);
  }
  ctx.stroke();
}"""


def rows():
    return [
        _row(
            "adam-valley", "adam", "En el valle angosto SGD rebota y Adam no",
            "Adam (Kingma y Ba, 1412.6980) da el paso m̂/(√v̂+ε). Aquí β1 es 0.9 y β2 es 0.999, fijos. "
            "El valle f = ½x² + pared·y² es un juguete, no una figura medida: en y el gradiente es 2·pared veces el de x. "
            "Con pared 20, SGD rebota; si el lr pasa el umbral de la derecha, se sale. El segundo momento achica ese eje y Adam se queda. "
            "Baja la pared a 1 y SGD también baja liso. No es una corrida de entrenamiento.",
            (
                ("Sube el paso a 0.08. ¿Quién se sale del valle?", "SGD cruza el umbral y Adam sigue dentro"),
                ("Baja la pared a 1. ¿SGD sigue rebotando?", "en un valle redondo el paso de y ya no es enorme"),
                ("En el paso 0.04 y pared 20, ¿quién baja liso?", "Adam, porque el segundo momento frena la pared"),
                ("¿Este valle es una curva del paper?", "no: es un juguete para ver el paso"),
            ),
            (_knob("lr", "paso lr", 0.02, 0.1, 0.04, 0.01), _knob("wall", "pared", 1, 20, 20, 1)),
            _ADAM,
            "Adam steps by the bias-corrected first moment over the square root of the second moment, so a narrow valley does not make that step explode.",
            "1412.6980",
        ),
        _row(
            "rope-shift", "rope", "Desplazar los dos tokens no mueve q·k",
            "RoPE (Su et al., 2104.09864) gira q y k con la posición absoluta. En este juguete de tres pares, "
            "q·k es la suma de cosenos de (m−n): desplazar los dos el mismo tramo mueve las flechas y deja la recta plana. "
            "Aleja n de m y el producto cae; la marca «lejos» aparece cuando baja de 1. "
            "No es el RoPE de un modelo completo, solo tres frecuencias fijas.",
            (
                ("Pon desplaza en 32. ¿q·k cambió?", "las flechas giran y el punto corre sobre una recta plana"),
                ("Pon n en 20, con m en 3. ¿Qué le pasa al producto?", "la distancia m-n tumba q·k y sale la marca lejos"),
                ("Mira la flecha de la izquierda y la de la derecha. ¿Cuál da más vueltas al desplazar?", "la rápida cierra vueltas; la lenta casi no se mueve"),
                ("Con desplaza en 32, ¿q·k compara las posiciones o la distancia m−n?", "los dos giros se restan y queda m-n"),
            ),
            (
                _knob("theta", "desplaza", 0, 40, 0, 1),
                _knob("m", "posición m", 0, 20, 3, 1),
                _knob("n", "posición n", 0, 20, 8, 1),
            ),
            _ROPE,
            "RoPE rotates each absolute position, and the attention score depends only on the relative distance between the tokens.",
            "2104.09864",
        ),
        _row(
            "beam-trap", "beam", "El haz ancho rescata el camino que empezó peor",
            "GNMT (Wu et al., 1609.08144) decodifica con beam search. En el abstract normalizan la longitud y penalizan la cobertura; este juguete no lo hace y no es una frase medida. "
            "«el» empieza en −0.15 y «el día» termina cerca de −2.3; «un gato» empieza peor y termina cerca de −0.6. "
            "Ancho 1 cae en la trampa. Ancho 2 lo rescata. Ancho 3 no cambia el ganador. "
            "La barra larga de la izquierda no es la frase mejor.",
            (
                ("Baja el ancho a 1. ¿Qué frase queda?", "el codicioso se queda con el día, que empezó mejor"),
                ("En el ancho 2, ¿por qué gana un gato si un empezó peor?", "el haz compara la frase completa, no el primer token"),
                ("Sube el ancho a 3. ¿Cambia el ganador?", "ya entra al haz y un gato sigue ganando"),
                ("¿La barra más larga de la izquierda es la mejor frase?", "no: el empieza mejor y termina peor"),
            ),
            (_knob("width", "ancho", 1, 3, 2, 1),),
            _BEAM,
            "Beam search keeps a beam of prefixes, because the single most probable first token can lead to a worse finished sentence.",
            "1609.08144",
        ),
        _row(
            "kl-policy", "kl_rlhf", "Sin el KL, ja se queda con el premio",
            "InstructGPT (Ouyang et al., 2203.02155) maximiza premio menos β por el KL contra la referencia. "
            "Estas barras son la forma cerrada π ∝ π_ref · exp(premio/β), no una corrida de PPO. "
            "Los números son ilustrativos: ja tiene premio 2.4 y en la referencia solo pesa 0.04. "
            "Con β 0.7, ja no pasa de la mitad y el KL queda bajo 1. Bájalo de 0.4 y ja se queda el premio.",
            (
                ("Baja beta a 0.2. ¿Qué token se queda la masa?", "ja pasa del 50% y el KL deja de repartir"),
                ("En beta 0.7, ¿por qué ja no se lo lleva todo si su premio es 2.4?", "la referencia casi no dice ja y el KL lo cobra"),
                ("Sube beta a 4. ¿A quién se parece la política?", "a la referencia: ja vuelve a ser la barra chica"),
                ("¿Estas barras son una corrida de PPO del paper?", "no: son la forma cerrada, con premios de juguete"),
            ),
            (_knob("beta", "beta", 0.12, 4, 0.7, 0.02),),
            _KL,
            "In RLHF the optimal policy is the reference policy times exp(reward / beta), so a small beta lets one token take the reward.",
            "2203.02155",
        ),
        _row(
            "pe-sincos", "positional_encoding", "Lo cercano se parece: el pico cae en p",
            "El encoding del Transformer (Vaswani et al., 1706.03762) es seno de pos/10000^(2i/d) y el coseno en la dimensión impar. "
            "El parecido es el promedio de cosenos de la diferencia, así que en p vale 1 y a 4 pasos sigue alto con la base 10000. "
            "La fila 0 no depende de la base. Bájala de 100 y las filas de abajo se aceleran: el pico se angosta. "
            "La base 10000 es la del paper; la curva es ese producto, no una medición.",
            (
                ("Mueve la posición. ¿El pico de abajo la sigue?", "el parecido vale 1 en p y cae al alejarse"),
                ("Baja la base a 20. ¿Qué le pasa a las ondas de abajo y al pico?", "se aceleran y el parecido a 4 pasos se desploma"),
                ("¿La fila marcada 0 fija cambia cuando mueves la base?", "no: su frecuencia es 1 para cualquier base"),
                ("Con la base en 10000, ¿por qué a 4 pasos el parecido sigue en 0.75 si las ondas oscilan?", "el producto depende de la diferencia, no de la posición suelta"),
            ),
            (_knob("base", "base", 20, 100000, 10000, 20), _knob("pos", "posición", 0, 60, 18, 1)),
            _PE,
            "Sinusoidal positional encoding uses sin(pos / 10000^{2i/d}), so nearby positions have a similar encoding.",
            "1706.03762",
        ),
    ]
