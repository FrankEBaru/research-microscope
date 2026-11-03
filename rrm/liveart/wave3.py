"""Resto de la segunda ola. Lo importa wave2 al terminar, para no hacer un ciclo."""

from rrm.liveart.wave2 import _spec


MORE = [
    _spec(
        "gae_lambda", "gae-lambda", "Lambda mezcla el retorno corto y el largo",
        "GAE blends a one-step advantage and the full return with lambda.",
        "1506.02438", r"\bgae\b", "lambda",
        "GAE mezcla con lambda el advantage de un paso y el retorno largo. Lambda en cero se queda en el paso; en uno usa la cadena entera.",
        (
            ("¿Lambda en cero usa la cadena completa?", "solo el advantage de un paso"),
            ("¿Qué crece cuando lambda sube?", "el peso del retorno largo"),
            ("¿Se está promediando la recompensa o el advantage?", "el advantage"),
        ),
        (("lam", "lambda", 0, 1, 0.4, 0.05),),
        """  var lam = state.lam;
  var td = 0.35, full = 0.9, mix, bh;
  mix = (1 - lam) * td + lam * full;
  ctx.fillStyle = "#d9d3c7";
  ctx.fillRect(40, h * 0.8 - td * h * 0.6, 36, td * h * 0.6);
  ctx.fillRect(100, h * 0.8 - full * h * 0.6, 36, full * h * 0.6);
  bh = mix * h * 0.6;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(180, h * 0.8 - bh, 48, bh);
""",
    ),
    _spec(
        "group_norm", "group-norm", "Los grupos parten los canales",
        "GroupNorm computes mean and variance inside each group of channels, not over the batch.",
        "1803.08494", r"groupnorm|group normalization", "group",
        "GroupNorm no mira el batch: parte los canales en grupos y normaliza adentro de cada uno. Más grupos, rebanadas más finas.",
        (
            ("¿La estadística sale del batch o del grupo?", "del grupo de canales"),
            ("¿Qué se adelgaza cuando hay más grupos?", "cada rebanada"),
            ("¿Un solo grupo se parece a normalizar todo el mapa?", "sí, es un grupo con todos los canales"),
        ),
        (("groups", "grupos", 1, 8, 4, 1),),
        """  var groups = state.groups;
  var i, x;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  for (i = 0; i <= groups; i++) {
    x = 24 + (i / groups) * (w - 48);
    ctx.beginPath();
    ctx.moveTo(x, 36);
    ctx.lineTo(x, h * 0.72);
    ctx.stroke();
  }
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(24, h * 0.78, (w - 48) / groups, 16);
""",
    ),
    _spec(
        "lookahead_k", "lookahead-k", "El peso lento promedia los pasos",
        "Lookahead averages the last k fast steps into a slow weight.",
        "1907.08610", r"\blookahead\b", "lookahead",
        "Lookahead deja que el peso rápido oscile y el lento promedia los últimos k pasos. K más grande jala el lento hacia el centro.",
        (
            ("¿El peso lento sigue cada paso rápido?", "promedia los últimos k"),
            ("¿Qué se aplana cuando k crece?", "el promedio del peso lento"),
            ("¿Quién oscila, el rápido o el lento?", "el rápido"),
        ),
        (("k", "pasos", 1, 8, 3, 1),),
        """  var k = state.k;
  var i, fast, slow, x, y;
  slow = 0;
  ctx.fillStyle = "#c4512c";
  for (i = 0; i < 16; i++) {
    fast = Math.sin(i * 0.9) * 0.8;
    x = 24 + i * ((w - 60) / 16);
    ctx.fillRect(x, h * 0.55 - fast * h * 0.28, 6, 6);
    if (i >= 16 - k) slow += fast;
  }
  slow = slow / k;
  ctx.fillStyle = "#1f4b99";
  ctx.beginPath();
  ctx.arc(w * 0.5, h * 0.55 - slow * h * 0.28, 8, 0, Math.PI * 2);
  ctx.fill();
""",
    ),
    _spec(
        "double_descent", "double-descent", "Después del pico, el error vuelve a bajar",
        "Double descent makes test error fall again after the interpolation peak.",
        "1912.02292", r"double descent", "descent",
        "Double descent baja, hace un pico en la interpolación y vuelve a bajar. El marcador recorre ese ancho.",
        (
            ("¿El error de prueba solo baja al agrandar el modelo?", "sube en el pico y después baja otra vez"),
            ("¿Dónde está el peor ancho?", "en el pico de interpolación"),
            ("¿Qué se está moviendo, el ancho o el pico?", "el ancho; el pico se queda"),
        ),
        (("width", "ancho", 1, 40, 18, 1),),
        """  var width = state.width;
  var i, u, err, x, y, mu, my;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 40; i++) {
    u = i / 40;
    err = 0.85 * Math.exp(-u * 3) + 0.55 * Math.exp(-Math.pow((u - 0.42) / 0.11, 2)) + 0.12 * Math.exp(-(1 - u) * 3);
    x = 28 + u * (w - 56);
    y = h * 0.82 - err * h * 0.5;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
  u = (width - 1) / 39;
  err = 0.85 * Math.exp(-u * 3) + 0.55 * Math.exp(-Math.pow((u - 0.42) / 0.11, 2)) + 0.12 * Math.exp(-(1 - u) * 3);
  mu = 28 + u * (w - 56);
  my = h * 0.82 - err * h * 0.5;
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(mu, my, 6, 0, Math.PI * 2);
  ctx.fill();
""",
    ),
    _spec(
        "lottery", "lottery-keep", "Podar de más tira el acierto",
        "The lottery ticket hypothesis says a dense net contains a sparse subnetwork that trains to the same accuracy.",
        "1803.03635", r"lottery ticket", "ticket",
        "La hipótesis del lottery ticket deja una subred rala. Mientras el keep aguanta, el acierto se queda; si podas de más, la barra se cae.",
        (
            ("¿Se puede tirar casi toda la red y seguir acertando?", "hasta un punto, sí"),
            ("¿Qué se cae cuando el keep pasa el umbral?", "el acierto"),
            ("¿Se está viendo el tamaño o la subred que queda?", "la subred que queda"),
        ),
        (("keep", "queda", 0.05, 1, 0.4, 0.05),),
        """  var keep = state.keep;
  var i, acc, bh;
  acc = keep > 0.25 ? 0.82 : 0.82 * (keep / 0.25);
  for (i = 0; i < 14; i++) {
    if (i / 14 <= keep) {
      ctx.strokeStyle = "#1f4b99";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(30 + i * 18, h * 0.3);
      ctx.lineTo(40 + i * 16, h * 0.55);
      ctx.stroke();
    }
  }
  bh = acc * h * 0.28;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.72, h * 0.78 - bh, 36, bh);
""",
    ),
    _spec(
        "paged_attn", "paged-blocks", "El bloque fija el hueco del final",
        "PagedAttention stores the KV cache in fixed-size blocks so a sequence does not reserve a contiguous slab.",
        "2309.06180", r"pagedattention", "paged",
        "PagedAttention parte el cache en bloques fijos. Un bloque más grande deja más hueco vacío al final de la secuencia.",
        (
            ("¿Por qué sobra espacio al final?", "el último bloque no se llena"),
            ("¿Qué crece con el tamaño de bloque?", "el hueco del último bloque"),
            ("¿La secuencia reserva una losa continua?", "no, reserva bloques"),
        ),
        (("block", "bloque", 2, 16, 8, 1),),
        """  var block = state.block;
  var seq = 20, pages, waste, i, x;
  pages = Math.ceil(seq / block);
  waste = pages * block - seq;
  for (i = 0; i < seq; i++) {
    x = 16 + (i % 20) * ((w - 40) / 20);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(x, 40, (w - 40) / 20 - 2, 18);
  }
  ctx.fillStyle = "#e4dccb";
  ctx.fillRect(16, 80, waste * ((w - 40) / 20), 18);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(16, 120, pages * 14, 18);
""",
    ),
    _spec(
        "zero_stage", "zero-stage", "Cada etapa parte más estado",
        "ZeRO stage 3 partitions optimizer state, gradients, and parameters across devices.",
        "1910.02054", r"zero stage", "zero",
        "ZeRO stage parte el estado. En la etapa 0 cada dispositivo guarda todo; en la 3 ya partió optimizador, gradiente y parámetros.",
        (
            ("¿Qué se reparte al subir de etapa?", "primero el optimizador, luego el gradiente, luego el parámetro"),
            ("¿La etapa 0 ahorra memoria?", "no, cada uno guarda el estado entero"),
            ("¿Se está partiendo el batch o el estado del optimizador?", "el estado"),
        ),
        (("stage", "etapa", 0, 3, 1, 1),),
        """  var stage = state.stage;
  var mem = [0.9, 0.62, 0.38, 0.16];
  var bh = mem[stage] * h * 0.6;
  var i, piece;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.8 - bh, 70, bh);
  for (i = 0; i < stage; i++) {
    piece = (i + 1) * 28;
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(160 + i * 50, h * 0.8 - piece, 36, piece);
  }
""",
    ),
    _spec(
        "retnet_decay", "retnet-decay", "El decay apaga los tokens viejos",
        "RetNet decays the retention of earlier tokens by a factor gamma along the sequence.",
        "2307.08621", r"\bretnet\b", "retnet",
        "RetNet multiplica la retención por gamma en cada paso. Gamma chico apaga el pasado; gamma cerca de uno lo deja vivo.",
        (
            ("¿Un token viejo pesa igual que el último?", "no, se multiplica por gamma en cada paso"),
            ("¿Qué sobrevive si gamma es casi uno?", "casi toda la secuencia"),
            ("¿Se está borrando el estado o decayéndolo?", "decayéndolo"),
        ),
        (("gamma", "gamma", 0.55, 0.98, 0.8, 0.01),),
        """  var gamma = state.gamma;
  var i, a, bh;
  for (i = 0; i < 12; i++) {
    a = Math.pow(gamma, 11 - i);
    bh = a * h * 0.62;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * ((w - 40) / 12), h * 0.8 - bh, (w - 40) / 12 - 4, bh);
  }
""",
    ),
    _spec(
        "facenet", "facenet-margin", "El margen separa al negativo",
        "FaceNet keeps a margin between the anchor-positive distance and the anchor-negative distance.",
        "1503.03832", r"\bfacenet\b", "facenet",
        "FaceNet exige un margen: el negativo tiene que quedar más lejos que el positivo, por ese hueco.",
        (
            ("¿Basta con que el negativo esté un poco más lejos?", "tiene que superar el margen"),
            ("¿Qué crece cuando el margen sube?", "el hueco entre positivo y negativo"),
            ("¿Quién se ancla, el positivo o el negativo?", "los dos se miden contra el ancla"),
        ),
        (("margin", "margen", 0.2, 1.4, 0.6, 0.05),),
        """  var margin = state.margin;
  var x0 = w * 0.22, y = h * 0.55;
  ctx.fillStyle = "#1c1915";
  ctx.beginPath();
  ctx.arc(x0, y, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#1f4b99";
  ctx.beginPath();
  ctx.arc(x0 + 70, y, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(x0 + 70 + margin * 120, y, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x0 + 78, y);
  ctx.lineTo(x0 + 70 + margin * 120 - 10, y);
  ctx.stroke();
""",
    ),
    _spec(
        "huber_delta", "huber-delta", "Dentro de delta la pérdida es curva",
        "Huber loss is quadratic inside a delta and linear outside it.",
        "1504.08083", r"\bhuber\b", "huber",
        "Huber es cuadrática dentro de delta y lineal afuera. El codo se corre con delta.",
        (
            ("¿Un error enorme crece al cuadrado?", "afuera de delta crece lineal"),
            ("¿Qué se mueve cuando delta crece?", "el codo"),
            ("¿Un error chico usa la recta o la curva?", "la curva"),
        ),
        (("delta", "delta", 0.3, 2.2, 1, 0.05),),
        """  var delta = state.delta;
  var i, u, loss, x, y;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 40; i++) {
    u = (i / 40) * 3;
    loss = u < delta ? 0.5 * u * u : delta * (u - 0.5 * delta);
    x = 24 + (i / 40) * (w - 48);
    y = h * 0.84 - loss * h * 0.18;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
  x = 24 + (delta / 3) * (w - 48);
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath();
  ctx.moveTo(x, 30);
  ctx.lineTo(x, h * 0.84);
  ctx.stroke();
""",
    ),
    _spec(
        "moe_capacity", "switch-capacity", "El cupo tira los tokens de más",
        "The Switch Transformer capacity factor drops tokens when an expert is over its budget.",
        "2101.03961", r"capacity factor", "capacity",
        "El capacity factor es el cupo de cada experto. Si llegan más tokens, los de encima se caen del cubo.",
        (
            ("¿Un experto atiende todos los tokens que le tocan?", "solo hasta el cupo"),
            ("¿Qué se cae cuando el cupo baja?", "los tokens que no entran"),
            ("¿Se está viendo el router o el desborde?", "el desborde"),
        ),
        (("cap", "cupo", 1, 6, 3, 1),),
        """  var cap = state.cap;
  var i, y;
  for (i = 0; i < 8; i++) {
    y = 30 + i * 22;
    if (i < cap) {
      ctx.fillStyle = "#1f4b99";
      ctx.fillRect(40, y, 80, 16);
    } else {
      ctx.fillStyle = "#c4512c";
      ctx.fillRect(160, y, 80, 16);
    }
  }
""",
    ),
    _spec(
        "length_penalty", "length-penalty", "Alpha castiga la hipótesis larga",
        "GNMT length penalty divides a hypothesis score by its length to the power alpha.",
        "1609.08144", r"length penalty", "penalty",
        "La length penalty divide el score por el largo elevado a alpha. Alpha alto le quita la ventaja a la frase larga.",
        (
            ("¿Por qué una frase larga no debería ganar solo por ser larga?", "su score se divide por el largo"),
            ("¿Qué hipótesis cae cuando alpha sube?", "la más larga"),
            ("¿Se está normalizando el largo o el vocabulario?", "el largo"),
        ),
        (("alpha", "alpha", 0.2, 1.6, 0.6, 0.05),),
        """  var alpha = state.alpha;
  var lens = [4, 8, 14];
  var raw = [3.2, 5.4, 7.1];
  var i, score, bh, best, bi;
  best = -1; bi = 0;
  for (i = 0; i < 3; i++) {
    score = raw[i] / Math.pow(lens[i], alpha);
    if (score > best) { best = score; bi = i; }
    bh = score * h * 0.12;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(40 + i * 80, h * 0.8 - bh, 48, bh);
  }
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  ctx.strokeRect(36 + bi * 80, 28, 56, h * 0.55);
""",
    ),
]


from rrm.liveart.wave4 import EXTRA

MORE.extend(EXTRA)
