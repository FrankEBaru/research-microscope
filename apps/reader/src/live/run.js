import { shapeErrors, bannedIn } from "./contract.js";

const VIEW = { w: 640, h: 360 };

export function createSession(widget, makeCanvas) {
  const hits = shapeErrors(widget);
  const banned = bannedIn(widget.draw);
  if (hits.length || banned.length) {
    const err = new Error("contract:" + hits.concat(banned).join(","));
    err.hits = hits;
    err.banned = banned;
    throw err;
  }
  const state = { w: VIEW.w, h: VIEW.h };
  for (const control of widget.controls) state[control.id] = control.value;
  const ctx = makeCanvas(state.w, state.h);
  const exec = new Function("ctx", "state", "t", `${widget.draw}\nreturn draw(ctx, state, t);`);
  const frame = (t = 0) => exec(ctx, state, Number(t) || 0);
  return {
    specs: widget.controls,
    frame,
    set(id, value) { state[id] = Number(value); },
  };
}

export function mountIn(el, widget) {
  const nodes = [];
  const session = createSession(widget, (w, h) => {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.className = "live-canvas";
    nodes.push(canvas);
    return canvas.getContext("2d");
  });
  el.replaceChildren(...nodes);
  let raf = 0;
  const t0 = performance.now();
  const tick = (now) => {
    session.frame((now - t0) / 1000);
    raf = requestAnimationFrame(tick);
  };
  session.frame(0);
  raf = requestAnimationFrame(tick);
  return {
    specs: session.specs,
    set: session.set,
    destroy() {
      cancelAnimationFrame(raf);
      el.replaceChildren();
    },
  };
}
