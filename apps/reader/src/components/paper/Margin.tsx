"use client";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

export type MarginNote = {
  id: string;
  anchor: string;
  dy?: number;
  kind?: string;
  body: ReactNode;
};

/** Columna derecha: cada nota se alinea con su marca y, si chocan, la de abajo baja. */
export default function Margin({ notes, layoutKey }: { notes: MarginNote[]; layoutKey: string }) {
  const col = useRef<HTMLElement>(null);
  const notesRef = useRef(notes);
  notesRef.current = notes;
  const [tops, setTops] = useState<Record<string, number>>({});

  useLayoutEffect(() => {
    const host = col.current;
    if (!host) return;
    let frame = 0;
    const place = () => {
      const list = notesRef.current;
      let colTop = 0;
      try { colTop = host.getBoundingClientRect().top; } catch { return; }
      const art = host.parentElement?.querySelector("article") || document;
      const rows = list.map((note) => {
        let raw: number | null = null;
        try {
          const mark = art.querySelector(note.anchor);
          if (mark) raw = mark.getBoundingClientRect().top - colTop + (note.dy || 0);
        } catch { raw = null; }
        return { id: note.id, raw };
      }).filter((row): row is { id: string; raw: number } => row.raw != null).sort((a, b) => a.raw - b.raw || a.id.localeCompare(b.id));
      let floor = -Infinity;
      const next: Record<string, number> = {};
      for (const row of rows) {
        let el: HTMLElement | null = null;
        try { el = host.querySelector(`[data-sn="${CSS.escape(row.id)}"]`) as HTMLElement | null; } catch { el = null; }
        const h = el?.offsetHeight || 0;
        const top = Math.max(row.raw, floor);
        next[row.id] = top;
        floor = top + h + 12;
      }
      setTops((prev) => {
        const keys = Object.keys(next);
        if (keys.length === Object.keys(prev).length && keys.every((k) => Math.abs((prev[k] ?? 0) - next[k]) < 1)) return prev;
        return next;
      });
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    place();
    schedule();
    const ro = new ResizeObserver(schedule);
    ro.observe(host);
    const art = host.parentElement?.querySelector("article");
    if (art) ro.observe(art);
    window.addEventListener("resize", schedule);
    document.fonts?.ready.then(schedule).catch(() => {});
    const mo = art ? new MutationObserver(schedule) : null;
    if (art && mo) mo.observe(art, { attributes: true, childList: true, subtree: true, attributeFilter: ["class"] });
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      mo?.disconnect();
      window.removeEventListener("resize", schedule);
    };
  }, [layoutKey]);

  return (
    <aside className="side" ref={col} aria-label="Margin notes">
      {notes.map((note) => (
        <div
          key={note.id}
          className={`sn${note.kind ? ` sn--${note.kind}` : ""}`}
          data-sn={note.id}
          style={{ ["--top" as string]: `${tops[note.id] ?? 0}px`, visibility: tops[note.id] == null ? "hidden" : "visible" }}
        >
          {note.body}
        </div>
      ))}
    </aside>
  );
}
