import { fallbackText } from "./fallback.js";
import { HOST, SANDBOX, isV04 } from "./spec.js";
import { srcdoc, srcdoc04 } from "./sandbox.js";
import { verifyWidget } from "./verify.js";

function showFallback(el, reasons) {
  const note = document.createElement("p");
  note.className = "liveart-fallback";
  note.dataset.reasons = reasons.join(" ");
  note.textContent = fallbackText(reasons);
  el.replaceChildren(note);
}

function reportStatus(opts, ok, reasons) {
  if (opts.onStatus) opts.onStatus({ ok, reasons });
}

// 0.4 (RRM-90): the B1 tokens, resolved here because the iframe cannot read var(--…) (contract §3.5).
function tokens() {
  if (typeof window === "undefined" || !window.getComputedStyle) return null;
  const cs = window.getComputedStyle(document.documentElement);
  const g = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
  return {
    bg: g("--sheet", "#ffffff"), ink: g("--ink", "#1d1a16"), ink2: g("--ink-2", "#5a5348"), ink3: g("--ink-3", "#6b6357"),
    rule: g("--rule", "#e2d9c8"), rule2: g("--rule-2", "#cfc4b0"), soft: g("--page-2", "#f6f1e7"), track: g("--data-track", "#efe8da"),
    ref: g("--data-raw", "#8c8271"), hl: g("--hl-soft", "rgba(255,225,77,.38)"),
    c1: g("--viz-1", g("--accent", "#0b6782")), c2: g("--viz-2", "#b4501f"), c3: g("--viz-3", "#7b4a8c"), c4: g("--viz-4", "#7d6418"),
  };
}

export function mountSandbox(el, widget, opts = {}) {
  const v04 = !!opts.v04 && isV04(widget);
  const report = verifyWidget(widget, { claim: opts.claim || "", v04: !!opts.v04 });
  if (!report.accept) {
    if (!opts.onStatus) showFallback(el, report.reasons);
    reportStatus(opts, false, report.reasons);
    return { ok: false, report, set() {}, destroy() {} };
  }

  const iframe = document.createElement("iframe");
  iframe.className = "liveart-frame";
  iframe.title = widget.title || "Live widget";
  iframe.setAttribute("sandbox", SANDBOX);
  iframe.referrerPolicy = "no-referrer";
  iframe.srcdoc = v04 ? srcdoc04(widget) : srcdoc(widget.draw);
  el.replaceChildren(iframe);

  const state = { w: HOST.canvas_w, h: HOST.canvas_h };
  // 0.4: the canvas measures what its container measures (R4); a layer over it takes the pointer (R8).
  const size = { w: HOST.canvas_w, h: HOST.canvas_h };
  let frame = null;
  let layer = null;
  let observer = null;
  function measure() {
    const w = Math.max(240, Math.floor(el.clientWidth || HOST.canvas_w));
    size.w = w;
    size.h = Math.round(w / (Number(widget.aspect) || 16 / 9));
    iframe.style.width = size.w + "px";
    iframe.style.height = size.h + "px";
  }
  function init() {
    const target = iframe.contentWindow;
    if (!target) return;
    const msg = { type: "rrm-init", w: size.w, h: size.h, dpr: window.devicePixelRatio || 1, colors: tokens(), mute: !!opts.mute };
    if (opts.font instanceof ArrayBuffer) msg.font = opts.font.slice(0);
    target.postMessage(msg, "*", msg.font ? [msg.font] : []);
  }
  if (v04) {
    iframe.style.border = "0";
    iframe.style.display = "block";
    el.style.position = el.style.position || "relative";
    measure();
    layer = document.createElement("div");
    layer.className = "liveart-layer";
    layer.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;touch-action:none";
    el.appendChild(layer);
    let drag = null;
    const point = (ev) => { const b = layer.getBoundingClientRect(); return { x: ev.clientX - b.left, y: ev.clientY - b.top }; };
    const control = (id) => widget.controls.find((c) => c.id === id);
    const snap = (c, v) => Math.max(c.min, Math.min(c.max, Math.round((v - c.min) / c.step) * c.step + c.min));
    const apply = (id, v) => { state[id] = v; dirty = true; if (!inflight) send(); if (opts.onSet) opts.onSet(id, v); };
    layer.addEventListener("pointerdown", (ev) => {
      if (!frame) return;
      const p = point(ev);
      const h = (frame.handles || []).find((q) => Math.hypot(q.x - p.x, q.y - p.y) <= 18);
      if (h) { drag = { h, p0: p, v0: h.ids.map((id) => state[id]) }; layer.setPointerCapture(ev.pointerId); layer.style.cursor = "grabbing"; ev.preventDefault(); return; }
      const k = (frame.picks || []).find((q) => p.x >= q.x0 && p.x <= q.x1 && p.y >= q.y0 && p.y <= q.y1);
      if (k && control(k.id)) apply(k.id, k.i);
    });
    layer.addEventListener("pointermove", (ev) => {
      const p = point(ev);
      if (!drag) {
        const over = frame && (frame.handles || []).some((q) => Math.hypot(q.x - p.x, q.y - p.y) <= 18);
        layer.style.cursor = over ? "grab" : "";
        return;
      }
      const h = drag.h;
      h.ids.forEach((id, i) => {
        const c = control(id);
        if (!c) return;
        let v;
        if (h.mode === "area") {
          const f = ((h.axis === "y" ? p.y : p.x) - h.p0) / (h.p1 - h.p0);
          v = (h.log ? Math.exp(Math.log(h.min) + f * (Math.log(h.max) - Math.log(h.min))) : h.min + f * (h.max - h.min)) + (h.offset || 0);
        } else {
          const d = (h.axis === "y" || i === 1) ? p.y - drag.p0.y : p.x - drag.p0.x;
          v = drag.v0[i] + d / (h.scale ? h.scale[i] : 1);
        }
        v = snap(c, v);
        if (v !== state[id]) apply(id, v);
      });
    });
    const end = () => { drag = null; layer.style.cursor = ""; };
    layer.addEventListener("pointerup", end);
    layer.addEventListener("pointercancel", end);
    if (typeof ResizeObserver === "function") {
      observer = new ResizeObserver(() => { const w0 = size.w; measure(); if (size.w !== w0 && ready) { init(); dirty = true; if (!inflight) send(); } });
      observer.observe(el);
    }
  }
  for (const control of widget.controls) state[control.id] = control.value;
  let t = 0;
  let ready = false;
  let dead = false;
  let inflight = false;
  let dirty = true;
  let timer = 0;
  let raf = 0;
  const t0 = { now: 0 };

  function fail(reason) {
    if (dead) return;
    dead = true;
    window.clearTimeout(timer);
    window.cancelAnimationFrame(raf);
    window.removeEventListener("message", onMsg);
    if (!opts.onStatus) showFallback(el, [reason]);
    reportStatus(opts, false, [reason]);
  }

  function send() {
    if (dead || !ready || inflight) return;
    const target = iframe.contentWindow;
    if (!target) return fail("throw");
    inflight = true;
    dirty = false;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fail("timeout"), HOST.frame_ms);
    target.postMessage({ type: "rrm-params", state: { ...state }, t }, "*");
  }

  function onMsg(ev) {
    if (dead || ev.source !== iframe.contentWindow) return;
    const data = ev.data;
    if (!data || data.type !== "rrm-live") return;
    if (data.reason === "ready" && data.ok) {
      ready = true;
      if (v04) init();
      send();
      return;
    }
    if (data.reason === "font") {
      dirty = true;
      if (!inflight) send();
      return;
    }
    if (!inflight && data.reason === "ready") return;
    window.clearTimeout(timer);
    inflight = false;
    if (!data.ok) return fail(data.reason || "throw");
    if (dead) return;
    if (v04 && data.frame) frame = data.frame;
    // 0.4 frames carry what the host paints; a 0.3 frame reports null.
    if (opts.onFrame) opts.onFrame(v04 ? frame : null, { ...state });
    if (report.usesT) {
      const play = (widget.controls || []).find((control) => control.kind === "play");
      raf = window.requestAnimationFrame((now) => {
        if (!t0.now) t0.now = now;
        const running = !play || Number(state[play.id]) >= 0.5;
        if (running) t = (now - t0.now) / 1000;
        dirty = true;
        send();
      });
      return;
    }
    if (dirty) send();
  }

  window.addEventListener("message", onMsg);
  timer = window.setTimeout(() => fail("timeout"), HOST.frame_ms);

  return {
    ok: true,
    report,
    set(id, value) {
      if (dead || !widget.controls.some((control) => control.id === id)) return;
      state[id] = Number(value);
      dirty = true;
      if (!inflight) send();
    },
    destroy() {
      dead = true;
      window.clearTimeout(timer);
      window.cancelAnimationFrame(raf);
      window.removeEventListener("message", onMsg);
      if (observer) observer.disconnect();
      if (layer) layer.remove();
      iframe.remove();
    },
  };
}
