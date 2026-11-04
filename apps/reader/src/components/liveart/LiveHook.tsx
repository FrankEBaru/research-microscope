"use client";
// RRM-96 · The margin hook: a curiosity question next to the claim, over a muted thumbnail of the same
// live figure (contract R10: same draw, ui.mute, no text, no controls). Click opens LiveFigure from here.
import { useEffect, useRef, useState } from "react";
import { mountSandbox } from "@/lib/liveart/mount.js";
import type { LiveEntry } from "@/lib/liveart/live96";
import LiveFigure from "./LiveFigure";

function Thumb({ entry }: { entry: LiveEntry }) {
  const box = useRef<HTMLSpanElement | null>(null);
  const [ok, setOk] = useState(true);
  useEffect(() => {
    const host = box.current;
    if (!host) return;
    let live = true;
    // Mount when the hook is near the viewport: a paper can carry several hooks.
    let handle: ReturnType<typeof mountSandbox> | null = null;
    const io = new IntersectionObserver((rows) => {
      if (!rows.some((r) => r.isIntersecting) || handle) return;
      handle = mountSandbox(host, entry.widget, { v04: true, mute: true, onStatus(s: { ok: boolean }) { if (live && !s.ok) setOk(false); } });
      io.disconnect();
    }, { rootMargin: "300px" });
    io.observe(host);
    return () => { live = false; io.disconnect(); handle?.destroy(); };
  }, [entry]);
  return <span className="lv96-thumb-fig" data-ok={ok ? "1" : "0"} ref={box} aria-hidden="true" />;
}

export default function LiveHook({ entry, inline = false }: { entry: LiveEntry; inline?: boolean }) {
  const btn = useRef<HTMLButtonElement | null>(null);
  const [from, setFrom] = useState<DOMRect | null>(null);
  const [open, setOpen] = useState(false);
  const w = entry.widget;
  return (
    <>
      <button
        ref={btn}
        type="button"
        className={`lv96-hook${inline ? " is-inline" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-widget={w.id}
        onClick={() => { setFrom(btn.current?.getBoundingClientRect() ?? null); setOpen(true); }}
      >
        <Thumb entry={entry} />
        <span className="lv96-hook-b">
          <span className="lv96-hook-k"><i aria-hidden="true" />Live figure</span>
          <span className="lv96-hook-q">{w.hook || w.title}</span>
          <span className="lv96-hook-f">Muse · verified {entry.provenance.contract.replace("rrm-widget/", "v")}</span>
        </span>
      </button>
      {open ? <LiveFigure entry={entry} from={from} onClose={() => { setOpen(false); btn.current?.focus(); }} /> : null}
    </>
  );
}
