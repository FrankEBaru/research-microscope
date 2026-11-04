"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { atlasModel, lastVisit, suggestOf } from "@/lib/atlas.js";
import Atlas from "./atlas/Atlas";
import Overlay from "./atlas/Overlay";
import { Icon } from "./ui";
import type { AtlasCtx } from "./screens/types";

function markRead(id: string) {
  try { sessionStorage.setItem("rrm.read." + id, "1"); } catch { /* private mode */ }
}

export default function ReadMinimap({ papers, edges, layout, onOpen, explore, openId, atlasCtx }: {
  papers: any[];
  edges: any[];
  layout: any;
  onOpen: (id: string) => void;
  explore?: { nodes?: any[]; edges?: any[]; q?: string } | null;
  openId?: string;
  atlasCtx?: AtlasCtx;
}) {
  const source = atlasCtx?.papers?.length ? atlasCtx : null;
  const model = useMemo(() => atlasModel({
    papers: source ? source.papers : papers,
    edges: source ? source.edges : edges,
    layout: source ? source.layout : layout,
    states: source ? source.states : {},
    explore: source?.explore || explore,
    openId: openId || source?.openId || "",
  }), [source, papers, edges, layout, explore, openId]);
  const hereId = String(openId || source?.openId || lastVisit(source?.explore || explore));
  const suggested = suggestOf(model);
  const query = source?.query || explore?.q || "";
  const btn = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState<HTMLElement | null>(null);
  const n = model.visited?.length || 0;
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [narrow, setNarrow] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const [focusId, setFocusId] = useState("");
  useEffect(() => { setHost(document.body); }, []);
  // RRM-97: «See in the atlas» from a citation opens the atlas with that paper selected.
  useEffect(() => {
    const onAtlas = (e: Event) => {
      const id = String((e as CustomEvent).detail?.id || "");
      if (!id) return;
      setFocusId(id);
      setFrom(btn.current);
      setOpen(true);
    };
    window.addEventListener("rrm-atlas", onAtlas);
    return () => window.removeEventListener("rrm-atlas", onAtlas);
  }, []);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 760px)");
    const apply = () => {
      const small = mq.matches;
      setNarrow(small);
      setSlot(small ? document.querySelector<HTMLElement>(".folio .atlas-slot") : null);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  const close = () => {
    setOpen(false);
    setFocusId("");
    btn.current?.focus();
  };
  const scan = (id: string) => { onOpen(id); setOpen(false); setFocusId(""); };
  const read = (id: string) => {
    source?.onWant?.(id);
    markRead(id);
    onOpen(id);
    setOpen(false);
  };
  if (!host) return null;
  if (narrow && !slot) return null;
  const overlay = (
    <Overlay
      open={open}
      onClose={close}
      from={from}
      query={query}
      model={model}
      explore={source?.explore || explore}
      states={source?.states}
      hereId={hereId}
      suggestId={suggested}
      focusId={focusId}
      onScan={scan}
      onRead={read}
    />
  );
  // The overlay is portaled to body: main.zoom-in uses transform, which would trap position:fixed for 420ms.
  // RRM-95 integration: the desktop minimap button stays in its place under the contents (B.1), not floating
  // over the margin notes. On a narrow screen the button sits in the paper header.
  if (narrow) {
    return createPortal(
      <>
        <button
          ref={btn}
          type="button"
          className="atlas-head press"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label="Open the atlas"
          onClick={() => { setFocusId(""); setFrom(btn.current); setOpen(true); }}
        >Atlas</button>
        {overlay}
      </>,
      slot as HTMLElement,
    );
  }
  return (
    <>
      <button
        ref={btn}
        type="button"
        className="mini"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Open the atlas"
        onClick={() => { setFocusId(""); setFrom(btn.current); setOpen(true); }}
      >
        <Atlas model={model} mode="mini" hereId={hereId} suggestId={suggested} />
        <span className="mini-foot">Atlas · {n} explored</span>
        <span className="mini-x" aria-hidden="true"><Icon name="expand" size={13} /></span>
      </button>
      {createPortal(overlay, host)}
    </>
  );
}
