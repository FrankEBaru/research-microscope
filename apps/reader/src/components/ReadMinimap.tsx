"use client";
import { useMemo, useRef, useState } from "react";
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
  const close = () => {
    setOpen(false);
    btn.current?.focus();
  };
  const scan = (id: string) => { onOpen(id); setOpen(false); };
  const read = (id: string) => {
    source?.onWant?.(id);
    markRead(id);
    onOpen(id);
    setOpen(false);
  };
  return (
    <>
      <button
        ref={btn}
        type="button"
        className="mini"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Open the atlas"
        onClick={() => { setFrom(btn.current); setOpen(true); }}
      >
        <Atlas model={model} mode="mini" hereId={hereId} suggestId={suggested} />
        <span className="mini-foot">Atlas · {n} explored</span>
        <span className="mini-x" aria-hidden="true"><Icon name="expand" size={13} /></span>
      </button>
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
        onScan={scan}
        onRead={read}
      />
    </>
  );
}
