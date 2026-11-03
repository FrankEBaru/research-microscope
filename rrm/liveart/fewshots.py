"""Cuatro widgets de oro. El prompt de código los muestra completos.

Son la emulación de lo que Muse Code debería emitir (fase 1, sin Meta).
RRM-80 puede sustituir el draw; la forma JSON no cambia.
"""

import textwrap


def _src(text: str) -> str:
    return textwrap.dedent(text).strip()


def _knob(kid, label, lo, hi, value, step):
    return {"id": kid, "label": label, "min": lo, "max": hi, "value": value, "step": step}


DRAWS = {
    "positional_encoding": {
        "title": "La base cambia el ritmo de la onda",
        "controls": [
            _knob("base", "base", 10, 100000, 10000, 10),
            _knob("dim", "par i", 0, 8, 4, 1),
        ],
        "draw": _src(
            """\
            function draw(ctx, state, t) {
              var w = state.w, h = state.h, base = state.base, i = state.dim;
              var freq = 1 / Math.pow(base, (2 * i) / 64);
              var x, pos, y;
              ctx.clearRect(0, 0, w, h);
              ctx.fillStyle = "#f6f3ec";
              ctx.fillRect(0, 0, w, h);
              ctx.beginPath();
              ctx.lineWidth = 2;
              ctx.strokeStyle = "#1f4b99";
              for (x = 0; x < w; x++) {
                pos = (x / (w - 1)) * 64;
                y = h * 0.55 - Math.sin(pos * freq + t * 0.6) * (h * 0.32);
                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
              }
              ctx.stroke();
            }
            """
        ),
    },
    "softmax_temperature": {
        "title": "La temperatura afila el softmax",
        "controls": [_knob("temp", "temperatura", 0.05, 5, 1, 0.05)],
        "draw": _src(
            """\
            function draw(ctx, state, t) {
              var w = state.w, h = state.h, temp = state.temp;
              var logits = [1.2, 0.4, -0.2, -0.8];
              var i, m = logits[0], exps = [], s = 0, p, bw, bh, gap;
              if (temp < 0.05) temp = 0.05;
              for (i = 1; i < logits.length; i++) if (logits[i] > m) m = logits[i];
              for (i = 0; i < logits.length; i++) {
                exps[i] = Math.exp((logits[i] - m) / temp);
                s += exps[i];
              }
              ctx.clearRect(0, 0, w, h);
              ctx.fillStyle = "#f6f3ec";
              ctx.fillRect(0, 0, w, h);
              gap = 12;
              bw = (w - gap * (logits.length + 1)) / logits.length;
              for (i = 0; i < logits.length; i++) {
                p = exps[i] / s;
                bh = p * (h - 36);
                ctx.fillStyle = i === 0 ? "#c4512c" : "#1f4b99";
                ctx.fillRect(gap + i * (bw + gap), h - 16 - bh, bw, bh);
              }
            }
            """
        ),
    },
    "attention_scale": {
        "title": "Dividir entre la raíz aplana el peso",
        "controls": [_knob("d", "d_k", 4, 256, 64, 4)],
        "draw": _src(
            """\
            function draw(ctx, state, t) {
              var w = state.w, h = state.h, d = state.d;
              var raw = [1, 0.4, 0, -0.3];
              var s = Math.sqrt(d < 1 ? 1 : d);
              var grown = [], flat = [], i, gap, bw, x;
              function probs(xs) {
                var m = xs[0], k, out = [], acc = 0;
                for (k = 1; k < xs.length; k++) if (xs[k] > m) m = xs[k];
                for (k = 0; k < xs.length; k++) { out[k] = Math.exp(xs[k] - m); acc += out[k]; }
                for (k = 0; k < xs.length; k++) out[k] = out[k] / acc;
                return out;
              }
              for (i = 0; i < raw.length; i++) { grown[i] = raw[i] * s; flat[i] = raw[i]; }
              var top = probs(grown), bot = probs(flat);
              ctx.clearRect(0, 0, w, h);
              ctx.fillStyle = "#f6f3ec";
              ctx.fillRect(0, 0, w, h);
              gap = 8;
              bw = (w - gap * (raw.length + 1)) / raw.length;
              for (i = 0; i < raw.length; i++) {
                x = gap + i * (bw + gap);
                ctx.fillStyle = "#c4512c";
                ctx.fillRect(x, h * 0.46 - top[i] * (h * 0.40), bw, top[i] * (h * 0.40));
                ctx.fillStyle = "#1f4b99";
                ctx.fillRect(x, h * 0.96 - bot[i] * (h * 0.40), bw, bot[i] * (h * 0.40));
              }
            }
            """
        ),
    },
    "stddev": {
        "title": "Sigma es el ancho de la nube",
        "controls": [_knob("sigma", "sigma", 0.25, 4, 1, 0.05)],
        "draw": _src(
            """\
            function draw(ctx, state, t) {
              var w = state.w, h = state.h, sigma = state.sigma;
              var pts = [-1.2, -0.4, 0.1, 0.8, 1.5];
              var mid = h * 0.55, band = sigma * 22, i, x, y;
              ctx.clearRect(0, 0, w, h);
              ctx.fillStyle = "#f6f3ec";
              ctx.fillRect(0, 0, w, h);
              ctx.fillStyle = "#d9e3f5";
              ctx.fillRect(0, mid - band, w, band * 2);
              ctx.strokeStyle = "#1f4b99";
              ctx.lineWidth = 1;
              ctx.beginPath();
              ctx.moveTo(0, mid);
              ctx.lineTo(w, mid);
              ctx.stroke();
              ctx.fillStyle = "#c4512c";
              for (i = 0; i < pts.length; i++) {
                x = (i + 1) * w / (pts.length + 1);
                y = mid - pts[i] * sigma * 22;
                ctx.beginPath();
                ctx.arc(x, y, 4, 0, Math.PI * 2);
                ctx.fill();
              }
            }
            """
        ),
    },
}
