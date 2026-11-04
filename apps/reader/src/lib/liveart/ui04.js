// rrm-widget/0.4 helpers (ui.*). Engine builtins: the model never writes them.
// The same function runs in the verifier (run.js, over a recording stage) and inside the iframe
// (sandbox.js embeds makeUI.toString()), so it stays plain ES5 with no imports.
// Coordinates are CSS px of the canvas (state.w x state.h). The host already scaled the backing
// store to devicePixelRatio. Rules R1-R10: rrm/liveart/CONTRACT.md, section rrm-widget/0.4.
//
// makeUI(ctx, widget, opts) -> { ui, gctx, flush, result, fill, fmtRead }
//   ctx  : the real 2D context (or the verifier stage). Only the helpers use it.
//   gctx : what the draw receives: the closed method list, and it records geometry
//          (strokes >= 1.5 px, dots, bars) so ui.label does not cover it.
//   opts : { w, h, scale, mute, colors, v04 }. With v04, gctx.fillText is not drawn and is
//          counted in report.free_text (R1: the draw writes no text).

export const UI_METHODS = ["area", "axes", "label", "mark", "readout", "say", "fmt", "font", "clip", "unclip", "handle", "pick", "tip", "mix"];
export const UI_FIELDS = ["c", "lw", "mute"];

// Default colors for the verifier. The host passes the resolved B1 tokens instead.
export const UI_COLORS = {
  bg: "#ffffff", ink: "#1d1a16", ink2: "#5a5348", ink3: "#6b6357", rule: "#e2d9c8", rule2: "#cfc4b0",
  soft: "#f6f1e7", track: "#efe8da", ref: "#8c8271", hl: "rgba(255,225,77,.38)",
  c1: "#0b6782", c2: "#b4501f", c3: "#7b4a8c", c4: "#7d6418",
};

export function makeUI(ctx, widget, opts) {
  var W = opts.w, H = opts.h, SCALE = opts.scale || 1, MUTE = !!opts.mute;
  var C = opts.colors;
  var FONT = '"RRM UI", "Instrument Sans", ui-sans-serif, system-ui, sans-serif';
  var ROLE = { tick: "500 11px " + FONT, axis: "600 11px " + FONT, label: "600 12px " + FONT, mark: "600 11px " + FONT, big: "600 14px " + FONT };
  var LIM = { labels: 3, marks: 2, soft: 24, hard: 36, gap: 6 };
  var areas = {}, specs = {}, i;
  var segs = [], hairs = [], blobs = [], placed = [], queue = [], markQ = [];
  var res = { readouts: {}, say: null, cmarks: [], handles: [], picks: [], tips: [], report: { labels: 0, dropped: [], marks_out: [], over_budget: 0, cut: [] } };
  (widget.areas || [{ id: "main" }]).forEach(function (a) { specs[a.id] = a; });

  // ── formato ────────────────────────────────────────────────
  function minus(s) { return String(s).replace(/^-/, "−"); }
  function fmt(v, d) { if (!isFinite(v)) return "—"; var r = (+v).toFixed(d == null ? 2 : d); if (/^-0(\.0+)?$/.test(r)) r = r.slice(1); return minus(r); }
  function decFor(step) { var d = Math.max(0, -Math.floor(Math.log10(step) + 1e-9)); if (Math.abs(step * Math.pow(10, d) - Math.round(step * Math.pow(10, d))) > 1e-6) d += 1; return d; }
  function tickText(ax, v, step) {
    if (ax.format === "pct") return fmt(v * 100, Math.max(0, decFor(step * 100))) + "%";
    if (ax.log) { var e = Math.round(Math.log10(v)); return Math.abs(Math.log10(v) - e) < 1e-9 && (e > 3 || e < -2) ? "1e" + e : minus(+v.toPrecision(3)); }
    return fmt(v, decFor(step)) + (ax.unit ? ax.unit : "");
  }
  function niceTicks(min, max, count) {
    var span = max - min, step = Math.pow(10, Math.floor(Math.log10(span / Math.max(1, count)))), err = span / count / step;
    if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
    var out = [], v = Math.ceil(min / step - 1e-9) * step;
    for (; v <= max + step * 1e-9; v += step) out.push(+v.toFixed(12));
    return { t: out, step: step };
  }
  function logTicks(min, max) {
    var out = [], e; for (e = Math.ceil(Math.log10(min) - 1e-9); e <= Math.floor(Math.log10(max) + 1e-9); e++) out.push(Math.pow(10, e));
    if (out.length < 3) { var more = []; for (e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) [1, 2, 5].forEach(function (m) { var v = m * Math.pow(10, e); if (v >= min * 0.999 && v <= max * 1.001) more.push(v); }); out = more; }
    return { t: out, step: 1 };
  }
  function cut(s, field) {
    s = String(s);
    if (s.length > LIM.hard) { res.report.cut.push({ field: field, len: s.length, action: "ellipsis" }); s = s.slice(0, LIM.hard - 1).replace(/\s+\S*$/, "") + "…"; }
    return s;
  }
  // baja un paso de fuente y, si aún no cabe, corta en «…» (se reporta)
  function fitText(text, maxw, fonts) {
    var i2; for (i2 = 0; i2 < fonts.length; i2++) if (tw(text, fonts[i2]) <= maxw) return { text: text, font: fonts[i2] };
    var f = fonts[fonts.length - 1], t2 = text; while (t2.length > 1 && tw(t2 + "\u2026", f) > maxw) t2 = t2.slice(0, -1);
    res.report.cut.push({ field: "cat", len: text.length, action: "ellipsis" }); return { text: t2 + "\u2026", font: f };
  }
  function tw(text, font) { ctx.font = font; return ctx.measureText(text).width; }

  // ── áreas ─────────────────────────────────────────────────
  function area(id) {
    id = id || "main";
    if (areas[id]) return areas[id];
    var sp = specs[id] || { id: id }, r = sp.rect || [0, 0, 1, 1], P = sp.bleed ? 0 : 10;
    if (!Array.isArray(r)) r = (W < 440 && r.narrow) ? r.narrow : r.wide;
    var o = { x: r[0] * W + P, y: r[1] * H + P, w: r[2] * W - 2 * P, h: r[3] * H - 2 * P };
    var ax = sp.axes === false ? null : sp.x, ay = sp.axes === false ? null : sp.y, L = 0, B = 0, T = 0, R = 0;
    if (ay && !ay.cats) {
      if (!MUTE) {
        var yt = ay.log ? logTicks(ay.min, ay.max) : niceTicks(ay.min, ay.max, Math.max(2, Math.min(6, Math.floor(o.h / 34))));
        var mw = 0; yt.t.forEach(function (v) { mw = Math.max(mw, tw(tickText(ay, v, yt.step), ROLE.tick)); });
        L = Math.ceil(mw) + 17; T = ay.label ? 18 : 6;
      } else { L = 2; T = 2; }
    }
    if (ax) { B = MUTE ? (ax.cats ? 4 : 2) : 6 + 12 + (ax.sub ? 13 : 0); R = MUTE ? 2 : 4; }
    var a = { id: id, x: Math.round(o.x + L), y: Math.round(o.y + T), w: Math.round(o.w - L - R), h: Math.round(o.h - T - B), spec: sp };
    a.x1 = a.x + a.w; a.y1 = a.y + a.h;
    ax = sp.x; ay = sp.y;
    if (ax && ax.cats) { a.n = ax.cats.length; a.band = a.w / a.n; a.X = function (k) { return a.x + (k + 0.5) * a.band; }; }
    else if (ax) a.X = scale(ax, a.x, a.x1); else a.X = function (v) { return a.x + v * a.w; };
    if (ay) a.Y = scale(ay, a.y1, a.y); else a.Y = function (v) { return a.y1 - v * a.h; };
    areas[id] = a; return a;
  }
  function scale(ax, p0, p1) {
    if (ax.log) { var l0 = Math.log(ax.min), l1 = Math.log(ax.max); return function (v) { return p0 + (Math.log(v) - l0) / (l1 - l0) * (p1 - p0); }; }
    return function (v) { return p0 + (v - ax.min) / (ax.max - ax.min) * (p1 - p0); };
  }

  // ── ejes (marcas «bonitas» 1-2-5, cifras a 11 px, título corto) ──
  function axes(id, o) {
    if (typeof o === "boolean") o = { grid: o };
    o = o || {};
    var a = area(id), sp = a.spec, ax = sp.x, ay = sp.y;
    ctx.save(); ctx.lineWidth = 1; ctx.setLineDash([]);
    if (ay && !ay.cats) {
      var yt = ay.log ? logTicks(ay.min, ay.max) : niceTicks(ay.min, ay.max, Math.max(2, Math.min(6, Math.floor(a.h / 34))));
      yt.t.forEach(function (v) {
        var y = Math.round(a.Y(v)) + 0.5;
        if (o.grid !== false) { ctx.strokeStyle = C.rule; ctx.beginPath(); ctx.moveTo(a.x, y); ctx.lineTo(a.x1, y); ctx.stroke(); for (var gx = a.x; gx <= a.x1; gx += 6) hairs.push([gx, y]); }
        if (!MUTE) { ctx.font = ROLE.tick; ctx.fillStyle = C.ink3; ctx.textAlign = "right"; ctx.textBaseline = "middle"; ctx.fillText(tickText(ay, v, yt.step), a.x - 13, y); }
      });
      if (ay.label && !MUTE) { ctx.font = ROLE.axis; ctx.fillStyle = C.ink2; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic"; ctx.fillText(cut(ay.label, "axis"), a.x - 0, a.y - 9); }
    }
    if (ax) {
      var y0 = Math.round(a.y1) + 0.5;
      ctx.strokeStyle = C.rule2; ctx.beginPath(); ctx.moveTo(a.x, y0); ctx.lineTo(a.x1, y0); ctx.stroke();
      if (!MUTE) {
        ctx.font = ROLE.tick; ctx.textBaseline = "top";
        var titleBox = null;
        if (ax.label && !ax.cats) {
          var tt = cut(ax.label, "axis"), ww = tw(tt, ROLE.axis);
          titleBox = { x0: a.x1 - ww, x1: a.x1 + 2 };
          ctx.font = ROLE.axis; ctx.fillStyle = C.ink2; ctx.textAlign = "right"; ctx.fillText(tt, a.x1, y0 + 6);
        }
        if (ax.cats) {
          ax.cats.forEach(function (name, k) {
            var cx = a.X(k);
            var fitc = fitText(cut(name, "cat"), a.band - 6, [ROLE.label, ROLE.tick]);
            ctx.font = fitc.font; ctx.fillStyle = (ax.colors && ax.colors[k]) ? C[ax.colors[k]] || C.ink : C.ink; ctx.textAlign = "center"; ctx.fillText(fitc.text, cx, y0 + 6);
            if (ax.sub) { var fits = fitText(cut(ax.sub[k], "cat"), a.band - 6, [ROLE.tick]); ctx.font = fits.font; ctx.fillStyle = C.ink3; ctx.fillText(fits.text, cx, y0 + 20); }
          });
        } else {
          var xt = ax.log ? logTicks(ax.min, ax.max) : niceTicks(ax.min, ax.max, Math.max(2, Math.min(7, Math.floor(a.w / 64))));
          ctx.font = ROLE.tick; ctx.fillStyle = C.ink3; ctx.textAlign = "center";
          var last = -1e9;
          xt.t.forEach(function (v) {
            var x = Math.round(a.X(v)), s = tickText(ax, v, xt.step), ww2 = tw(s, ROLE.tick), x0 = x - ww2 / 2, x1 = x + ww2 / 2;
            if (x0 < 2) { x0 = 2; x1 = 2 + ww2; }
            if (x1 > W - 2) { x1 = W - 2; x0 = x1 - ww2; }
            if (titleBox && x1 > titleBox.x0 - 8) return;
            if (x0 < last + 8) return;
            ctx.strokeStyle = C.rule2; ctx.beginPath(); ctx.moveTo(x + 0.5, y0); ctx.lineTo(x + 0.5, y0 + 4); ctx.stroke();
            ctx.textAlign = "left"; ctx.fillText(s, x0, y0 + 6); last = x1;
          });
        }
      }
    }
    ctx.restore();
  }

  // ── rótulos: medir, evitar choques, recortar al lienzo; si no cabe, no se pinta y se reporta ──
  function label(text, x, y, o, align, size) {
    if (typeof o === "string" || o == null) o = { color: o || undefined, align: align || undefined, size: size || undefined };
    if (MUTE) return;
    if (queue.length >= LIM.labels) { res.report.over_budget++; return; }
    queue.push({ text: cut(text, "label"), x: x, y: y, color: o.color, prefer: o.align || o.prefer, font: ROLE[o.size === "big" ? "big" : "label"], area: o.area });
  }
  function boxFor(L, pos, d) {
    var w = tw(L.text, L.font), h = L.font.indexOf("14px") > 0 ? 16 : 14, x = L.x, y = L.y;
    switch (pos) {
      case "right": return { x0: x + d, y0: y - h / 2, w: w, h: h };
      case "left": return { x0: x - d - w, y0: y - h / 2, w: w, h: h };
      case "above": return { x0: x - w / 2, y0: y - d - h, w: w, h: h };
      case "below": return { x0: x - w / 2, y0: y + d, w: w, h: h };
      case "above-right": return { x0: x + d * 0.6, y0: y - d * 0.6 - h, w: w, h: h };
      case "below-right": return { x0: x + d * 0.6, y0: y + d * 0.6, w: w, h: h };
      case "above-left": return { x0: x - d * 0.6 - w, y0: y - d * 0.6 - h, w: w, h: h };
      case "below-left": return { x0: x - d * 0.6 - w, y0: y + d * 0.6, w: w, h: h };
      case "center": return { x0: x - w / 2, y0: y - h / 2, w: w, h: h };
    }
  }
  function cost(b, bounds) {
    if (b.x0 < bounds.x0 || b.y0 < bounds.y0 || b.x0 + b.w > bounds.x1 || b.y0 + b.h > bounds.y1) return 1e9;
    var k, c = 0, m = 2;
    for (k = 0; k < placed.length; k++) { var p = placed[k]; if (b.x0 < p.x0 + p.w + 3 && b.x0 + b.w + 3 > p.x0 && b.y0 < p.y0 + p.h + 2 && b.y0 + b.h + 2 > p.y0) return 1e9; }
    for (k = 0; k < segs.length; k++) { var s = segs[k]; if (s[0] > b.x0 - m && s[0] < b.x0 + b.w + m && s[1] > b.y0 - m && s[1] < b.y0 + b.h + m) c += 1; }
    for (k = 0; k < hairs.length; k++) { var hs = hairs[k]; if (hs[0] > b.x0 - 1 && hs[0] < b.x0 + b.w + 1 && hs[1] > b.y0 + 1 && hs[1] < b.y0 + b.h - 1) c += 0.5; }
    for (k = 0; k < blobs.length; k++) { var q = blobs[k]; var ix = Math.min(b.x0 + b.w, q.x1) - Math.max(b.x0, q.x0), iy = Math.min(b.y0 + b.h, q.y1) - Math.max(b.y0, q.y0); if (ix > 0 && iy > 0) c += 4 + ix * iy / 40; }
    return c;
  }
  function place(L, budgetName) {
    var order = ["right", "above", "left", "below", "above-right", "below-right", "above-left", "below-left"];
    if (L.prefer) order = [L.prefer].concat(order.filter(function (p) { return p !== L.prefer; }));
    var bounds = { x0: 2, y0: 2, x1: W - 2, y1: H - 2 };
    if (L.area && areas[L.area]) { var A = areas[L.area]; bounds = { x0: A.x - 4, y0: A.y - 14, x1: A.x1 + 4, y1: A.y1 + 4 }; }
    var best = null, bc = 1e9, dists = [LIM.gap, LIM.gap + 6, LIM.gap + 12, LIM.gap + 20, LIM.gap + 30], di, pi;
    for (di = 0; di < dists.length && bc > 0; di++) for (pi = 0; pi < order.length; pi++) {
      var b = boxFor(L, order[pi], dists[di]), c = cost(b, bounds);
      if (c < bc) { bc = c; best = b; } if (c === 0) break;
    }
    if (!best || bc > (budgetName === "mark" ? 16 : 3)) { res.report.dropped.push({ text: L.text, as: budgetName }); return null; }
    placed.push(best);
    ctx.save(); ctx.setLineDash([]); ctx.font = L.font; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.globalAlpha = 0.86; ctx.fillStyle = C.bg; ctx.beginPath(); ctx.rect(best.x0 - 3, best.y0, best.w + 6, best.h); ctx.fill(); ctx.globalAlpha = 1;
    ctx.lineJoin = "round"; ctx.lineWidth = 3.5; ctx.strokeStyle = C.bg; ctx.strokeText(L.text, best.x0, best.y0 + best.h / 2 + 0.5);
    ctx.fillStyle = L.color ? (C[L.color] || C.ink) : C.ink; ctx.fillText(L.text, best.x0, best.y0 + best.h / 2 + 0.5);
    ctx.restore(); res.report.labels++;
    return best;
  }

  // ── marca de régimen: en el lienzo (raya de segmentos + rótulo con su valor) o sobre la pista de un control ──
  function mark(id, value) {
    var m = (widget.marks || []).filter(function (q) { return q.id === id; })[0];
    if (!m || !isFinite(value)) { res.report.marks_out.push(id); return; }
    if (m.control) {
      var c = (widget.controls || []).filter(function (q) { return q.id === m.control; })[0];
      if (!c || value < c.min || value > c.max) { res.report.marks_out.push(id); return; }
      res.cmarks.push({ id: id, control: m.control, value: value, label: m.label, region: m.region, color: m.color });
      if (!m.area) return;
    }
    if (markQ.length >= LIM.marks) { res.report.over_budget++; return; }
    var a = area(m.area || "main"), ax = m.axis === "y" ? a.spec.y : a.spec.x;
    if (!ax || value < Math.min(ax.min, ax.max) || value > Math.max(ax.min, ax.max)) { res.report.marks_out.push(id); return; }
    markQ.push({ m: m, a: a, v: value });
  }
  function drawMark(q) {
    var a = q.a, m = q.m, isY = m.axis === "y", p = Math.round(isY ? a.Y(q.v) : a.X(q.v)) + 0.5;
    ctx.save(); ctx.strokeStyle = m.color ? C[m.color] : C.ink; ctx.lineWidth = 1.25; ctx.setLineDash([4, 3]); ctx.beginPath();
    if (isY) { ctx.moveTo(a.x, p); ctx.lineTo(a.x1, p); } else { ctx.moveTo(p, a.y - 4); ctx.lineTo(p, a.y1); }
    ctx.stroke(); ctx.restore();
    if (isY) blobs.push({ x0: a.x, x1: a.x1, y0: p - 1.5, y1: p + 1.5 }); else blobs.push({ x0: p - 1.5, x1: p + 1.5, y0: a.y - 4, y1: a.y1 });
    if (MUTE || !m.label) return;
    var txt = cut(fill(m.label, q.v), "mark");
    var L = { text: txt, x: isY ? a.x1 : p, y: isY ? p : a.y - 4, font: ROLE.mark, color: m.color, prefer: isY ? "above-left" : "above", area: a.id };
    if (!isY) L.prefer = p > a.x + a.w * 0.7 ? "above-left" : "above-right";
    place(L, "mark");
  }
  function fill(tpl, v) { return String(tpl).replace(/\{(\w+)\}/g, function (_, k) { if (k === "v") return fmt(v, 2); var rd = (widget.readouts || []).filter(function (r) { return r.id === k; })[0]; return k in res.readouts ? fmtRead(rd, res.readouts[k]) : "{" + k + "}"; }); }
  function fmtRead(rd, v) { if (rd && rd.format === "pct") return fmt(v * 100, rd.digits == null ? 0 : rd.digits) + "%"; return fmt(v, rd && rd.digits != null ? rd.digits : 2) + (rd && rd.unit ? rd.unit : ""); }

  // ── contexto del draw: lista cerrada + registro de geometría para los rótulos ──
  var cur = null, startPt = null;
  function P(x, y) { var m = ctx.getTransform ? ctx.getTransform() : null; if (!m) return [x, y]; return [(m.a * x + m.c * y + m.e) / SCALE, (m.b * x + m.d * y + m.f) / SCALE]; }
  function heavy() { return (ctx.lineWidth || 1) * 1 >= 1.5 * (ctx.getTransform ? Math.hypot(ctx.getTransform().a, ctx.getTransform().b) / SCALE : 1); }
  var pending = [];
  var gctx = Object.create(null);
  ["clearRect", "strokeRect", "closePath", "rect", "fill", "save", "restore", "translate", "rotate", "scale", "fillText"].forEach(function (n) {
    gctx[n] = function () { return ctx[n].apply(ctx, arguments); };
  });
  gctx.beginPath = function () { pending = []; cur = null; return ctx.beginPath(); };
  gctx.moveTo = function (x, y) { cur = P(x, y); startPt = cur; return ctx.moveTo(x, y); };
  gctx.lineTo = function (x, y) { var q = P(x, y); if (cur) { var n = Math.max(1, Math.ceil(Math.hypot(q[0] - cur[0], q[1] - cur[1]) / 6)), k; for (k = 0; k <= n; k++) pending.push([cur[0] + (q[0] - cur[0]) * k / n, cur[1] + (q[1] - cur[1]) * k / n]); } cur = q; return ctx.lineTo(x, y); };
  gctx.arc = function (cx, cy, r, a0, a1, ccw) {
    var c = P(cx, cy), rr = r * (ctx.getTransform ? Math.hypot(ctx.getTransform().a, ctx.getTransform().b) / SCALE : 1);
    if (rr < 9) pending.push({ dot: [c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr] });
    else { var n = Math.ceil(Math.abs(a1 - a0) * rr / 6), k; for (k = 0; k <= n; k++) { var an = a0 + (a1 - a0) * k / n; pending.push(P(cx + r * Math.cos(an), cy + r * Math.sin(an))); } }
    return ctx.arc(cx, cy, r, a0, a1, ccw);
  };
  gctx.ellipse = function () { return ctx.ellipse.apply(ctx, arguments); };
  gctx.stroke = function () { var hv = heavy(); pending.forEach(function (p) { if (p.dot) { if (hv) blobs.push({ x0: p.dot[0], y0: p.dot[1], x1: p.dot[2], y1: p.dot[3] }); } else (hv ? segs : hairs).push(p); }); return ctx.stroke(); };
  var _fill = gctx.fill;
  gctx.fill = function () { pending.forEach(function (p) { if (p.dot) blobs.push({ x0: p.dot[0], y0: p.dot[1], x1: p.dot[2], y1: p.dot[3] }); }); return _fill.apply(null, arguments); };
  gctx.fillRect = function (x, y, w, h) { var a = P(x, y), b = P(x + w, y + h), x0 = Math.min(a[0], b[0]), y0 = Math.min(a[1], b[1]), x1 = Math.max(a[0], b[0]), y1 = Math.max(a[1], b[1]); if ((x1 - x0) * (y1 - y0) < 0.25 * W * H && (x1 - x0) > 2 && (y1 - y0) > 2) blobs.push({ x0: x0, y0: y0, x1: x1, y1: y1 }); return ctx.fillRect(x, y, w, h); };
  ["fillStyle", "strokeStyle", "lineWidth", "font", "globalAlpha", "lineCap", "lineJoin", "textAlign", "textBaseline"].forEach(function (n) {
    Object.defineProperty(gctx, n, { enumerable: true, get: function () { return ctx[n]; }, set: function (v) { ctx[n] = v; } });
  });
  // 0.4: el draw no escribe texto libre. fillText queda fuera (el verificador lo rechaza); aquí se ignora y se reporta.
  if (opts.v04) gctx.fillText = function (s) { res.report.free_text = (res.report.free_text || 0) + 1; };

  var ui = {
    c: C, lw: { hair: 1, line: 1.5, bold: 2.5 }, mute: MUTE,
    area: area, axes: axes, label: label, mark: mark,
    readout: function (id, v) { res.readouts[id] = +v; },
    say: function (id) { res.say = String(id); },
    fmt: fmt,
    font: function (role) { ctx.font = ROLE[role] || ROLE.label; },
    clip: function (id) { var a = area(id); ctx.save(); ctx.beginPath(); ctx.rect(a.x - 1, a.y - 1, a.w + 2, a.h + 2); ctx.clip(); },
    unclip: function () { ctx.restore(); },
    // drag: un asa en el lienzo que mueve un control numérico (el teclado sigue en su slider)
    handle: function (id, x, y, o, axis, extra) {
      // positional form (the draw subset has no object literals): (ids, x, y, area, axis, offset | scale)
      if (typeof o === "string" || o == null) o = o ? { area: o, axis: axis, offset: extra } : { axis: axis, scale: extra };
      if (res.handles.length >= 2) { res.report.over_budget++; return; }
      var ids = Array.isArray(id) ? id : [id];
      if (o.area && ids.length === 1) {
        var a = area(o.area), sp = a.spec, isY = o.axis === "y", ax = isY ? sp.y : sp.x;
        if (!ax) { res.report.over_budget++; return; }
        res.handles.push({ ids: ids, mode: "area", x: x, y: y, axis: isY ? "y" : "x", p0: isY ? a.y1 : a.x, p1: isY ? a.y : a.x1, min: ax.min, max: ax.max, log: !!ax.log, color: o.color, offset: +o.offset || 0 });
      } else {
        // modo delta: px de arrastre → unidades del control (scale = px por unidad; 2D con ids [x, y])
        var sc = Array.isArray(o.scale) ? o.scale : [o.scale || 1, o.scale || 1];
        res.handles.push({ ids: ids, mode: "delta", x: x, y: y, axis: ids.length === 2 ? "xy" : (o.axis || "x"), scale: sc, color: o.color });
      }
    },
    // pick: un elemento elegible; el host hace el hit-test y el teclado (flechas) recorre los índices
    pick: function (id, index, x, y, w, h) { if (res.picks.length < 32) res.picks.push({ id: id, i: index, x0: x, y0: y, x1: x + w, y1: y + h }); },
    // inspect: detalle bajo demanda (≤ 36 caracteres); nunca algo que la figura necesite para leerse
    tip: function (x, y, w, h, text) { if (res.tips.length < 32) res.tips.push({ x0: x, y0: y, x1: x + w, y1: y + h, text: cut(text, "tip") }); },
    mix: function (col, alpha) { var h = String(col).replace("#", ""); if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2]; var n = parseInt(h, 16); return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + alpha + ")"; }
  };
  function drawHandle(hd) {
    var col = hd.color ? (C[hd.color] || C.ink) : C.ink;
    ctx.save(); ctx.setLineDash([]);
    ctx.fillStyle = C.hl; ctx.beginPath(); ctx.arc(hd.x, hd.y, 11.5, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = col; ctx.strokeStyle = C.bg; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(hd.x, hd.y, 6.5, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    ctx.restore(); blobs.push({ x0: hd.x - 13, y0: hd.y - 13, x1: hd.x + 13, y1: hd.y + 13 });
  }
  function flush() {
    ctx.setLineDash && ctx.setLineDash([]);
    res.handles.forEach(drawHandle);
    markQ.forEach(drawMark);
    queue.forEach(function (L) { place(L, "label"); });
    return res;
  }
  return { ui: ui, gctx: gctx, flush: flush, result: res, fill: fill, fmtRead: fmtRead };
}
