"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { mapLayout } from "@/lib/backend.js";
import { atlasModel, lastVisit, suggestOf } from "@/lib/atlas.js";
import Atlas, { Legend, ReadFirst } from "../atlas/Atlas";
import { AtlasCard } from "../atlas/Card";
import type { AtlasCtx } from "./types";

function markRead(id: string) {
  try { sessionStorage.setItem("rrm.read." + id, "1"); } catch { /* private mode */ }
}

export default function MapBody({ atlasCtx, onLayout }: { atlasCtx: AtlasCtx; onLayout: (next: any) => void }) {
  const model = useMemo(
    () => atlasModel({
      papers: atlasCtx.papers,
      edges: atlasCtx.edges,
      layout: atlasCtx.layout,
      states: atlasCtx.states,
      explore: atlasCtx.explore,
      openId: atlasCtx.openId,
    }),
    [atlasCtx.papers, atlasCtx.edges, atlasCtx.layout, atlasCtx.states, atlasCtx.explore, atlasCtx.openId],
  );
  const hereId = lastVisit(atlasCtx.explore);
  const suggested = suggestOf(model);
  const [selected, setSelected] = useState("");
  const [linked, setLinked] = useState(false);
  const pick = (id: string) => { setSelected(id); setLinked(true); };
  const scan = (id: string) => atlasCtx.onOpen(id, "from the map");
  const read = (id: string) => {
    atlasCtx.onWant(id);
    markRead(id);
    atlasCtx.onOpen(id, "from the map");
  };
  const pendingKey = (atlasCtx.layout?.pending_vectors || []).join(",");
  const onLayoutRef = useRef(onLayout);
  onLayoutRef.current = onLayout;
  useEffect(() => {
    if (!atlasCtx.query || !pendingKey) return;
    let stop = false;
    let tries = 0;
    let timer = 0;
    const tick = async () => {
      tries += 1;
      try {
        const body = await mapLayout(atlasCtx.query);
        if (stop) return;
        if (body?.layout && body.pending === false) {
          onLayoutRef.current?.(body.layout);
          return;
        }
      } catch { /* the first map stays on screen */ }
      if (!stop && tries < 12) timer = window.setTimeout(tick, 700);
    };
    timer = window.setTimeout(tick, 350);
    return () => { stop = true; window.clearTimeout(timer); };
  }, [atlasCtx.query, pendingKey]);

  return (
    <div className="atlas-screen" data-live-map>
      <div className="atlas-grid">
        <div className="plot">
          <Atlas model={model} mode="full" hereId={hereId} suggestId={suggested} selected={selected} drawSelection={linked} laneId={atlasCtx.laneId || ""} onSelect={pick} onOpen={scan} />
        </div>
        <AtlasCard model={model} explore={atlasCtx.explore} states={atlasCtx.states} selected={selected} hereId={hereId} suggestId={suggested} onScan={scan} onRead={read} onPick={pick} onOpen={read} />
      </div>
      <Legend />
      <ReadFirst points={model.points || []} onPick={pick} />
    </div>
  );
}
