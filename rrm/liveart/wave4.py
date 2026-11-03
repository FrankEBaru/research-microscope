"""Tercer bloque de temas. wave3 lo agrega al terminar."""

from rrm.liveart.wave2 import _spec


EXTRA = [
    _spec(
        "ema_decay", "ema-beta", "El decay deja atrás al maestro",
        "An EMA decay beta tracks a teacher that lags the noisy student.",
        "1703.01780", r"\bema\b", "ema",
        "EMA con decay beta sigue al estudiante ruidoso desde atrás. Beta alto casi no se mueve; beta bajo lo copia.",
        (
            ("¿El maestro copia cada salto del estudiante?", "solo una fracción, el decay"),
            ("¿Qué se queda quieto si beta es casi uno?", "el maestro"),
            ("¿Se promedia el peso o el gradiente?", "el peso"),
        ),
        (("beta", "decay", 0.1, 0.95, 0.7, 0.05),),
        """  var beta = state.beta;
  var i, student, teacher, x;
  teacher = 0;
  for (i = 0; i < 18; i++) {
    student = Math.sin(i * 0.7) * 0.8;
    teacher = beta * teacher + (1 - beta) * student;
    x = 20 + i * ((w - 50) / 18);
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(x, h * 0.55 - student * h * 0.28, 5, 5);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(x, h * 0.55 - teacher * h * 0.28, 5, 5);
  }
""",
    ),
    _spec(
        "cosine_snr", "cosine-mix", "El coseno no deja caer la señal a la mitad",
        "The improved DDPM cosine schedule keeps the signal-to-noise ratio from collapsing in the middle.",
        "2102.09672", r"cosine schedule", "cosine",
        "El cosine schedule aguanta la señal a la mitad del proceso. El calendario lineal ya la dejó caer.",
        (
            ("¿Cuál de las dos curvas cae antes?", "la lineal"),
            ("¿Qué se conserva a la mitad, la señal o el ruido?", "más señal con el coseno"),
            ("¿Se está viendo el paso del sampler o el calendario?", "el calendario"),
        ),
        (("mix", "mezcla", 0, 1, 0.5, 0.05),),
        """  var mix = state.mix;
  var i, u, lin, cosn, y, x;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.strokeStyle = "#1f4b99";
  for (i = 0; i <= 32; i++) {
    u = i / 32;
    lin = 1 - u;
    cosn = Math.cos(u * Math.PI * 0.5);
    y = h * 0.8 - ((1 - mix) * lin + mix * cosn) * h * 0.55;
    x = 24 + u * (w - 48);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
""",
    ),
    _spec(
        "per_alpha", "per-alpha", "Alpha concentra el muestreo en el error",
        "Prioritized replay samples a transition with probability proportional to its TD error raised to alpha.",
        "1511.05952", r"prioritized replay", "alpha",
        "Prioritized replay eleva el error TD a alpha. Alpha alto se queda con las transiciones que más fallan.",
        (
            ("¿Todas las transiciones salen igual de seguido?", "no, pesan por su error"),
            ("¿Qué barra crece cuando alpha sube?", "la del error grande"),
            ("¿Se está ordenando el buffer o el gradiente?", "la probabilidad de sacarla del buffer"),
        ),
        (("alpha", "alpha", 0.2, 2, 0.6, 0.05),),
        """  var alpha = state.alpha;
  var err = [0.2, 0.5, 1.4, 0.3];
  var i, p, s, bh;
  var wts = [0, 0, 0, 0];
  s = 0;
  for (i = 0; i < 4; i++) { wts[i] = Math.pow(err[i], alpha); s += wts[i]; }
  for (i = 0; i < 4; i++) {
    p = wts[i] / s;
    bh = p * h * 0.7;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(40 + i * 70, h * 0.82 - bh, 46, bh);
  }
""",
    ),
    _spec(
        "eps_greedy", "eps-greedy", "Epsilon reserva sitio al azar",
        "DQN epsilon-greedy takes a random action with probability epsilon and the greedy action otherwise.",
        "1312.5602", r"epsilon-greedy", "greedy",
        "Epsilon-greedy reserva una franja al azar y deja el resto a la acción greedy. La franja es epsilon.",
        (
            ("¿Siempre se toma la mejor acción?", "una fracción epsilon es al azar"),
            ("¿Qué crece cuando epsilon sube?", "la franja aleatoria"),
            ("¿Se está enfriando la política o el paso?", "la política"),
        ),
        (("eps", "eps", 0, 1, 0.2, 0.05),),
        """  var eps = state.eps;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(24, 40, eps * (w - 48), h * 0.35);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(24 + eps * (w - 48), 40, (1 - eps) * (w - 48), h * 0.35);
""",
    ),
    _spec(
        "discount_gamma", "discount-gamma", "Gamma apaga la recompensa lejana",
        "A reward delayed by eight steps is multiplied by gamma to the eight in the discounted return.",
        "1312.5602", r"discounted return", "discount",
        "En el discounted return, una recompensa a ocho pasos pesa gamma a la ocho. Gamma bajo la deja en el piso.",
        (
            ("¿Una recompensa lejana vale igual que una de ahora?", "se multiplica por gamma en cada paso"),
            ("¿Qué casi desaparece si gamma baja?", "la recompensa lejana"),
            ("¿Se está descontando el paso de gradiente o el retorno?", "el retorno"),
        ),
        (("gamma", "gamma", 0.5, 0.99, 0.9, 0.01),),
        """  var gamma = state.gamma;
  var now = h * 0.55;
  var later = Math.pow(gamma, 8) * h * 0.55;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(50, h * 0.8 - now, 50, now);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(140, h * 0.8 - later, 50, Math.max(2, later));
""",
    ),
    _spec(
        "polyak_tau", "polyak-tau", "Tau decide cuánto corre el blanco",
        "A Polyak average moves the target network only a fraction tau toward the online weights.",
        "1509.02971", r"\bpolyak\b", "polyak",
        "El promedio de Polyak mueve el blanco solo una fracción tau hacia la red online. Tau chico lo deja atrás.",
        (
            ("¿El blanco copia los pesos online?", "solo la fracción tau"),
            ("¿Qué se queda atrás si tau es chico?", "la red blanco"),
            ("¿Se promedian los datos o los pesos?", "los pesos"),
        ),
        (("tau", "tau", 0.02, 1, 0.2, 0.02),),
        """  var tau = state.tau;
  var online = w * 0.72;
  var target = w * 0.2 + tau * (online - w * 0.2);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(online, h * 0.4, 14, 14);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(target, h * 0.58, 14, 14);
""",
    ),
    _spec(
        "sliding_window", "sliding-window", "La ventana es una banda",
        "Longformer attends only inside a sliding window, so the band grows with the window.",
        "2004.05150", r"sliding window", "window",
        "Longformer no mira toda la frase: la atención es una banda, la sliding window. La banda se abre con la ventana.",
        (
            ("¿Un token ve toda la secuencia?", "solo la ventana"),
            ("¿Qué se ensancha cuando la ventana crece?", "la banda"),
            ("¿Se está recortando el contexto o el vocabulario?", "el contexto"),
        ),
        (("win", "ventana", 1, 10, 3, 1),),
        """  var win = state.win;
  var n = 14, i, j, cell;
  cell = Math.min((w - 30) / n, (h - 30) / n);
  for (i = 0; i < n; i++) {
    for (j = 0; j < n; j++) {
      if (Math.abs(i - j) <= win) {
        ctx.fillStyle = "#1f4b99";
        ctx.fillRect(16 + j * cell, 16 + i * cell, cell - 1, cell - 1);
      }
    }
  }
""",
    ),
    _spec(
        "attn_sink", "attn-sink", "El primer token se queda con masa",
        "An attention sink keeps a large score on the first token no matter how long the context is.",
        "2309.17453", r"attention sink", "sink",
        "El attention sink reserva masa en el primer token. Si el sink sube, esa barra crece y las demás bajan.",
        (
            ("¿El primer token puede quedarse con atención aunque no importe?", "sí, es el sink"),
            ("¿Qué les pasa a los demás si el sink sube?", "les queda menos masa"),
            ("¿Se está viendo el contexto o el primer puesto?", "el primer puesto"),
        ),
        (("sink", "sink", 0.2, 3, 1, 0.1),),
        """  var sink = state.sink;
  var scores = [sink, 0.6, 0.3, 0.2, 0.15];
  var i, m, z, p, bh;
  m = scores[0];
  for (i = 1; i < 5; i++) if (scores[i] > m) m = scores[i];
  z = 0;
  for (i = 0; i < 5; i++) z += Math.exp(scores[i] - m);
  for (i = 0; i < 5; i++) {
    p = Math.exp(scores[i] - m) / z;
    bh = p * h * 0.7;
    ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
    ctx.fillRect(30 + i * 55, h * 0.82 - bh, 40, bh);
  }
""",
    ),
    _spec(
        "neg_sample", "neg-k", "K negativos jalan el vector",
        "Negative sampling draws k noise words so the model does not score the whole vocabulary.",
        "1301.3781", r"negative sampling", "sampling",
        "Negative sampling no puntúa el vocabulario: dibuja k negativos. Más k, más flechas que jalan el vector.",
        (
            ("¿Hay que puntuar todas las palabras?", "basta k negativos"),
            ("¿Qué se suma cuando k crece?", "más jalones"),
            ("¿El positivo también es una muestra?", "no, el positivo se queda"),
        ),
        (("k", "k", 1, 10, 4, 1),),
        """  var k = state.k;
  var i, y;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(w * 0.3, h * 0.55);
  ctx.lineTo(w * 0.55, h * 0.35);
  ctx.stroke();
  for (i = 0; i < k; i++) {
    y = 30 + i * ((h - 50) / 10);
    ctx.strokeStyle = "#c4512c";
    ctx.beginPath();
    ctx.moveTo(w * 0.3, h * 0.55);
    ctx.lineTo(w * 0.72, y);
    ctx.stroke();
  }
""",
    ),
    _spec(
        "grad_ckpt", "ckpt-segments", "Menos cortes, más memoria",
        "Gradient checkpointing stores only a subset of activations and recomputes the rest.",
        "1604.06174", r"gradient checkpointing", "checkpoint",
        "Gradient checkpointing guarda solo algunos cortes. Menos cortes, menos memoria guardada y más recálculo.",
        (
            ("¿Hay que guardar cada activación?", "basta un subconjunto"),
            ("¿Qué baja cuando hay más cortes?", "la memoria de cada tramo"),
            ("¿El recálculo reemplaza a la memoria?", "sí, en los tramos que no se guardan"),
        ),
        (("segs", "cortes", 1, 8, 2, 1),),
        """  var segs = state.segs;
  var mem = (1 / segs) * h * 0.6;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.8 - mem, 60, mem);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(140, h * 0.8 - segs * 12, 60, segs * 12);
""",
    ),
    _spec(
        "pipe_bubble", "gpipe-bubble", "La burbuja crece con las etapas",
        "GPipe leaves a bubble of idle time that grows with the number of pipeline stages.",
        "1811.06965", r"\bgpipe\b", "bubble",
        "GPipe llena un pipeline y deja una bubble ociosa. Más etapas, más casillas vacías al arrancar.",
        (
            ("¿Todas las etapas trabajan desde el primer paso?", "las de adelante esperan"),
            ("¿Qué crece con el número de etapas?", "la burbuja"),
            ("¿Se está viendo el batch o el hueco ocioso?", "el hueco"),
        ),
        (("stages", "etapas", 2, 8, 4, 1),),
        """  var stages = state.stages;
  var r, c;
  for (r = 0; r < 6; r++) {
    for (c = 0; c < stages; c++) {
      ctx.fillStyle = r < c ? "#e4dccb" : "#1f4b99";
      ctx.fillRect(24 + c * 36, 24 + r * 28, 30, 22);
    }
  }
""",
    ),
    _spec(
        "batch_scale", "batch-lr", "El paso crece con el batch",
        "The linear scaling rule multiplies the learning rate by the batch size over a reference batch.",
        "1706.02677", r"linear scaling rule", "batch",
        "La linear scaling rule multiplica el paso por el batch relativo. Batch más grande, paso más largo.",
        (
            ("¿Un batch más grande usa el mismo paso?", "el paso crece en proporción"),
            ("¿Qué barra sigue al batch?", "el learning rate"),
            ("¿Se está escalando el modelo o el paso?", "el paso"),
        ),
        (("batch", "batch", 32, 1024, 256, 32),),
        """  var batch = state.batch;
  var lr = batch / 1024;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.8 - lr * h * 0.6, 80, lr * h * 0.6);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(160, h * 0.8 - (batch / 1024) * h * 0.5, 80, (batch / 1024) * h * 0.5);
""",
    ),
    _spec(
        "arcface", "arcface-margin", "El margen abre el ángulo",
        "ArcFace adds an angular margin so the target class must clear a wider angle.",
        "1801.07698", r"\barcface\b", "arcface",
        "ArcFace suma un margen angular. El arco de la clase correcta tiene que llegar más lejos cuando el margen crece.",
        (
            ("¿Basta con apuntar cerca de la clase?", "hay que pasar el margen angular"),
            ("¿Qué arco se alarga?", "el de la clase correcta"),
            ("¿El margen es una distancia o un ángulo?", "un ángulo"),
        ),
        (("margin", "margen", 0.1, 1.2, 0.5, 0.05),),
        """  var margin = state.margin;
  var cx = w * 0.4, cy = h * 0.6, rad = 90;
  ctx.strokeStyle = "#d9d3c7";
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.arc(cx, cy, rad, -1.2, 1.2);
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(cx + rad, cy);
  ctx.lineTo(cx + rad + margin * 160, cy - 40);
  ctx.stroke();
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(-0.4) * rad, cy + Math.sin(-0.4) * rad);
  ctx.stroke();
""",
    ),
    _spec(
        "flow_match", "flow-straight", "El flujo va en línea recta",
        "Flow matching moves the sample along a straight path from noise to data.",
        "2210.02747", r"flow matching", "flow",
        "Flow matching no da vueltas: el camino de ruido a dato es una recta. El control recorre ese flow.",
        (
            ("¿El camino del ruido al dato es una curva?", "en flow matching es una recta"),
            ("¿Qué se mueve con el control?", "el punto sobre la recta"),
            ("¿Se está mezclando ruido o siguiendo el flujo?", "el flujo"),
        ),
        (("tpos", "tiempo", 0, 1, 0.4, 0.05),),
        """  var tpos = state.tpos;
  var x0 = 40, y0 = h * 0.75, x1 = w - 50, y1 = h * 0.25;
  var x = x0 + (x1 - x0) * tpos;
  var y = y0 + (y1 - y0) * tpos;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(x, y, 7, 0, Math.PI * 2);
  ctx.fill();
""",
    ),
    _spec(
        "consistency_model", "consistency-steps", "Un paso ya cae cerca del dato",
        "A consistency model maps a noisy point at any time to the clean sample, and extra steps still refine it.",
        "2303.01469", r"consistency model", "consistency",
        "Un consistency model salta de cualquier ruido al dato. Más pasos todavía acercan el punto, pero el primer salto ya cruza.",
        (
            ("¿Hay que recorrer todos los pasos del proceso?", "un salto ya cae cerca"),
            ("¿Qué se acorta con más pasos?", "el error que queda"),
            ("¿Se está viendo el calendario o los saltos?", "los saltos"),
        ),
        (("steps", "pasos", 1, 6, 2, 1),),
        """  var steps = state.steps;
  var i, x, y, left;
  left = w * 0.75;
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(left, h * 0.3, 8, 0, Math.PI * 2);
  ctx.fill();
  for (i = 0; i < steps; i++) {
    x = 30 + i * ((w * 0.6) / 6);
    y = h * 0.75 - i * 18;
    ctx.fillStyle = "#1f4b99";
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fill();
  }
""",
    ),
    _spec(
        "min_snr", "minsnr-gamma", "Gamma tapa el peso de la pérdida",
        "Min-SNR caps the diffusion loss weight by a gamma so early steps do not dominate.",
        "2303.09556", r"min-snr", "gamma",
        "Min-SNR tapa el peso de la pérdida en gamma. Sin el tope, los pasos tempranos se llevan la barra entera.",
        (
            ("¿Todos los pasos pesan igual en la pérdida?", "los tempranos pesarían de más"),
            ("¿Qué le pasa al pico si gamma baja?", "se aplana al tope"),
            ("¿Se está recortando el ruido o el peso?", "el peso"),
        ),
        (("gamma", "gamma", 0.4, 4, 1.5, 0.1),),
        """  var gamma = state.gamma;
  var raw = [4.2, 2.4, 1.3, 0.6, 0.3];
  var i, v, bh;
  for (i = 0; i < 5; i++) {
    v = raw[i] > gamma ? gamma : raw[i];
    bh = v * h * 0.14;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(30 + i * 55, h * 0.82 - bh, 40, bh);
  }
""",
    ),
    _spec(
        "medusa_heads", "medusa-heads", "Cada cabeza propone un token futuro",
        "Medusa adds extra heads that propose the next several tokens at once.",
        "2401.10774", r"\bmedusa\b", "medusa",
        "Medusa cuelga cabezas extra del mismo punto. Cada cabeza propone un token más adelante.",
        (
            ("¿Hace falta un paso por token futuro?", "varias cabezas proponen juntos"),
            ("¿Qué se ramifica cuando hay más cabezas?", "el abanico"),
            ("¿Se está prediciendo el pasado o lo que sigue?", "lo que sigue"),
        ),
        (("heads", "cabezas", 1, 5, 3, 1),),
        """  var heads = state.heads;
  var i, x;
  for (i = 0; i < heads; i++) {
    x = w * 0.35 + i * 36;
    ctx.strokeStyle = "#1f4b99";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(w * 0.22, h * 0.62);
    ctx.lineTo(x, h * 0.28);
    ctx.stroke();
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(x - 8, h * 0.2, 16, 16);
  }
""",
    ),
    _spec(
        "multi_query", "mqa-share", "Una sola llave para todas las consultas",
        "Multi-query attention uses one key head shared by every query head.",
        "1911.02150", r"multi-query", "query",
        "Multi-query deja una sola llave y varias consultas. Las consultas se multiplican; la llave no.",
        (
            ("¿Cada consulta trae su propia llave?", "comparten una"),
            ("¿Qué no crece cuando hay más consultas?", "la memoria de la llave"),
            ("¿Se comparten las consultas o la llave?", "la llave"),
        ),
        (("queries", "queries", 1, 8, 4, 1),),
        """  var queries = state.queries;
  var i, y;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.62, h * 0.4, 36, 36);
  for (i = 0; i < queries; i++) {
    y = 24 + i * ((h - 40) / 8);
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(40, y, 28, 16);
    ctx.strokeStyle = "#1f4b99";
    ctx.beginPath();
    ctx.moveTo(68, y + 8);
    ctx.lineTo(w * 0.62, h * 0.4 + 18);
    ctx.stroke();
  }
""",
    ),
    _spec(
        "logit_cap", "logit-cap", "El tope aplana el logit enorme",
        "Gemma soft-caps a logit so a huge value cannot dominate the softmax.",
        "2403.08295", r"soft-cap", "logit",
        "El soft-cap de Gemma aplana un logit enorme contra un tope. Debajo del tope, la curva casi no se entera.",
        (
            ("¿Un logit enorme se come el softmax?", "el tope lo aplana antes"),
            ("¿Qué parte de la curva se dobla?", "la que pasa el tope"),
            ("¿Se está cortando la probabilidad o el logit?", "el logit"),
        ),
        (("cap", "tope", 1, 8, 4, 0.25),),
        """  var cap = state.cap;
  var i, u, yv, x, y, e;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 32; i++) {
    u = -2 + (i / 32) * 12;
    e = Math.exp(2 * u / cap);
    yv = cap * ((e - 1) / (e + 1));
    x = 24 + (i / 32) * (w - 48);
    y = h * 0.55 - yv * (h * 0.05);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
""",
    ),
    _spec(
        "pre_norm", "prenorm-scale", "Pre-norm deja el atajo en uno",
        "Pre-norm puts the norm on the branch so the residual path stays near unit scale.",
        "2002.04745", r"pre-norm", "norm",
        "Pre-norm pone la norm en la rama y deja el atajo cerca de uno. Si la rama crece, el atajo sigue derecho.",
        (
            ("¿La norma está en el atajo o en la rama?", "en la rama"),
            ("¿Qué se queda en uno?", "el atajo"),
            ("¿Se está escalando la entrada o la rama?", "la rama"),
        ),
        (("scale", "rama", 0.2, 3, 1, 0.1),),
        """  var scale = state.scale;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(30, h * 0.55);
  ctx.lineTo(w - 30, h * 0.55);
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(w * 0.35, h * 0.55);
  ctx.lineTo(w * 0.55, h * 0.55 - scale * 28);
  ctx.lineTo(w * 0.7, h * 0.55);
  ctx.stroke();
""",
    ),
    _spec(
        "drop_path", "drop-path", "La probabilidad apaga ramas",
        "Stochastic depth drops a residual path with probability p during training.",
        "1603.09382", r"stochastic depth", "path",
        "Stochastic depth apaga un residual path con probabilidad p. Más p, más bloques que no se dibujan.",
        (
            ("¿Todas las capas se usan en cada paso?", "algunas se apagan"),
            ("¿Qué bloques desaparecen si p sube?", "los que caen bajo la probabilidad"),
            ("¿Se apaga el atajo o un peso suelto?", "el path residual"),
        ),
        (("p", "p", 0, 0.8, 0.3, 0.05),),
        """  var p = state.p;
  var i;
  for (i = 0; i < 8; i++) {
    if (i / 8 >= p) {
      ctx.fillStyle = "#1f4b99";
      ctx.fillRect(24 + i * ((w - 40) / 8), h * 0.4, (w - 40) / 8 - 6, 36);
    }
  }
""",
    ),
]


from rrm.liveart.wave5 import TAIL

EXTRA.extend(TAIL)
