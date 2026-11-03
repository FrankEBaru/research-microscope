import { fallbackText } from "./fallback.js";
import { HOST, SANDBOX } from "./spec.js";
import { srcdoc } from "./sandbox.js";
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

export function mountSandbox(el, widget, opts = {}) {
  const report = verifyWidget(widget, { claim: opts.claim || "" });
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
  iframe.srcdoc = srcdoc(widget.draw);
  el.replaceChildren(iframe);

  const state = { w: HOST.canvas_w, h: HOST.canvas_h };
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
      send();
      return;
    }
    if (!inflight && data.reason === "ready") return;
    window.clearTimeout(timer);
    inflight = false;
    if (!data.ok) return fail(data.reason || "throw");
    if (dead) return;
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
      iframe.remove();
    },
  };
}
