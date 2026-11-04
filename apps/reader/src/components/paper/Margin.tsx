"use client";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { foldPlan } from "@/lib/marginfold.js";

export type MarginNote = {
  id: string;
  anchor: string;
  dy?: number;
  kind?: string;
  body: ReactNode;
};

/** Height of a folded note: its label and one line, faded (lectura.css `.sn.is-folded`). */
const FOLD_PX = 64;

/**
 * Columna derecha: cada nota se alinea con su marca y, si chocan, la de abajo baja.
 * RRM-103b: in a dense stretch the pile drifted far from its marks (Attention §3.2: 1.7k px). A note that would sit
 * more than 250 px from its mark folds the tall AI note pushing it (foldPlan). A folded note opens over the column on
 * hover (or when its paragraph is hovered), without moving anything; a click keeps it open and the column re-flows.
 */
export default function Margin({ notes, layoutKey }: { notes: MarginNote[]; layoutKey: string }) {
  const col = useRef<HTMLElement>(null);
  const notesRef = useRef(notes);
  notesRef.current = notes;
  const [tops, setTops] = useState<Record<string, number>>({});
  const [folded, setFolded] = useState<string[]>([]);
  const [opened, setOpened] = useState<string[]>([]);
  const openedRef = useRef(opened);
  openedRef.current = opened;
  const [lit, setLit] = useState("");

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
        let el: HTMLElement | null = null;
        try { el = host.querySelector(`[data-sn="${CSS.escape(note.id)}"]`) as HTMLElement | null; } catch { el = null; }
        // scrollHeight: the full height even while the note is folded (overflow hidden).
        const h = el ? Math.max(el.offsetHeight, el.scrollHeight) : 0;
        return { id: note.id, raw, h };
      }).filter((row): row is { id: string; raw: number; h: number } => row.raw != null).sort((a, b) => a.raw - b.raw || a.id.localeCompare(b.id));
      const plan = foldPlan(rows, {
        limit: 250,
        foldH: FOLD_PX,
        gap: 12,
        canFold: (id: string) => id.startsWith("g-") && !openedRef.current.includes(id),
      });
      setFolded((prev) => (prev.length === plan.folded.length && prev.every((id) => plan.folded.includes(id)) ? prev : plan.folded));
      setTops((prev) => {
        const next = plan.tops as Record<string, number>;
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
    // Hovering a paragraph previews its folded notes (the mark and the note stay linked both ways).
    const over = (e: Event) => {
      const blk = (e.target as HTMLElement)?.closest?.("[data-blk]") as HTMLElement | null;
      setLit(blk?.dataset.blk || "");
    };
    const leave = () => setLit("");
    art?.addEventListener("mouseover", over);
    art?.addEventListener("mouseleave", leave);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      mo?.disconnect();
      window.removeEventListener("resize", schedule);
      art?.removeEventListener("mouseover", over);
      art?.removeEventListener("mouseleave", leave);
    };
  }, [layoutKey, opened.join(",")]);

  const markOf = (note: MarginNote) => {
    try { return col.current?.parentElement?.querySelector("article")?.querySelector(note.anchor) as HTMLElement | null; } catch { return null; }
  };
  const link = (note: MarginNote, on: boolean) => markOf(note)?.classList.toggle("is-noted", on);
  const toggle = (id: string) => setOpened((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  return (
    <aside className="side" ref={col} aria-label="Margin notes">
      {notes.map((note) => {
        const isFolded = folded.includes(note.id);
        const isOpen = opened.includes(note.id);
        const blk = /^g-(.+)-\d+$/.exec(note.id)?.[1] || "";
        return (
          <div
            key={note.id}
            className={`sn${note.kind ? ` sn--${note.kind}` : ""}${isFolded ? " is-folded" : ""}${isOpen ? " is-open" : ""}${isFolded && blk && lit === blk ? " is-lit" : ""}`}
            data-sn={note.id}
            style={{ ["--top" as string]: `${tops[note.id] ?? 0}px`, visibility: tops[note.id] == null ? "hidden" : "visible" }}
            onMouseEnter={() => link(note, true)}
            onMouseLeave={() => link(note, false)}
            {...(isFolded || isOpen ? {
              role: "button",
              tabIndex: 0,
              "aria-expanded": isOpen,
              onClick: (e: React.MouseEvent) => { if (!(e.target as HTMLElement).closest("a, button")) toggle(note.id); },
              onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(note.id); } },
            } : {})}
          >
            {note.body}
          </div>
        );
      })}
    </aside>
  );
}
