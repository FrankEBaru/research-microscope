"use client";
import type { ReactNode } from "react";
import "@/styles/inicio.css";
import PaperView from "../Paper";
import { Notice } from "../faults";
import { Pulse, Skeleton } from "../ui/Pulse";
import type { AtlasCtx } from "./types";

/** El paper en vivo: abierto, o la espera mientras llega. */
export default function ReaderFrame({
  opened, back, openLine, liveErr, liveCode,
  content, focus, companion, onHideCompanion, core, burstIds, map, explore, openId, onOpenPaper, onPromote, atlasCtx,
}: {
  opened: { paper: any; remote: any } | null;
  back: ReactNode;
  jump?: ReactNode;
  openLine: string;
  liveErr: string;
  liveCode: string;
  debug: boolean;
  content: any;
  focus?: string;
  companion: boolean;
  onHideCompanion: () => void;
  core: boolean;
  burstIds: string[];
  map: { papers: any[]; edges: any[]; layout: any } | null;
  explore: { nodes?: any[]; edges?: any[] } | null;
  openId: string;
  onOpenPaper: (id: string, why: string) => void;
  onPromote: () => void;
  atlasCtx: AtlasCtx;
}) {
  const wait = liveErr
    ? <><Pulse mode="error" detail={liveErr} /><Notice kind="fault" code={liveCode} /></>
    : <><Skeleton lines={6} /><Pulse mode="loading" detail={openLine || "Cargando el paper…"} /></>;
  if (opened) {
    return (
      <div className="lvl" data-screen="paper">
        {!core && back}
        <PaperView paper={opened.paper} content={content || {}} focus={focus} companion={core ? false : companion} onHideCompanion={onHideCompanion} remote={opened.remote} showInstrument={!core} showCrops={!core} core={core} burstIds={burstIds} map={map} explore={explore} openId={openId} onOpenPaper={onOpenPaper} onPromote={onPromote} atlasCtx={atlasCtx} />
      </div>
    );
  }
  return (
    <div className="lvl" data-screen="paper">
      {!core && back}
      {wait}
    </div>
  );
}
