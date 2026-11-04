// Three catalog claims whose control is the claim. Each keeps min/max/step/value
// so a 0.3 host still mounts them as sliders. kind is the 0.4 control.
export const NOSLIDER = [
  {
    source: "noslider",
    widget: {
      id: "giou-gap",
      topic: "giou",
      title: "Si no se tocan, IoU se queda en 0",
      explain: "Rezatofighi et al. 1902.09630: GIoU = IoU − |C\\(A∪B)|/|C|. C es la caja mínima que encierra a A y a B. Si no se tocan, IoU se queda en 0 y GIoU sigue bajando porque C crece. Arrastra B en x, en y o en diagonal: la zona plana de IoU es el plano. Estas dos cajas son un juguete, no COCO.",
      equation: "GIoU=IoU-\\frac{|C\\setminus(A\\cup B)|}{|C|}",
      anchor: "IoU has a plateau making it infeasible to optimize in the case of non-overlapping bounding boxes.",
      cite: "Rezatofighi et al., 1902.09630",
      questions: [
        {
          q: "Pon B en x = 100 y en y = 0. ¿Qué le pasa a IoU?",
          why: "no se tocan: IoU queda en 0 y GIoU ya es negativo",
        },
        {
          q: "Arrastra B hasta encimarlo con A. ¿IoU sigue en 0?",
          why: "en cuanto hay intersección, IoU sube y GIoU se le acerca",
        },
        {
          q: "Con IoU en 0, baja B sin moverlo en x. ¿GIoU se queda?",
          why: "no: C se hace más alta y GIoU baja aunque IoU no se mueva",
        },
        {
          q: "¿Estas barras son una medición de MS COCO?",
          why: "no: son las dos fórmulas sobre estas dos cajas de juguete",
        },
      ],
      controls: [
        { id: "bx", label: "B en x", kind: "drag", min: 0, max: 180, value: 100, step: 1 },
        { id: "by", label: "B en y", kind: "drag", min: 0, max: 130, value: 0, step: 1 },
      ],
      draw: `function draw(ctx, state, t) {
  var w = state.w, h = state.h, S = 64, ax = 48, ay = 78;
  var bx = ax + state.bx, by = ay + state.by;
  var ix0 = Math.max(ax, bx), iy0 = Math.max(ay, by);
  var ix1 = Math.min(ax + S, bx + S), iy1 = Math.min(ay + S, by + S);
  var iw = ix1 - ix0, ih = iy1 - iy0;
  if (iw < 0) iw = 0;
  if (ih < 0) ih = 0;
  var inter = iw * ih, union = S * S * 2 - inter, iou = inter / union;
  var cx0 = Math.min(ax, bx), cy0 = Math.min(ay, by);
  var cx1 = Math.max(ax + S, bx + S), cy1 = Math.max(ay + S, by + S);
  var area = (cx1 - cx0) * (cy1 - cy0);
  var giou = iou - (area - union) / area;
  function r2(v) { return Math.round(v * 100) / 100; }
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText("GIoU = IoU - |C sin (A union B)| / |C|", 16, 24);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = iou < 0.001 ? "#c4512c" : "#2e7d32";
  ctx.fillText(iou < 0.001 ? "IoU = 0: las cajas no se tocan" : "se tocan: IoU ya no esta en la meseta", 16, 46);
  ctx.fillStyle = "#e4d8bc";
  ctx.fillRect(cx0, cy0, cx1 - cx0, cy1 - cy0);
  ctx.strokeStyle = "#8a8175";
  ctx.lineWidth = 1;
  ctx.strokeRect(cx0, cy0, cx1 - cx0, cy1 - cy0);
  ctx.globalAlpha = 0.9;
  ctx.fillStyle = "#1f4b99";
  ctx.fillRect(ax, ay, S, S);
  ctx.fillStyle = "#c4512c";
  ctx.fillRect(bx, by, S, S);
  ctx.globalAlpha = 1;
  if (iw > 0 && ih > 0) {
    ctx.fillStyle = "#1d1a16";
    ctx.fillRect(ix0, iy0, iw, ih);
  }
  ctx.fillStyle = "#f6f3ec";
  ctx.font = "13px sans-serif";
  ctx.fillText("A", ax + 4, ay + 16);
  ctx.fillText("B", bx + 4, by + 16);
  var rx = 430, zy = 220, bh = 120;
  ctx.strokeStyle = "#1d1a16";
  ctx.beginPath();
  ctx.moveTo(rx, zy);
  ctx.lineTo(rx + 150, zy);
  ctx.stroke();
  if (iou >= 0.001) {
    ctx.fillStyle = "#1f4b99";
    ctx.fillRect(rx + 18, zy - iou * bh, 28, iou * bh);
  }
  ctx.fillStyle = "#c4512c";
  if (giou >= 0.001) ctx.fillRect(rx + 78, zy - giou * bh, 28, giou * bh);
  else if (giou < -0.001) ctx.fillRect(rx + 78, zy, 28, Math.min(64, -giou * bh));
  ctx.fillStyle = "#1d1a16";
  ctx.font = "14px sans-serif";
  ctx.fillText("IoU " + r2(iou), rx, 78);
  ctx.fillText("GIoU " + r2(giou), rx, 100);
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("azul A   coral B", rx, 126);
  ctx.fillText("beige = caja C", rx, 144);
  ctx.fillText("IoU", rx + 18, zy + 78);
  ctx.fillText("GIoU", rx + 72, zy + 78);
}`,
    },
  },
  {
    source: "noslider",
    widget: {
      id: "double-descent",
      topic: "double_descent",
      title: "Después del pico, el error vuelve a bajar",
      explain: "Nakkiran et al. 1912.02292: al crecer el modelo, el desempeño primero empeora y luego mejora. El pico está donde EMC = n, el umbral de interpolación. La curva es un esquema de esa frase, no la figura del paper. Elige qué sigue después del umbral: recién ahí aparece el segundo descenso.",
      equation: "\\mathrm{EMC}_{\\mathcal{D},\\epsilon}(\\mathcal{T}):=\\max\\{n\\mid\\mathbb{E}_{S\\sim\\mathcal{D}^{n}}[\\mathrm{Error}_{S}(\\mathcal{T}(S))]\\leq\\epsilon\\}",
      anchor: "as we increase model size, performance first gets worse and then gets better.",
      cite: "Nakkiran et al., 1912.02292",
      questions: [
        {
          q: "Pon el ancho en 6, antes del umbral. ¿El error está en el pico?",
          why: "no: a la izquierda el esquema todavía baja, como el clásico",
        },
        {
          q: "Sin elegir, pon el ancho en 24. ¿Ves el error de después?",
          why: "no: el marcador se frena en el umbral hasta que eliges",
        },
        {
          q: "Elige «vuelve a bajar». ¿Qué le pasa al error pasado el umbral?",
          why: "cae otra vez; las otras dos predicciones se quedan arriba",
        },
        {
          q: "¿Esta curva es la ResNet18 del paper en CIFAR-10?",
          why: "no: es un esquema de la frase; la figura medida no está aquí",
        },
      ],
      controls: [
        { id: "width", label: "ancho", min: 1, max: 28, value: 6, step: 1 },
        {
          id: "guess",
          label: "predicción",
          kind: "predict",
          prompt: "Después del umbral, ¿el error?",
          options: ["sigue subiendo", "se queda arriba", "vuelve a bajar"],
          answer: 3,
          min: 0,
          max: 3,
          value: 0,
          step: 1,
        },
      ],
      draw: `function draw(ctx, state, t) {
  var w = state.w, h = state.h, guess = Math.round(state.guess);
  var n = state.width, shown = guess === 0 && n > 12 ? 12 : n;
  function err(k) {
    if (k <= 6) return 0.7 - (k - 1) * 0.07;
    if (k <= 12) return 0.35 + (k - 6) * 0.07;
    return 0.77 - (k - 12) * 0.025;
  }
  function guessY(k) {
    if (guess === 1) return Math.min(0.95, 0.77 + (k - 12) * 0.04);
    if (guess === 2) return 0.77;
    return err(k);
  }
  var x0 = 46, y0 = 58, pw = 400, ph = 230;
  function X(k) { return x0 + 6 + (k - 1) / 27 * (pw - 16); }
  function Y(v) { return y0 + (1 - v) * ph; }
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(guess === 0 ? "¿qué hace el error después del umbral?" : "esquema, no la figura del paper", 16, 24);
  ctx.strokeStyle = "#cfc5b5";
  ctx.strokeRect(x0, y0, pw, ph);
  ctx.strokeStyle = "#c4512c";
  ctx.beginPath();
  ctx.moveTo(X(12), y0);
  ctx.lineTo(X(12), y0 + ph);
  ctx.stroke();
  ctx.font = "12px sans-serif";
  ctx.fillStyle = "#c4512c";
  ctx.fillText("umbral", X(12) + 4, y0 + 14);
  ctx.strokeStyle = "#1f4b99";
  ctx.lineWidth = 2;
  ctx.beginPath();
  var k, last = guess === 0 ? 12 : 28;
  for (k = 1; k <= last; k++) {
    if (k === 1) ctx.moveTo(X(k), Y(err(k)));
    else ctx.lineTo(X(k), Y(err(k)));
  }
  ctx.stroke();
  if (guess > 0) {
    ctx.strokeStyle = "#c4512c";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (k = 12; k <= 28; k++) {
      if (k === 12) ctx.moveTo(X(k), Y(guessY(k)));
      else ctx.lineTo(X(k), Y(guessY(k)));
    }
    ctx.stroke();
  }
  ctx.fillStyle = "#1d1a16";
  ctx.beginPath();
  ctx.arc(X(shown), Y(guess > 0 && shown > 12 ? err(shown) : err(shown)), 6, 0, 6.2832);
  ctx.fill();
  var names = ["", "sigue subiendo", "se queda arriba", "vuelve a bajar"];
  ctx.font = "14px sans-serif";
  ctx.fillText("error " + Math.round(err(shown) * 100) / 100, 470, 120);
  ctx.font = "13px sans-serif";
  if (guess === 0) {
    ctx.fillStyle = "#5c564c";
    ctx.fillText("elige para ver", 470, 148);
    ctx.fillText("el otro lado", 470, 168);
  } else if (guess === 3) {
    ctx.fillStyle = "#2e7d32";
    ctx.fillText("baja otra vez", 470, 148);
  } else {
    ctx.fillStyle = "#c4512c";
    ctx.fillText("tu línea queda alta", 470, 148);
    ctx.fillStyle = "#1f4b99";
    ctx.fillText("el esquema baja", 470, 170);
  }
  ctx.fillStyle = "#5c564c";
  ctx.font = "12px sans-serif";
  ctx.fillText(guess === 0 ? "sin predicción" : names[guess], 470, 210);
  ctx.fillText("ancho " + Math.round(n), 470, 230);
}`,
    },
  },
  {
    source: "noslider",
    widget: {
      id: "lottery-keep",
      topic: "lottery",
      title: "El boleto gana con su inicio original",
      explain: "Frankle y Carbin 1803.03635: el boleto es f(x; m⊙θ₀), la máscara podada devuelta a su inicio. Reiniciada al azar, f(x; m⊙θ′₀), ya no empata a la red densa. El acierto dibujado es un esquema de ese contraste, no una cifra del paper. 21% es un P_m que el texto muestra.",
      equation: "f(x;m\\odot\\theta_0)",
      anchor: "When randomly reinitialized, winning tickets perform far worse.",
      cite: "Frankle y Carbin, 1803.03635",
      questions: [
        {
          q: "Pon quedan en 21% con rebobinar encendido. ¿El acierto se cae?",
          why: "no: con el inicio original el esquema se sostiene",
        },
        {
          q: "Apaga rebobinar, en el mismo 21%. ¿Qué le pasa al acierto?",
          why: "cae: la misma máscara con un inicio nuevo ya no entrena igual",
        },
        {
          q: "Con rebobinar apagado, sube quedan a 100%. ¿Se acerca al denso?",
          why: "sí: sin podar, reiniciar no cambia la red completa",
        },
        {
          q: "¿El 0.9 del eje es el acierto de CIFAR del paper?",
          why: "no: el alto contra el bajo es el contraste; el número es esquema",
        },
      ],
      controls: [
        { id: "keep", label: "quedan %", min: 5, max: 100, value: 21, step: 1 },
        { id: "rewind", label: "rebobinar", kind: "toggle", min: 0, max: 1, value: 1, step: 1 },
      ],
      draw: `function draw(ctx, state, t) {
  var w = state.w, h = state.h, keep = state.keep, rewind = state.rewind >= 0.5 ? 1 : 0;
  function acc(p, back) {
    if (back) return p >= 20 ? 0.9 : 0.9 - (20 - p) * 0.028;
    return 0.9 - (100 - p) * 0.0055;
  }
  var x0 = 48, y0 = 56, pw = 400, ph = 220;
  function X(p) { return x0 + (p - 5) / 95 * pw; }
  function Y(v) { return y0 + (1 - (v - 0.2) / 0.8) * ph; }
  ctx.fillStyle = "#f6f3ec";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "15px sans-serif";
  ctx.fillText(rewind ? "f(x; m con theta0)  inicio original" : "f(x; m con theta nuevo)  reinicio al azar", 16, 24);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = rewind ? "#2e7d32" : "#c4512c";
  ctx.fillText(rewind ? "el boleto se sostiene al podar" : "la misma máscara, sin su inicio, cae", 16, 44);
  ctx.strokeStyle = "#cfc5b5";
  ctx.strokeRect(x0, y0, pw, ph);
  function curve(back, col, width) {
    var p;
    ctx.strokeStyle = col;
    ctx.lineWidth = width;
    ctx.beginPath();
    for (p = 5; p <= 100; p += 5) {
      if (p === 5) ctx.moveTo(X(p), Y(acc(p, back)));
      else ctx.lineTo(X(p), Y(acc(p, back)));
    }
    ctx.stroke();
  }
  curve(0, "#c4512c", rewind ? 1 : 3);
  curve(1, "#1f4b99", rewind ? 3 : 1);
  var yA = acc(keep, rewind);
  ctx.fillStyle = rewind ? "#1f4b99" : "#c4512c";
  ctx.beginPath();
  ctx.arc(X(keep), Y(yA), 6, 0, 6.2832);
  ctx.fill();
  ctx.fillStyle = "#e4d6c4";
  ctx.fillRect(480, 250, 120, 12);
  ctx.fillStyle = yA > 0.75 ? "#2e7d32" : "#c4512c";
  ctx.fillRect(480, 250, Math.max(2, 120 * (yA - 0.2) / 0.8), 12);
  ctx.fillStyle = "#1d1a16";
  ctx.font = "16px sans-serif";
  ctx.fillText("esquema " + Math.round(yA * 100) / 100, 480, 120);
  ctx.font = "13px sans-serif";
  ctx.fillStyle = "#5c564c";
  ctx.fillText("quedan " + Math.round(keep) + "%", 480, 148);
  ctx.fillText(rewind ? "rebobinado a theta0" : "inicio nuevo", 480, 170);
  ctx.fillText("azul: con theta0", 480, 210);
  ctx.fillText("coral: al azar", 480, 228);
  ctx.fillText("no es una cifra del paper", 48, 340);
}`,
    },
  },
];
