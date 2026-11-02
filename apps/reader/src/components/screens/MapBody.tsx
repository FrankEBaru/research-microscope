"use client";
import LiveMap from "../LiveMap";
import type { AtlasCtx } from "./types";

/** El cuerpo del mapa. Hoy es el LiveMap; el atlas nuevo lo sustituye aquí. */
export default function MapBody({ atlasCtx, onLayout }: { atlasCtx: AtlasCtx; onLayout: (next: any) => void }) {
  return <LiveMap papers={atlasCtx.papers} edges={atlasCtx.edges} layout={atlasCtx.layout} states={atlasCtx.states} query={atlasCtx.query} onLayout={onLayout} onOpen={(id: string) => atlasCtx.onOpen(id, "desde el mapa")} onWant={atlasCtx.onWant} />;
}
