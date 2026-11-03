"""Segunda ola de temas. Un nombre propio puntúa 3 y va delante en el desempate.

Cada draw usa el subconjunto del sandbox 0.3: sin toFixed, sin slice, sin continue.
El control mueve coordenadas, no solo el color.
"""

import re


def _mark(pattern):
    cre = re.compile(pattern, re.I)

    def score(blob, cre=cre):
        return 3 if cre.search(blob) else 0

    return score


def _knob(kid, label, lo, hi, value, step):
    return {"id": kid, "label": label, "min": lo, "max": hi, "value": value, "step": step}


def _spec(name, sid, title, claim, arxiv, pattern, mark, explain, questions, knobs, body):
    return {
        "name": name,
        "id": sid,
        "title": title,
        "claim": claim,
        "arxiv": arxiv,
        "score": _mark(pattern),
        "mark": mark,
        "explain": explain,
        "questions": questions,
        "controls": [_knob(*item) for item in knobs],
        "body": body,
    }


def extra_topics():
    return tuple(
        {
            "name": spec["name"],
            "score": spec["score"],
            "controls": tuple(item["id"] for item in spec["controls"]),
            "mark": spec["mark"],
            "explain": spec["explain"],
            "questions": tuple(tuple(pair) for pair in spec["questions"]),
        }
        for spec in SPECS
    )


def selector_rows():
    return [
        (
            spec["id"],
            {"text": spec["claim"], "latex": "", "context": "", "arxiv": spec["arxiv"]},
            "widget",
            spec["name"],
            "mechanism",
        )
        for spec in SPECS
    ]


_Q = tuple  # alias so the table below stays short


SPECS = [
    _spec(
        "ddim_eta", "ddim-eta", "Eta abre el abanico",
        "DDIM uses eta to mix a deterministic step with residual noise.",
        "2010.02502", r"\bddim\b", "ddim",
        "DDIM con eta en cero sigue una sola curva. Al subir eta, el ruido residual abre un abanico de trayectorias alrededor de ese paso.",
        (
            ("¿Por qué con eta en cero las curvas se pegan?", "sin ruido residual el paso es único"),
            ("¿Qué se agrega cuando eta sube?", "un resto aleatorio alrededor del paso"),
            ("¿El paso determinista sigue apuntando al dato?", "la curva central no se mueve"),
        ),
        (("eta", "eta", 0, 1, 0.35, 0.05),),
        """  var eta = state.eta;
  var s, i, x, y, wobble;
  ctx.lineWidth = 1.6;
  ctx.strokeStyle = "#1f4b99";
  for (s = 0; s < 7; s++) {
    ctx.beginPath();
    for (i = 0; i <= 16; i++) {
      x = 36 + i * ((w - 72) / 16);
      wobble = Math.sin(i * 0.7 + s) * eta * (s - 3) * 16;
      y = h * 0.78 - i * (h * 0.032) + wobble;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
""",
    ),
    _spec(
        "adamw", "adamw-decay", "El decaimiento jala el peso",
        "AdamW applies weight decay to the weights themselves, not to the adaptive gradient moment.",
        "1711.05101", r"\badamw\b", "adamw",
        "AdamW resta el decaimiento del peso, no del momento. El punto naranja se queda; el azul se encoge hacia cero aunque el gradiente sea chico.",
        (
            ("¿Por qué el peso azul se encoge si el gradiente es chico?", "el decaimiento se resta del peso"),
            ("¿Qué le pasa al naranja cuando sube el decaimiento?", "no usa decaimiento, se queda"),
            ("¿Se está achicando el paso adaptativo o el parámetro?", "el parámetro"),
        ),
        (("decay", "decay", 0, 0.25, 0.08, 0.01),),
        """  var decay = state.decay;
  var i, wa, ww, x, lr, g;
  wa = 1; ww = 1; lr = 0.12; g = 0.015;
  for (i = 0; i < 16; i++) {
    x = 28 + i * ((w - 70) / 16);
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(x, h * 0.78 - wa * h * 0.55, 7, 7);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(x + 10, h * 0.78 - ww * h * 0.55, 7, 7);
    wa = wa - lr * g;
    ww = ww - lr * g - decay * ww;
    if (wa < 0) wa = 0;
    if (ww < 0) ww = 0;
  }
""",
    ),
    _spec(
        "cutmix", "cutmix-area", "El área es la etiqueta",
        "CutMix pastes a patch from another image and mixes the labels by the patch area.",
        "1905.04899", r"\bcutmix\b", "cutmix",
        "CutMix pega un recorte de la otra imagen. La barra de la etiqueta sigue el área del parche, no el borde.",
        (
            ("¿La etiqueta sigue el borde o el área?", "sigue el área del parche"),
            ("¿Qué pasa con la clase de abajo cuando el parche crece?", "cede peso en proporción al área"),
            ("¿Por qué un parche chico casi no mueve la etiqueta?", "su área es poca"),
        ),
        (("lam", "area", 0.08, 0.85, 0.35, 0.01),),
        """  var lam = state.lam;
  var side = Math.sqrt(lam) * (w * 0.42);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(28, 36, w * 0.42, h * 0.62);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(44, 52, side, side * 0.72);
  ctx.fillStyle = "#1c1915";
  ctx.fillRect(w * 0.62, h * 0.78 - lam * h * 0.5, 36, Math.max(4, lam * h * 0.5));
""",
    ),
    _spec(
        "sgdr", "sgdr-cycles", "El coseno vuelve a subir",
        "SGDR decays the learning rate with a cosine and restarts it at the next cycle.",
        "1608.03983", r"\bsgdr\b", "sgdr",
        "SGDR baja el paso con un coseno y lo reinicia. Más ciclos meten más reinicios en el mismo tramo.",
        (
            ("¿Por qué el paso vuelve a uno sin cambiar el máximo?", "cada ciclo reinicia el coseno"),
            ("¿Qué se aprieta cuando hay más ciclos?", "el tramo de cada bajada"),
            ("¿El mínimo del coseno llega a cero?", "sí, al final de cada ciclo"),
        ),
        (("cycles", "ciclos", 1, 4, 2, 1),),
        """  var cycles = state.cycles;
  var i, u, lr, x, y;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 64; i++) {
    u = (i / 64) * cycles;
    lr = 0.5 * (1 + Math.cos(Math.PI * (u - Math.floor(u))));
    x = 24 + (i / 64) * (w - 48);
    y = h * 0.78 - lr * h * 0.55;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
""",
    ),
    _spec(
        "sac_temp", "sac-alpha", "Alpha abre la política",
        "SAC sets a temperature alpha so the policy entropy stays near a target.",
        "1801.01290", r"\bsac\b", "alpha",
        "SAC usa una temperatura alpha. Con alpha chico una acción se queda el peso; con alpha grande las tres se parecen.",
        (
            ("¿Por qué una acción se come el resto si alpha baja?", "la temperatura ya no aplana"),
            ("¿Qué se está empujando, la recompensa o la entropía?", "alpha sostiene la entropía"),
            ("¿Las tres acciones pueden quedar parejas?", "sí, con alpha alto"),
        ),
        (("alpha", "alpha", 0.15, 2.5, 0.6, 0.05),),
        """  var alpha = state.alpha;
  var logits = [1.4, 0.2, -0.6];
  var i, m, z, p, bh;
  var probs = [0, 0, 0];
  m = -100;
  for (i = 0; i < 3; i++) if (logits[i] / alpha > m) m = logits[i] / alpha;
  z = 0;
  for (i = 0; i < 3; i++) { probs[i] = Math.exp(logits[i] / alpha - m); z += probs[i]; }
  for (i = 0; i < 3; i++) {
    p = probs[i] / z;
    bh = p * h * 0.62;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(w * 0.22 + i * 70, h * 0.8 - bh, 46, bh);
  }
""",
    ),
    _spec(
        "grad_clip", "grad-clip", "El pico se corta",
        "Gradient clipping cuts a gradient whose norm exceeds a threshold.",
        "1211.5063", r"gradient clipping", "clip",
        "El clip del gradiente deja pasar lo chico y aplana el pico que pasa el tope. La curva se corta, no se reescala entera.",
        (
            ("¿Se achica todo el gradiente o solo el pico?", "solo lo que pasa el tope"),
            ("¿Qué pasa con un paso que ya cabía?", "sigue igual"),
            ("¿Por qué un tope más bajo aplana más?", "corta antes"),
        ),
        (("cap", "tope", 0.25, 2.4, 1, 0.05),),
        """  var cap = state.cap;
  var raw = [0.2, 0.5, 1.4, 2.8, 1.1, 0.4, 0.3];
  var i, v, x, y0, y1;
  y0 = h * 0.82;
  ctx.strokeStyle = "#d9d3c7";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i < 7; i++) {
    x = 30 + i * ((w - 60) / 6);
    y1 = y0 - raw[i] * h * 0.22;
    if (i === 0) ctx.moveTo(x, y1); else ctx.lineTo(x, y1);
  }
  ctx.stroke();
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  for (i = 0; i < 7; i++) {
    v = raw[i] > cap ? cap : raw[i];
    x = 30 + i * ((w - 60) / 6);
    y1 = y0 - v * h * 0.22;
    if (i === 0) ctx.moveTo(x, y1); else ctx.lineTo(x, y1);
  }
  ctx.stroke();
""",
    ),
    _spec(
        "atrous", "atrous-rate", "Los huecos agrandan el campo",
        "DeepLab atrous convolution inserts holes so the rate grows the field without more weights.",
        "1606.00915", r"\batrous\b", "atrous",
        "La convolución atrous no suma pesos: mete huecos. La tasa separa las tres muestras y el campo crece.",
        (
            ("¿Crecen los pesos o los huecos?", "los huecos"),
            ("¿Por qué el campo se abre sin más parámetros?", "las mismas tres muestras se separan"),
            ("¿Qué se pierde si la tasa es uno?", "el campo se queda chico"),
        ),
        (("rate", "tasa", 1, 6, 2, 1),),
        """  var rate = state.rate;
  var gap = rate * 18;
  var i, x;
  ctx.fillStyle = "#e7e0d2";
  ctx.fillRect(w * 0.12, h * 0.42, gap * 4 + 20, 28);
  ctx.fillStyle = "#1f4b99";
  for (i = 0; i < 3; i++) {
    x = w * 0.18 + i * gap;
    ctx.fillRect(x, h * 0.38, 16, 36);
  }
""",
    ),
    _spec(
        "sam_rho", "sam-rho", "El mínimo tiene que caber en la bola",
        "Sharpness-aware minimization looks for a low loss throughout a neighborhood of radius rho.",
        "2010.01412", r"sharpness-aware", "rho",
        "SAM (sharpness-aware) no se queda en un mínimo filoso. Rho es el radius del vecindario: el punto marcado es el peor dentro de esa bola.",
        (
            ("¿Por qué no basta el mínimo de un solo punto?", "al lado la pérdida puede dispararse"),
            ("¿Qué crece cuando rho crece?", "la bola donde se busca el peor punto"),
            ("¿Un valle ancho se mueve igual que un pico?", "el valle aguanta un rho mayor"),
        ),
        (("rho", "radio", 0.15, 1.6, 0.6, 0.05),),
        """  var rho = state.rho;
  var i, u, x, y, loss, worst, wx, wy, px;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  worst = -1; wx = 0; wy = 0;
  for (i = 0; i <= 48; i++) {
    u = -1.6 + (i / 48) * 3.2;
    loss = 0.15 + u * u * 0.35 + 0.55 * Math.exp(-Math.pow((u - 0.15) / 0.18, 2));
    x = w * 0.5 + u * (w * 0.22);
    y = h * 0.82 - loss * h * 0.28;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    if (Math.abs(u) <= rho && loss > worst) { worst = loss; wx = x; wy = y; }
  }
  ctx.stroke();
  px = rho * w * 0.22;
  ctx.strokeStyle = "#c4512c";
  ctx.strokeRect(w * 0.5 - px, 28, px * 2, h * 0.62);
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(wx, wy, 5, 0, Math.PI * 2);
  ctx.fill();
""",
    ),
    _spec(
        "mixup", "mixup-lambda", "El ejemplo queda en el segmento",
        "Mixup draws a lambda and trains on the segment between two examples and their labels.",
        "1710.09412", r"\bmixup\b", "mixup",
        "Mixup no elige una de las dos fotos: el ejemplo y la etiqueta quedan sobre el segmento, en la fracción lambda.",
        (
            ("¿El modelo ve una de las dos clases o una mezcla?", "una mezcla sobre el segmento"),
            ("¿Qué se mueve cuando lambda va de cero a uno?", "el punto y la barra de la etiqueta"),
            ("¿Lambda en un medio es la clase de la izquierda?", "es mitad y mitad"),
        ),
        (("lam", "lambda", 0, 1, 0.35, 0.05),),
        """  var lam = state.lam;
  var x0 = w * 0.18, x1 = w * 0.62, y = h * 0.58;
  var x = x0 + (x1 - x0) * lam;
  ctx.strokeStyle = "#d9d3c7";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x0, y);
  ctx.lineTo(x1, y);
  ctx.stroke();
  ctx.fillStyle = "#1f4b99";
  ctx.beginPath();
  ctx.arc(x0, y, 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(x1, y, 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#1c1915";
  ctx.beginPath();
  ctx.arc(x, y - 36, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillRect(w * 0.78, h * 0.74 - lam * h * 0.4, 28, Math.max(4, lam * h * 0.4));
""",
    ),
    _spec(
        "soft_nms", "soft-nms", "El solape apaga la caja",
        "Soft-NMS decays the score of a box whose IoU with the selected box exceeds a threshold.",
        "1704.04503", r"soft-nms|soft nms", "nms",
        "Soft-NMS no borra de golpe: si el IoU con la caja elegida pasa el umbral, la otra caja se encoge.",
        (
            ("¿Una caja que se solapa desaparece o se apaga?", "su score baja"),
            ("¿Qué decide el umbral?", "a partir de qué solape empieza el castigo"),
            ("¿La caja elegida también se encoge?", "no, ella fija el solape"),
        ),
        (("iou", "iou", 0.15, 0.9, 0.5, 0.05),),
        """  var iou = state.iou;
  var overlaps = [0, 0.35, 0.62, 0.84];
  var i, keep, bh;
  for (i = 0; i < 4; i++) {
    keep = i === 0 || overlaps[i] < iou ? 1 : 0.22;
    bh = (i === 0 ? 0.9 : 0.75 * keep) * h * 0.55;
    ctx.fillStyle = i === 0 ? "#1f4b99" : "#c4512c";
    ctx.fillRect(36 + i * 70, h * 0.8 - bh, 48, bh);
  }
""",
    ),
]


from rrm.liveart.wave3 import MORE

SPECS.extend(MORE)
