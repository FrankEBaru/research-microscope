"use client";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

export const WORLD_W = 1600;
export const WORLD_H = 1000;
export const LENSES = [1, 2, 4, 8];

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

/** Drag, wheel, lenses and keyboard for the platina. Shared by the curated map and the live map. */
export function usePlatina(resetKey: string) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 1000, h: 600 });
  const kFit = Math.min(size.w / WORLD_W, size.h / WORLD_H) * 0.96;
  const [view, setView] = useState({ k: 0.6, cx: WORLD_W / 2, cy: WORLD_H / 2 });
  const raf = useRef(0);
  const viewRef = useRef(view);
  viewRef.current = view;
  const z = kFit > 0 ? view.k / kFit : 1;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setView({ k: kFit, cx: WORLD_W / 2, cy: WORLD_H / 2 });
  }, [resetKey, kFit]);

  const animateTo = useCallback((t: { k?: number; cx?: number; cy?: number }) => {
    cancelAnimationFrame(raf.current);
    const a = viewRef.current;
    const k1 = clamp(t.k ?? a.k, kFit * 0.9, kFit * 12);
    const cx1 = clamp(t.cx ?? a.cx, 0, WORLD_W);
    const cy1 = clamp(t.cy ?? a.cy, 0, WORLD_H);
    const t0 = performance.now();
    const D = 460;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / D);
      const e = 1 - Math.pow(1 - p, 3);
      setView({
        k: Math.exp(Math.log(a.k) + (Math.log(k1) - Math.log(a.k)) * e),
        cx: a.cx + (cx1 - a.cx) * e,
        cy: a.cy + (cy1 - a.cy) * e,
      });
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  }, [kFit]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      cancelAnimationFrame(raf.current);
      const v = viewRef.current;
      const r = el.getBoundingClientRect();
      const sx = e.clientX - r.left;
      const sy = e.clientY - r.top;
      const k = clamp(v.k * Math.exp(-e.deltaY * 0.0016), kFit * 0.9, kFit * 12);
      const wx = (sx - size.w / 2) / v.k + v.cx;
      const wy = (sy - size.h / 2) / v.k + v.cy;
      setView({
        k,
        cx: clamp(wx - (sx - size.w / 2) / k, 0, WORLD_W),
        cy: clamp(wy - (sy - size.h / 2) / k, 0, WORLD_H),
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [size, kFit]);

  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onDown = (e: PointerEvent) => {
    if ((e.target as HTMLElement).closest("button,.ov,.minimap,.map-tip")) return;
    cancelAnimationFrame(raf.current);
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const onMove = (e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.abs(dx) + Math.abs(dy) > 3) {
      d.moved = true;
      box.current?.setPointerCapture(e.pointerId);
    }
    if (!d.moved) return;
    d.x = e.clientX;
    d.y = e.clientY;
    const v = viewRef.current;
    setView({ k: v.k, cx: clamp(v.cx - dx / v.k, 0, WORLD_W), cy: clamp(v.cy - dy / v.k, 0, WORLD_H) });
  };
  const onUp = () => { setTimeout(() => { drag.current = null; }, 0); };
  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).closest(".map-tip,button")) return;
    const v = viewRef.current;
    const s = 90 / v.k;
    if (e.key === "+" || e.key === "=") animateTo({ k: v.k * 1.6 });
    else if (e.key === "-") animateTo({ k: v.k / 1.6 });
    else if (e.key === "0") animateTo({ k: kFit, cx: WORLD_W / 2, cy: WORLD_H / 2 });
    else if (e.key === "ArrowLeft") animateTo({ cx: v.cx - s });
    else if (e.key === "ArrowRight") animateTo({ cx: v.cx + s });
    else if (e.key === "ArrowUp") animateTo({ cy: v.cy - s });
    else if (e.key === "ArrowDown") animateTo({ cy: v.cy + s });
    else return;
    e.preventDefault();
  };

  const sx = (x: number) => (x - view.cx) * view.k + size.w / 2;
  const sy = (y: number) => (y - view.cy) * view.k + size.h / 2;
  const lensZ = LENSES.reduce((a, b) => (Math.abs(Math.log(z / b)) < Math.abs(Math.log(z / a)) ? b : a));

  return { box, size, view, kFit, z, sx, sy, animateTo, lensZ, drag, onDown, onMove, onUp, onKey };
}
