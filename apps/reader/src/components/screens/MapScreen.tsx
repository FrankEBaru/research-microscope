"use client";
import { paper as fetchPaper, settled } from "@/lib/backend.js";
import { LiveCoverage } from "../Panorama";
import SimPanorama from "../SimPanorama";
import { LiveCircle } from "../MapView";
import { Boundary, Notice } from "../faults";
import MapBody from "./MapBody";
import CoreList from "./CoreList";
import type { AtlasCtx } from "./types";

export default function MapScreen({
  core, shownQ, topics, liveResult, phase, engine, say, liveErr, liveCode, debug, pending, asList, setAsList, labelNote,
  liveIds, impatient, forced, setForced, liveQ, liveName, go, backToCurated, atlasCtx, onLayout,
}: {
  core: boolean;
  shownQ: string;
  topics: string[] | null;
  liveResult: any;
  phase: string;
  engine: string;
  say: (phase: string) => string;
  liveErr: string;
  liveCode: string;
  debug: boolean;
  pending: boolean;
  asList: boolean;
  setAsList: (value: boolean) => void;
  labelNote: string;
  liveIds: string[];
  impatient: boolean;
  forced: boolean;
  setForced: (value: boolean) => void;
  liveQ: string;
  liveName: (id: string) => string;
  go: (route: { q?: string; c?: string; p?: string; b?: string }) => void;
  backToCurated: () => void;
  atlasCtx: AtlasCtx;
  onLayout: (next: any) => void;
}) {
  const rowState = atlasCtx.states;
  return (
    <section className={`lvl ${core ? "lvl-map" : ""}`} data-screen="map">
      {!core && <button type="button" className="link" onClick={backToCurated}>volver a la ráfaga curada</button>}
      <h1 className="question">{shownQ}</h1>
      {!core && topics && <p className="sub" data-subtopics>{topics.length ? <>Subtemas: {topics.join(" · ")}</> : "Esta pregunta no separó subtemas."}</p>}
      {!core && !liveResult && <p className="warm" role="status">{say(phase || (engine === "preparando" ? "wake" : "search"))}</p>}
      {phase === "layout" && liveResult && <p className="warm" role="status">{say("layout")}</p>}
      {core && !liveResult && <div className="platina is-wait" role="status"><p>{say(phase || "search")}</p></div>}
      {liveErr && <Notice kind="fault" code={liveCode} />}
      {liveErr && debug && <p className="fail-reason">{liveErr}</p>}
      {core && liveErr && !liveResult && !pending && <div className="platina is-wait"><p>No se pudo armar el mapa.</p></div>}
      {core && liveResult && (liveResult.papers || []).length > 0 && (
        <>
          <div className="view-toggle" role="tablist" aria-label="Vista">
            <button type="button" className={!asList ? "on" : ""} onClick={() => setAsList(false)}>Mapa</button>
            <button type="button" className={asList ? "on" : ""} onClick={() => setAsList(true)}>Lista</button>
          </div>
          {labelNote && <p className="muted" role="status">{labelNote}</p>}
          {liveResult.topic_note && <p className="muted" role="status">{liveResult.topic_note}</p>}
          {asList
            ? <Boundary name="core-list"><CoreList papers={liveResult.papers || []} states={rowState} onOpen={(id: string) => atlasCtx.onOpen(id, "desde el mapa")} onWant={atlasCtx.onWant} /></Boundary>
            : <Boundary name="map-body"><MapBody atlasCtx={atlasCtx} onLayout={onLayout} /></Boundary>}
          <p className="muted small">Datos de papers y citas: Semantic Scholar. LaTeX primero; OCR solo si el paper no tiene LaTeX.</p>
        </>
      )}
      {!core && liveResult && <LiveCoverage ids={liveIds} states={rowState} />}
      {!core && liveResult && liveIds.length === 0 && <p className="muted" role="status">La ráfaga no encontró papers para esta pregunta. Prueba con otras palabras.</p>}
      {core && liveResult && (liveResult.papers || []).length === 0 && <p className="muted" role="status">La ráfaga no encontró papers para esta pregunta. Prueba con otras palabras.</p>}
      {!core && liveResult && liveIds.length > 0 && !liveIds.every((id: string) => settled(rowState[id]?.status)) && impatient && !forced && (
        <p className="muted small" role="status">Algunos papers siguen en cola o leyéndose. <button type="button" className="link" onClick={() => setForced(true)}>Armar el Panorama con los ya leídos</button> (los que faltan no cuentan como «no lo dice»).</p>
      )}
      {!core && liveResult && liveIds.length > 0 && (forced || liveIds.every((id: string) => settled(rowState[id]?.status))) && (
        <SimPanorama key={`${liveQ}|${forced}`} autorun question={liveQ} ids={liveIds} states={rowState} getDoc={async (id: string) => { try { return (await fetchPaper(id)).paper; } catch { return null; } }} nameOf={liveName} open={(id, b) => go({ p: id, b })} />
      )}
      {!core && liveResult && <LiveCircle papers={liveResult.papers || []} edges={liveResult.edges || []} states={rowState} onOpen={(id) => go({ p: id })} />}
    </section>
  );
}
