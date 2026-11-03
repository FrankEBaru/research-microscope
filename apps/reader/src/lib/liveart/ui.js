// Host helpers for rrm-widget/0.4. The model calls them; it does not define them.
// The recorded canvas calls stay on the same stage the verifier already diffs.

const COLORS = {
  bg: "#f6f3ec", ink: "#1d1a16", ink2: "#5c564c", ink3: "#8a8175",
  rule: "#e4d6c4", rule2: "#d9d0c3", soft: "#f3efe6", track: "#e7e1d6",
  ref: "#8a8175", hl: "#c4512c", c1: "#1f4b99", c2: "#c4512c", c3: "#2e7d32", c4: "#8e44ad",
};

function host(fn) {
  return { __kind: "host", call: fn };
}

function box(props) {
  return Object.assign({ __kind: "box" }, props);
}

function num(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function makeUi(widget, state, api) {
  const report = {
    readouts: {},
    say: "",
    handles: [],
    picks: [],
    tips: [],
    marks_out: [],
    dropped: [],
    layout: { text: [] },
  };
  const w = num(state && state.w, 640);
  const h = num(state && state.h, 360);
  const areas = Array.isArray(widget.areas) && widget.areas.length
    ? widget.areas
    : [{ id: "main", rect: [0, 0, 1, 1] }];
  const placed = [];
  let labels = 0;
  let handles = 0;

  function findArea(id) {
    return areas.find((item) => item && item.id === id) || areas[0];
  }

  function areaOf(id) {
    const spec = findArea(id);
    const rect = Array.isArray(spec.rect) && spec.rect.length >= 4 ? spec.rect : [0, 0, 1, 1];
    const pad = spec.bleed ? 0 : 10;
    const axis = spec.axes === false ? 0 : 18;
    const x = rect[0] * w + pad;
    const y = rect[1] * h + pad;
    const ww = Math.max(8, rect[2] * w - pad * 2);
    const hh = Math.max(8, rect[3] * h - pad * 2 - axis);
    const xSpec = spec.x || {};
    const ySpec = spec.y || {};
    return {
      spec, x, y, w: ww, h: hh, x1: x + ww, y1: y + hh, xSpec, ySpec,
    };
  }

  function mapX(area, value) {
    const spec = area.xSpec;
    if (Array.isArray(spec.cats) && spec.cats.length) {
      const band = area.w / spec.cats.length;
      const i = Math.max(0, Math.min(spec.cats.length - 1, num(value, 0)));
      return area.x + band * i + band / 2;
    }
    const lo = num(spec.min, 0);
    const hi = num(spec.max, lo + 1);
    const span = hi === lo ? 1 : hi - lo;
    return area.x + ((num(value, lo) - lo) / span) * area.w;
  }

  function mapY(area, value) {
    const lo = num(area.ySpec.min, 0);
    const hi = num(area.ySpec.max, lo + 1);
    const span = hi === lo ? 1 : hi - lo;
    return area.y + area.h - ((num(value, lo) - lo) / span) * area.h;
  }

  function expose(area) {
    return box({
      x: area.x, y: area.y, w: area.w, h: area.h, x1: area.x1, y1: area.y1,
      X: host((args) => mapX(area, args[0])),
      Y: host((args) => mapY(area, args[0])),
    });
  }

  function ticks(lo, hi) {
    const span = hi === lo ? 1 : hi - lo;
    const raw = span / 4;
    const pow = Math.pow(10, Math.floor(Math.log10(Math.abs(raw) || 1)));
    const err = raw / pow;
    const step = (err >= 5 ? 5 : err >= 2 ? 2 : 1) * pow;
    const out = [];
    let v = Math.ceil(lo / step) * step;
    while (v <= hi + step * 0.01 && out.length < 6) {
      out.push(Math.abs(v) < step * 0.01 ? 0 : v);
      v += step;
    }
    return out.length >= 2 ? out : [lo, hi];
  }

  function paint(text, x, y) {
    api.font = "12px sans-serif";
    api.fillStyle = COLORS.ink;
    api.fillText(String(text), x, y);
  }

  const ui = {
    __kind: "ui",
    c: box(COLORS),
    lw: box({ hair: 1, line: 1.5, bold: 2.5 }),
    mute: Boolean(state && state.mute),
    area: host((args) => expose(areaOf(args[0]))),
    axes: host((args) => {
      const area = areaOf(args[0]);
      api.strokeStyle = COLORS.rule;
      api.lineWidth = 1;
      api.beginPath();
      api.moveTo(area.x, area.y);
      api.lineTo(area.x, area.y1);
      api.lineTo(area.x1, area.y1);
      api.stroke();
      if (ui.mute) return;
      const ys = ticks(num(area.ySpec.min, 0), num(area.ySpec.max, 1));
      for (const value of ys) paint(String(value), area.x + 2, mapY(area, value));
      if (Array.isArray(area.xSpec.cats)) {
        area.xSpec.cats.slice(0, 7).forEach((cat, i) => paint(String(cat).slice(0, 8), mapX(area, i) - 8, area.y1 + 12));
      } else {
        const xs = ticks(num(area.xSpec.min, 0), num(area.xSpec.max, 1));
        for (const value of xs) paint(String(value), mapX(area, value), area.y1 + 12);
      }
    }),
    clip: host(() => undefined),
    unclip: host(() => undefined),
    label: host((args) => {
      const text = String(args[0] == null ? "" : args[0]).slice(0, 18);
      if (!text || ui.mute) return;
      if (labels >= 3) {
        report.dropped.push(text);
        return;
      }
      const x = num(args[1], 0);
      const y = num(args[2], 0);
      const width = text.length * 6.2;
      const spots = [[0, 0], [8, -12], [-width - 4, 0], [0, 14]];
      for (const [dx, dy] of spots) {
        const boxAt = { x: x + dx, y: y + dy - 10, w: width, h: 12 };
        const inside = boxAt.x >= 0 && boxAt.y >= 0 && boxAt.x + boxAt.w <= w && boxAt.y + boxAt.h <= h;
        const hit = placed.some((prev) => prev.x < boxAt.x + boxAt.w && boxAt.x < prev.x + prev.w && prev.y < boxAt.y + boxAt.h && boxAt.y < prev.y + prev.h);
        if (!inside || hit) continue;
        placed.push(boxAt);
        labels += 1;
        paint(text, boxAt.x, y + dy);
        return;
      }
      report.dropped.push(text);
    }),
    mark: host((args) => {
      const id = args[0];
      const value = num(args[1], NaN);
      const spec = (widget.marks || []).find((item) => item && item.id === id);
      if (!spec) return;
      if (spec.control) {
        const control = (widget.controls || []).find((item) => item && item.id === spec.control);
        if (control && (value < control.min || value > control.max)) {
          report.marks_out.push(id);
          return;
        }
      }
      const area = areaOf(spec.area || "main");
      api.strokeStyle = COLORS[spec.color] || COLORS.hl;
      api.lineWidth = 1.5;
      api.beginPath();
      if (spec.axis === "x" || spec.control) {
        const px = mapX(area, value);
        api.moveTo(px, area.y);
        api.lineTo(px, area.y1);
      } else {
        const py = mapY(area, value);
        api.moveTo(area.x, py);
        api.lineTo(area.x1, py);
      }
      api.stroke();
    }),
    readout: host((args) => {
      const id = String(args[0] || "");
      const value = Number(args[1]);
      if (id) report.readouts[id] = value;
    }),
    say: host((args) => {
      report.say = String(args[0] || "");
    }),
    fmt: host((args) => {
      const value = Number(args[0]);
      const digits = Math.max(0, Math.min(6, args.length > 1 ? args[1] | 0 : 2));
      if (!Number.isFinite(value)) return "";
      const text = Math.abs(value) < 0.5 * 10 ** -digits ? (0).toFixed(digits) : value.toFixed(digits);
      return text.replace("-", "−");
    }),
    font: host((args) => {
      const role = args[0];
      if (role === "big") return "15px sans-serif";
      if (role === "label") return "12px sans-serif";
      return "11px sans-serif";
    }),
    handle: host((args) => {
      if (handles >= 2) return;
      handles += 1;
      const id = String(args[0] || "");
      const x = num(args[1], 0);
      const y = num(args[2], 0);
      report.handles.push({ id, x, y });
      api.fillStyle = COLORS.ink;
      api.beginPath();
      api.arc(x, y, 6.5, 0, 6.2832);
      api.fill();
    }),
    pick: host((args) => {
      if (report.picks.length >= 32) return;
      report.picks.push({ id: args[0], index: args[1], x: args[2], y: args[3], w: args[4], h: args[5] });
    }),
    tip: host((args) => {
      if (report.tips.length >= 32) return;
      report.tips.push({ x: args[0], y: args[1], w: args[2], h: args[3], text: String(args[4] || "").slice(0, 36) });
    }),
    mix: host((args) => {
      const color = String(args[0] || COLORS.ink);
      const alpha = Math.max(0, Math.min(1, num(args[1], 1)));
      return color + ":" + alpha;
    }),
  };

  return { ui, report };
}
