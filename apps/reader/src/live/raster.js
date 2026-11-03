// Tiny canvas stand-in so the headless verifier can see pixels.
// Supports the methods the mockup contract allows. Not a full Canvas spec.

const BG = [253, 250, 244, 255];

function parseColor(input) {
  const c = String(input || "#000").trim();
  if (c[0] === "#") {
    let h = c.slice(1);
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    const n = Number.parseInt(h.slice(0, 6), 16);
    if (!Number.isFinite(n)) return [0, 0, 0, 255];
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 255];
  }
  const m = c.match(/rgba?\(([^)]+)\)/);
  if (!m) return [0, 0, 0, 255];
  const p = m[1].split(",").map((x) => Number(x.trim()));
  return [p[0] || 0, p[1] || 0, p[2] || 0, 255];
}

export function makeRaster(w, h) {
  const buf = new Uint8ClampedArray(w * h * 4);
  function plot(x, y, col) {
    const ix = Math.round(x);
    const iy = Math.round(y);
    if (ix < 0 || iy < 0 || ix >= w || iy >= h) return;
    const o = (iy * w + ix) * 4;
    buf[o] = col[0];
    buf[o + 1] = col[1];
    buf[o + 2] = col[2];
    buf[o + 3] = 255;
  }
  function fillBox(x, y, rw, rh, col) {
    let x0 = Math.round(Math.min(x, x + rw));
    let x1 = Math.round(Math.max(x, x + rw));
    let y0 = Math.round(Math.min(y, y + rh));
    let y1 = Math.round(Math.max(y, y + rh));
    x0 = Math.max(0, x0);
    y0 = Math.max(0, y0);
    x1 = Math.min(w, x1);
    y1 = Math.min(h, y1);
    for (let yy = y0; yy < y1; yy++) {
      for (let xx = x0; xx < x1; xx++) plot(xx, yy, col);
    }
  }
  function line(x0, y0, x1, y1, col, lw) {
    const r = Math.max(0.5, lw / 2);
    const dx = x1 - x0;
    const dy = y1 - y0;
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(dy))));
    const rad = Math.ceil(r);
    for (let i = 0; i <= steps; i++) {
      const x = x0 + (dx * i) / steps;
      const y = y0 + (dy * i) / steps;
      for (let oy = -rad; oy <= rad; oy++) {
        for (let ox = -rad; ox <= rad; ox++) {
          if (ox * ox + oy * oy <= r * r + 0.25) plot(x + ox, y + oy, col);
        }
      }
    }
  }
  function fillPoly(pts, col) {
    if (pts.length < 3) return;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of pts) {
      if (p[1] < minY) minY = p[1];
      if (p[1] > maxY) maxY = p[1];
    }
    const y0 = Math.max(0, Math.floor(minY));
    const y1 = Math.min(h - 1, Math.ceil(maxY));
    for (let y = y0; y <= y1; y++) {
      const xs = [];
      for (let i = 0; i < pts.length; i++) {
        const [xa, ya] = pts[i];
        const [xb, yb] = pts[(i + 1) % pts.length];
        if ((ya <= y && yb > y) || (yb <= y && ya > y)) {
          const t = (y - ya) / (yb - ya);
          xs.push(xa + t * (xb - xa));
        }
      }
      xs.sort((a, b) => a - b);
      for (let i = 0; i + 1 < xs.length; i += 2) {
        const a = Math.ceil(xs[i]);
        const b = Math.floor(xs[i + 1]);
        for (let x = a; x <= b; x++) plot(x, y, col);
      }
    }
  }
  const ctx = {
    canvas: { width: w, height: h },
    fillStyle: "#000000",
    strokeStyle: "#000000",
    lineWidth: 1,
    font: "12px sans-serif",
    textAlign: "left",
    textBaseline: "alphabetic",
    globalAlpha: 1,
    _path: [],
    buf,
    beginPath() { this._path = []; },
    moveTo(x, y) { this._path.push([x, y]); },
    lineTo(x, y) { this._path.push([x, y]); },
    closePath() {
      if (this._path.length) this._path.push(this._path[0].slice());
    },
    arc(x, y, radius, a0, a1, ccw) {
      let d = a1 - a0;
      if (ccw) { if (d > 0) d -= Math.PI * 2; }
      else if (d < 0) d += Math.PI * 2;
      const steps = Math.max(8, Math.ceil(Math.abs(d) * Math.max(radius, 1) / 2));
      for (let i = 0; i <= steps; i++) {
        const a = a0 + (d * i) / steps;
        this._path.push([x + Math.cos(a) * radius, y + Math.sin(a) * radius]);
      }
    },
    fill() { fillPoly(this._path, parseColor(this.fillStyle)); },
    stroke() {
      const col = parseColor(this.strokeStyle);
      const pts = this._path;
      for (let i = 1; i < pts.length; i++) line(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1], col, this.lineWidth);
    },
    fillRect(x, y, rw, rh) { fillBox(x, y, rw, rh, parseColor(this.fillStyle)); },
    clearRect(x, y, rw, rh) { fillBox(x, y, rw, rh, BG); },
    strokeRect(x, y, rw, rh) {
      const col = parseColor(this.strokeStyle);
      const lw = this.lineWidth || 1;
      line(x, y, x + rw, y, col, lw);
      line(x + rw, y, x + rw, y + rh, col, lw);
      line(x + rw, y + rh, x, y + rh, col, lw);
      line(x, y + rh, x, y, col, lw);
    },
    fillText(text, x, y) {
      const s = String(text);
      const width = s.length * 6;
      let left = x;
      if (this.textAlign === "center") left = x - width / 2;
      if (this.textAlign === "right") left = x - width;
      const col = parseColor(this.fillStyle);
      for (let i = 0; i < s.length; i++) {
        const px = left + i * 6;
        const py = y - 8;
        const code = s.charCodeAt(i);
        for (let dy = 0; dy < 8; dy++) {
          for (let dx = 0; dx < 4; dx++) {
            if ((code * 3 + dx * 5 + dy * 7) % 4 !== 0) plot(px + dx, py + dy, col);
          }
        }
      }
    },
    measureText(text) { return { width: String(text).length * 6 }; },
  };
  ctx.fillStyle = "#fdfaf4";
  ctx.fillRect(0, 0, w, h);
  return ctx;
}

export function inkCount(ctx) {
  const d = ctx.buf;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i] !== BG[0] || d[i + 1] !== BG[1] || d[i + 2] !== BG[2]) n += 1;
  }
  return n;
}

export function digest(ctx) {
  const d = ctx.buf;
  let h = 2166136261;
  for (let i = 0; i < d.length; i += 4) {
    h ^= d[i];
    h = Math.imul(h, 16777619);
    h ^= d[i + 1];
    h = Math.imul(h, 16777619);
    h ^= d[i + 2];
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
