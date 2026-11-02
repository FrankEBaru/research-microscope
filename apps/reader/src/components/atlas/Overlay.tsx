"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Atlas, { Legend } from "./Atlas";
import { AtlasCard } from "./Card";
import { Icon } from "../ui";

export default function Overlay({
  open, onClose, from, query, model, explore, states, hereId, suggestId, onScan, onRead,
}: {
  open: boolean;
  onClose: () => void;
  from: HTMLElement | null;
  query?: string;
  model: any;
  explore?: { nodes?: any[]; edges?: any[]; q?: string } | null;
  states?: Record<string, any>;
  hereId: string;
  suggestId: string;
  onScan: (id: string) => void;
  onRead: (id: string) => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [out, setOut] = useState(false);
  const [selected, setSelected] = useState(hereId || suggestId || "");
  const [linked, setLinked] = useState(false);
  const closing = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const requestClose = () => {
    if (closing.current) return;
    closing.current = true;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onCloseRef.current();
      return;
    }
    setOut(true);
    window.setTimeout(() => onCloseRef.current(), 160);
  };
  const closeRef = useRef(requestClose);
  closeRef.current = requestClose;

  useEffect(() => {
    if (!open) return;
    closing.current = false;
    setOut(false);
    setSelected(hereId || suggestId || "");
    setLinked(false);
  }, [open, hereId, suggestId]);

  useLayoutEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel || !from) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const a = from.getBoundingClientRect();
    const b = panel.getBoundingClientRect();
    if (!b.width || !b.height) return;
    panel.style.transformOrigin = "0 0";
    panel.style.transform = `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`;
    panel.style.opacity = "0.4";
    let stop = 0;
    const frame = requestAnimationFrame(() => {
      panel.classList.add("is-anim");
      panel.style.transform = "";
      panel.style.opacity = "";
      stop = window.setTimeout(() => panel.classList.remove("is-anim"), 380);
    });
    return () => { cancelAnimationFrame(frame); window.clearTimeout(stop); };
  }, [open, from]);

  useEffect(() => {
    if (!open) return;
    const root = document.documentElement;
    root.classList.add("ovl-open");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const items = [...panel.querySelectorAll<HTMLElement>("button, [href], input, textarea, select, [tabindex]:not([tabindex='-1'])")]
        .filter((el) => !el.hasAttribute("disabled"));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey, true);
    const focus = window.setTimeout(() => panelRef.current?.querySelector<HTMLElement>(".ovl-x")?.focus(), 30);
    return () => {
      root.classList.remove("ovl-open");
      window.removeEventListener("keydown", onKey, true);
      window.clearTimeout(focus);
    };
  }, [open]);

  if (!open) return null;
  const pick = (id: string) => { setSelected(id); setLinked(true); };
  return (
    <div className={`ovl${out ? " is-out" : ""}`} onMouseDown={(e) => { if (e.target === e.currentTarget) closeRef.current(); }}>
      <div className="ovl-panel" role="dialog" aria-modal="true" aria-label="Atlas" ref={panelRef}>
        <header className="ovl-h">
          <div className="ovl-t">
            <span>Atlas</span>
            {query ? <span className="ovl-q">{query}</span> : null}
          </div>
          <Legend />
          <button type="button" className="ovl-x" aria-label="Close" onClick={() => closeRef.current()}><Icon name="close" size={16} /></button>
        </header>
        <div className="ovl-g">
          <div className="plot">
            <Atlas model={model} mode="full" hereId={hereId} suggestId={suggestId} selected={selected} drawSelection={linked} onSelect={pick} onOpen={onScan} />
          </div>
          <AtlasCard model={model} explore={explore} states={states} selected={selected} hereId={hereId} suggestId={suggestId} onScan={onScan} onRead={onRead} onPick={pick} />
        </div>
      </div>
    </div>
  );
}
