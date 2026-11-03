"""Último bloque para cerrar el banco en 100 casos."""

from rrm.liveart.wave2 import _spec


TAIL = [
    _spec(
        "swa_average", "swa-avg", "El promedio se queda en el centro",
        "SWA averages weights along the trajectory so the result sits in the middle of the cycle.",
        "1803.05407", r"\bswa\b", "average",
        "SWA average junta los pesos del ciclo. El punto azul es el promedio; los naranjas son los pasos.",
        (
            ("¿El resultado es el último peso?", "es el promedio del ciclo"),
            ("¿Qué se queda en el centro?", "el average"),
            ("¿Se promedian los gradientes o los pesos?", "los pesos"),
        ),
        (("take", "pasos", 2, 10, 5, 1),),
        """  var take = state.take;
  var i, x, y, sx, sy;
  sx = 0; sy = 0;
  for (i = 0; i < 10; i++) {
    x = w * 0.3 + Math.cos(i) * 70;
    y = h * 0.5 + Math.sin(i * 1.3) * 40;
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(x, y, 6, 6);
    if (i < take) { sx += x; sy += y; }
  }
  ctx.fillStyle = "#1f4b99";
  ctx.beginPath();
  ctx.arc(sx / take, sy / take, 8, 0, Math.PI * 2);
  ctx.fill();
""",
    ),
    _spec(
        "controlnet", "controlnet-zero", "La rama de condición sale de cero",
        "ControlNet adds a locked copy and a zero-initialized branch for the extra condition.",
        "2302.05543", r"\bcontrolnet\b", "controlnet",
        "ControlNet deja la rama de la condición en cero al inicio. El control la abre y la condición empieza a empujar.",
        (
            ("¿La condición mueve el resultado desde el primer paso?", "la rama sale de cero"),
            ("¿Qué crece cuando se abre la rama?", "el empujón de la condición"),
            ("¿Se entrena la copia o la rama nueva?", "la rama nueva"),
        ),
        (("gain", "rama", 0, 1, 0.4, 0.05),),
        """  var gain = state.gain;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(30, h * 0.55);
  ctx.lineTo(w - 30, h * 0.55);
  ctx.stroke();
  ctx.strokeStyle = "#c4512c";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(w * 0.4, h * 0.55);
  ctx.lineTo(w * 0.62, h * 0.55 - gain * 80);
  ctx.lineTo(w * 0.78, h * 0.55);
  ctx.stroke();
""",
    ),
    _spec(
        "ia3_scale", "ia3-scale", "Escala la llave, no le suma un rango",
        "IA3 scales key vectors instead of adding a low-rank update.",
        "2205.05638", r"\bia3\b", "scale",
        "IA3 scale multiplica la llave. No suma una matriz: la barra de la llave se estira.",
        (
            ("¿IA3 suma un rango bajo o multiplica?", "multiplica"),
            ("¿Qué se estira con la escala?", "la llave"),
            ("¿Cambia el número de parámetros como LoRA?", "no, solo escalas"),
        ),
        (("scale", "escala", 0.3, 2.4, 1, 0.05),),
        """  var scale = state.scale;
  var vals = [0.3, 0.7, 0.45, 0.9];
  var i, bh;
  for (i = 0; i < 4; i++) {
    bh = vals[i] * scale * h * 0.28;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(40 + i * 50, h * 0.8 - bh, 32, bh);
  }
""",
    ),
    _spec(
        "prefix_tune", "prefix-len", "El prefijo se antepone a la llave",
        "Prefix tuning prepends learned vectors to the keys and values and freezes the model.",
        "2101.00190", r"prefix tuning", "prefix",
        "Prefix tuning antepone vectores aprendidos. El prefix crece hacia la izquierda de la llave congelada.",
        (
            ("¿Se afinan todos los pesos?", "no, el modelo queda congelado"),
            ("¿Qué se alarga?", "el prefix"),
            ("¿El prefijo va en la entrada o en las llaves?", "en las llaves"),
        ),
        (("plen", "prefijo", 1, 8, 3, 1),),
        """  var plen = state.plen;
  var i;
  for (i = 0; i < plen; i++) {
    ctx.fillStyle = "#c4512c";
    ctx.fillRect(24 + i * 22, h * 0.4, 16, 28);
  }
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(24 + plen * 22, h * 0.4, 120, 28);
""",
    ),
    _spec(
        "mae_mask", "mae-ratio", "Enmascarar deja huecos por reconstruir",
        "MAE masks a large ratio of patches and reconstructs the missing pixels.",
        "2111.06377", r"\bmae\b", "mask",
        "MAE mask tapa una fracción de los parches. Más ratio, más huecos que el decoder tiene que rellenar.",
        (
            ("¿El modelo ve la imagen completa?", "ve solo los parches que quedan"),
            ("¿Qué crece con el ratio?", "los huecos"),
            ("¿Se reconstruye lo visible o lo tapado?", "lo tapado"),
        ),
        (("ratio", "ratio", 0.1, 0.9, 0.75, 0.05),),
        """  var ratio = state.ratio;
  var i, hidden;
  hidden = Math.round(ratio * 12);
  for (i = 0; i < 12; i++) {
    if (i >= hidden) {
      ctx.fillStyle = "#1f4b99";
      ctx.fillRect(20 + (i % 6) * 36, 40 + Math.floor(i / 6) * 40, 30, 30);
    }
  }
""",
    ),
    _spec(
        "moco_queue", "moco-queue", "La cola guarda negativos viejos",
        "MoCo keeps a queue of negatives of length K so the batch can stay small.",
        "1911.05722", r"\bmoco\b", "queue",
        "MoCo queue guarda negativos de pasos anteriores. K es el largo de esa cola.",
        (
            ("¿Los negativos salen solo del batch de ahora?", "también de la cola"),
            ("¿Qué se alarga con K?", "la cola"),
            ("¿Se está agrandando el batch o la memoria de negativos?", "la memoria"),
        ),
        (("k", "cola", 2, 14, 6, 1),),
        """  var k = state.k;
  var i;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(30, h * 0.45, 28, 28);
  for (i = 0; i < k; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(80 + i * 22, h * 0.45, 16, 28);
  }
""",
    ),
    _spec(
        "byol_pred", "byol-stop", "Una rama no recibe gradiente",
        "BYOL trains a predictor against a stopped target branch and uses no negative pairs.",
        "2006.07733", r"\bbyol\b", "byol",
        "BYOL para el gradiente en una rama. El predictor persigue a ese blanco quieto, sin negativos.",
        (
            ("¿Hacen falta negativos?", "no"),
            ("¿Qué rama no recibe gradiente?", "el blanco"),
            ("¿Quién persigue a quién?", "el predictor al blanco"),
        ),
        (("gap", "hueco", 0.1, 1, 0.45, 0.05),),
        """  var gap = state.gap;
  ctx.fillStyle = "#1f4b99";
  ctx.beginPath();
  ctx.arc(w * 0.3, h * 0.55, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#c4512c";
  ctx.beginPath();
  ctx.arc(w * 0.3 + 40 + gap * 160, h * 0.55, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#1c1915";
  ctx.beginPath();
  ctx.moveTo(w * 0.3 + 12, h * 0.55);
  ctx.lineTo(w * 0.3 + 28 + gap * 160, h * 0.55);
  ctx.stroke();
""",
    ),
    _spec(
        "qk_norm", "qk-norm", "La norma baja el producto",
        "QK-Norm divides queries and keys by their norm before the dot product.",
        "2010.04245", r"qk-norm", "norm",
        "QK-Norm divide cada vector por su norma. El producto deja de crecer solo porque los vectores eran largos.",
        (
            ("¿Un vector más largo debería dar más atención?", "después de la norma, no"),
            ("¿Qué se está dividiendo?", "la norma del vector"),
            ("¿El producto de la derecha sigue el largo?", "no, está normalizado"),
        ),
        (("length", "largo", 0.4, 3, 1.4, 0.1),),
        """  var length = state.length;
  var raw = length * 1.2;
  var normed = 1.2;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - raw * 40, 50, raw * 40);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(120, h * 0.8 - normed * 40, 50, normed * 40);
""",
    ),
    _spec(
        "relu6", "relu6-cap", "El tope corta la unidad",
        "ReLU6 caps the activation at a ceiling so the unit cannot grow without bound.",
        "1704.04861", r"\brelu6\b", "relu6",
        "ReLU6 corta la activación en un tope. Debajo del tope sigue a ReLU; arriba se queda plano.",
        (
            ("¿Una activación enorme sigue creciendo?", "no, se queda en el tope"),
            ("¿Qué tramo es plano?", "el que pasa el tope"),
            ("¿Debajo del tope es ReLU?", "sí"),
        ),
        (("cap", "tope", 1, 8, 6, 0.25),),
        """  var cap = state.cap;
  var i, u, v, x, y;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= 24; i++) {
    u = -1 + (i / 24) * 10;
    v = u < 0 ? 0 : (u > cap ? cap : u);
    x = 24 + (i / 24) * (w - 48);
    y = h * 0.8 - v * (h * 0.07);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
""",
    ),
    _spec(
        "fpn_level", "fpn-level", "Lo fino recibe lo grueso",
        "FPN adds a top-down path so a fine level receives the upsampled coarse map.",
        "1612.03144", r"\bfpn\b", "level",
        "FPN baja un mapa grueso al level fino. El control elige hasta qué nivel llega esa flecha.",
        (
            ("¿El mapa fino se queda solo?", "recibe lo que baja de arriba"),
            ("¿Qué se alarga al bajar de nivel?", "el camino de arriba hacia abajo"),
            ("¿Se está fusionando la resolución o el batch?", "la resolución"),
        ),
        (("level", "nivel", 1, 4, 2, 1),),
        """  var level = state.level;
  var i, y, wide;
  for (i = 0; i < 4; i++) {
    wide = 40 + i * 36;
    y = 30 + i * 40;
    ctx.fillStyle = "#d9d3c7";
    ctx.fillRect(w * 0.5 - wide / 2, y, wide, 24);
  }
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(w * 0.5, 30);
  ctx.lineTo(w * 0.5, 30 + level * 48);
  ctx.stroke();
""",
    ),
    _spec(
        "cutout", "cutout-side", "El cuadrado tapado crece",
        "Cutout erases a square of a chosen side so the classifier cannot rely on one patch.",
        "1708.04552", r"\bcutout\b", "cutout",
        "Cutout borra un cuadrado. El lado del hueco es el control: más lado, menos imagen útil.",
        (
            ("¿Se tapa un píxel o una región?", "un cuadrado"),
            ("¿Qué crece con el lado?", "el hueco"),
            ("¿La etiqueta cambia con el área tapada?", "la imagen sí, la etiqueta no"),
        ),
        (("side", "lado", 0.1, 0.8, 0.35, 0.05),),
        """  var side = state.side;
  var s = side * (w * 0.4);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(30, 30, w * 0.5, h * 0.7);
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(50, 50, s, s);
""",
    ),
    _spec(
        "dice_loss", "dice-overlap", "El solape es el peso",
        "Dice loss scores a mask by the overlap between prediction and target.",
        "1606.04797", r"dice loss", "dice",
        "Dice loss mira el solape. Si la predicción se corre, el overlap baja y la pérdida sube.",
        (
            ("¿Una máscara que solo se corre un poco sigue bien?", "el solape baja"),
            ("¿Qué mide el control?", "cuánto se pisan las dos máscaras"),
            ("¿Se está viendo el borde o el área compartida?", "el área compartida"),
        ),
        (("shift", "corrimiento", 0, 80, 20, 2),),
        """  var shift = state.shift;
  ctx.fillStyle = "#1f4b99";
  ctx.globalAlpha = 0.8;
  ctx.fillRect(40, h * 0.35, 120, 50);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40 + shift, h * 0.35, 120, 50);
  ctx.globalAlpha = 1;
""",
    ),
    _spec(
        "h2o_cache", "h2o-budget", "El presupuesto se queda con los heavy hitters",
        "H2O keeps heavy-hitter tokens in a cache budget and drops the rest.",
        "2306.14048", r"\bh2o\b", "cache",
        "H2O cache guarda solo un presupuesto de tokens. Los heavy hitters entran; el resto se cae.",
        (
            ("¿Cabe toda la historia en el cache?", "solo el presupuesto"),
            ("¿A quién se conserva?", "a los heavy hitters"),
            ("¿Qué se cae cuando el presupuesto baja?", "los tokens de menos peso"),
        ),
        (("budget", "cupo", 1, 8, 4, 1),),
        """  var budget = state.budget;
  var score = [0.9, 0.7, 0.55, 0.4, 0.3, 0.2, 0.12, 0.05];
  var i, bh;
  for (i = 0; i < 8; i++) {
    bh = score[i] * h * 0.5;
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * ((w - 30) / 8), (i < budget ? h * 0.55 : h * 0.82) - bh, (w - 30) / 8 - 6, bh);
  }
""",
    ),
    _spec(
        "performer_m", "performer-m", "Más rasgos, más cerca del softmax",
        "Performer approximates softmax attention with m random features.",
        "2009.14794", r"\bperformer\b", "performer",
        "Performer cambia el softmax por m rasgos al azar. Más m, la barra de error se acorta.",
        (
            ("¿Hace falta el softmax exacto?", "se aproxima con rasgos"),
            ("¿Qué baja cuando m crece?", "el error de la aproximación"),
            ("¿Se está viendo el costo o el error?", "el error"),
        ),
        (("m", "rasgos", 1, 16, 4, 1),),
        """  var m = state.m;
  var err = h * 0.55 * (1 / m);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - err, 70, err);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(140, h * 0.8 - m * 6, 70, m * 6);
""",
    ),
    _spec(
        "rwkv_time", "rwkv-decay", "El estado se apaga por canal",
        "RWKV mixes a time-decayed state with the current token, and the decay is per channel.",
        "2305.13048", r"\brwkv\b", "rwkv",
        "RWKV decay apaga el estado antes de sumar el token nuevo. Un decay chico olvida; uno alto acumula.",
        (
            ("¿El estado viejo entra completo?", "primero se multiplica por el decay"),
            ("¿Qué canal se queda más alto?", "el de decay más alto"),
            ("¿Se está mezclando atención o un estado?", "un estado"),
        ),
        (("decay", "decay", 0.4, 0.95, 0.7, 0.05),),
        """  var decay = state.decay;
  var i, s, bh;
  s = 0;
  for (i = 0; i < 10; i++) {
    s = s * decay + 0.35;
  }
  bh = s * h * 0.15;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(40, h * 0.8 - bh, 80, bh);
""",
    ),
    _spec(
        "s4_kernel", "s4-kernel", "El kernel largo sigue barato",
        "S4 uses a structured state space so a long convolution kernel stays cheap to apply.",
        "2111.00396", r"structured state space", "kernel",
        "S4 arma un kernel de convolución largo sin pagar el largo completo. El control estira ese kernel.",
        (
            ("¿Un kernel largo tiene que ser caro?", "la estructura lo deja barato"),
            ("¿Qué se estira?", "el kernel"),
            ("¿Se está viendo la recurrencia o la convolución?", "la convolución"),
        ),
        (("span", "largo", 4, 28, 12, 1),),
        """  var span = state.span;
  var i, x, y;
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (i = 0; i <= span; i++) {
    x = 24 + i * ((w - 48) / 28);
    y = h * 0.7 - Math.exp(-i / 6) * h * 0.4;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
""",
    ),
    _spec(
        "deepnorm", "deepnorm-alpha", "Alpha agranda el atajo",
        "DeepNet uses DeepNorm, which scales the residual branch by alpha so a deep stack does not wash out.",
        "2203.00555", r"\bdeepnorm\b", "deepnorm",
        "DeepNorm multiplica el atajo por alpha. Alpha grande deja pasar la entrada aunque la pila sea honda.",
        (
            ("¿Una pila honda se traga la entrada?", "alpha se lo impide"),
            ("¿Qué barra es el atajo?", "la que crece con alpha"),
            ("¿Se escala la rama o el atajo?", "el atajo"),
        ),
        (("alpha", "alpha", 0.5, 4, 2, 0.25),),
        """  var alpha = state.alpha;
  var branch = h * 0.2;
  var skip = alpha * h * 0.12;
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(40, h * 0.8 - branch, 50, branch);
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(120, h * 0.8 - skip, 50, skip);
""",
    ),
    _spec(
        "t5_buckets", "t5-buckets", "Un bucket cubre varias distancias",
        "T5 relative position buckets share one bias across a range of distances.",
        "1910.10683", r"position buckets", "buckets",
        "Los position buckets de T5 juntan varias distancias en un mismo sesgo. Menos buckets, cada uno cubre más.",
        (
            ("¿Cada distancia tiene su propio sesgo?", "las de un bucket comparten uno"),
            ("¿Qué se ensancha si hay menos buckets?", "el rango de cada uno"),
            ("¿Se está viendo la posición absoluta o la relativa?", "la relativa"),
        ),
        (("buckets", "buckets", 2, 8, 4, 1),),
        """  var buckets = state.buckets;
  var i, x, bw;
  bw = (w - 40) / buckets;
  for (i = 0; i < buckets; i++) {
    x = 20 + i * bw;
    ctx.fillStyle = i % 2 === 0 ? "#1f4b99" : "#c4512c";
    ctx.fillRect(x, h * 0.4, bw - 4, 36);
  }
""",
    ),
    _spec(
        "bigbird", "bigbird-random", "Unos tokens al azar salen de la ventana",
        "BigBird adds a few random tokens on top of a local window.",
        "2007.14062", r"\bbigbird\b", "bigbird",
        "BigBird suma tokens random a la ventana local. Esos puntos saltan fuera de la banda.",
        (
            ("¿Solo se atiende a los vecinos?", "también a unos tokens random"),
            ("¿Qué puntos salen de la banda?", "los random"),
            ("¿La banda local desaparece?", "no, se queda"),
        ),
        (("extra", "azar", 0, 6, 2, 1),),
        """  var extra = state.extra;
  var i;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(30, h * 0.45, w * 0.45, 24);
  for (i = 0; i < extra; i++) {
    ctx.fillStyle = "#c4512c";
    ctx.beginPath();
    ctx.arc(w * 0.62 + i * 22, h * 0.3 + (i % 2) * 40, 7, 0, Math.PI * 2);
    ctx.fill();
  }
""",
    ),
    _spec(
        "linformer", "linformer-k", "Las llaves se proyectan a k",
        "Linformer projects the keys down to a length k before attention.",
        "2006.04768", r"\blinformer\b", "linformer",
        "Linformer proyecta las llaves a un largo k. La fila de llaves se acorta y la atención mira esa fila.",
        (
            ("¿La atención mira todas las posiciones?", "mira las k proyectadas"),
            ("¿Qué se acorta?", "la fila de llaves"),
            ("¿Se proyectan las consultas o las llaves?", "las llaves"),
        ),
        (("k", "k", 2, 16, 6, 1),),
        """  var k = state.k;
  var i;
  for (i = 0; i < 16; i++) {
    ctx.fillStyle = "#d9d3c7";
    ctx.fillRect(20 + i * 18, 40, 12, 16);
  }
  for (i = 0; i < k; i++) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(20 + i * 18, 80, 12, 28);
  }
""",
    ),
    _spec(
        "ciou", "ciou-dist", "La distancia entre centros suma castigo",
        "CIoU adds a center-distance penalty on top of IoU.",
        "1911.08287", r"\bciou\b", "ciou",
        "CIoU suma un castigo por la distancia entre centros, además del IoU. Si los centros se separan, la barra del castigo sube.",
        (
            ("¿Dos cajas con el mismo IoU son igual de buenas?", "no, si los centros están lejos"),
            ("¿Qué barra sube al separar los centros?", "el castigo"),
            ("¿Se está midiendo solo el solape?", "el solape y la distancia"),
        ),
        (("dist", "distancia", 0, 160, 40, 4),),
        """  var dist = state.dist;
  ctx.strokeStyle = "#1f4b99";
  ctx.strokeRect(40, h * 0.4, 70, 50);
  ctx.strokeStyle = "#c4512c";
  ctx.strokeRect(40 + dist, h * 0.4, 70, 50);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(w * 0.72, h * 0.75 - dist * 0.4, 28, Math.max(4, dist * 0.4));
""",
    ),
]
