import { HOST, SANDBOX } from "./spec.js";
import { srcdoc } from "./sandbox.js";
import { verifyWidget } from "./verify.js";

function fallbackCopy(reasons) {
  if (reasons.some((reason) => reason === "dead_control" || reason.startsWith("slop_inert"))) {
    return "A control does not move the picture, so this widget stays down.";
  }
  if (reasons.includes("slop_unrelated")) return "The picture does not match the claim, so this widget stays down.";
  if (reasons.includes("step_cap") || reasons.includes("timeout")) return "This widget took too long, so the sandbox stopped it.";
  if (reasons.includes("banned")) return "This widget asked for something the sandbox does not allow.";
  return "The sandbox stopped this widget.";
}

function showFallback(el, reasons) {
  const note = document.createElement("p");
  note.className = "liveart-fallback";
  note.dataset.reasons = reasons.join(" ");
  note.textContent = fallbackCopy(reasons);
  el.replaceChildren(note);
}

export function mountSandbox(el, widget, opts = {}) {
  const report = verifyWidget(widget, { claim: opts.claim || "" });
  if (!report.accept) {
    showFallback(el, report.reasons);
    return { ok: false, report, set() {}, destroy() { el.replaceChildren(); } };
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
    showFallback(el, [reason]);
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
      raf = window.requestAnimationFrame((now) => {
        if (!t0.now) t0.now = now;
        t = (now - t0.now) / 1000;
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
