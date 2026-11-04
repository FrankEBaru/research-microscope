"use client";
import type { ReactNode } from "react";
import "@/styles/inicio.css";
import { paper as fetchPaper, paperKey, settled } from "@/lib/backend.js";
import { LiveCoverage } from "../Panorama";
import SimPanorama from "../SimPanorama";
import { LiveCircle } from "../MapView";
import { Boundary, Notice } from "../faults";
import MapBody from "./MapBody";
import CoreList from "./CoreList";
import BootPanel from "./BootPanel";
import { Pulse, Skeleton } from "../ui/Pulse";
import type { AtlasCtx } from "./types";

function isFull(paper: any, state: any) {
  if (paper?.full || state?.text) return true;
  if (state?.status === "done") return true;
  if (state?.source === "latex" || state?.source === "ocr") return true;
  return state?.stages?.sections === "done";
}

export default function MapScreen({
  core, shownQ, topics, liveResult, phase, engine, say, liveErr, liveCode, debug, pending, asList, setAsList, labelNote,
  liveIds, impatient, forced, setForced, liveQ, liveName, go, backToCurated, atlasCtx, onLayout, jump,
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
  jump?: ReactNode;
}) {
  const rowState = atlasCtx.states;
  if (!core) {
    return (
      <section className={`lvl ${core ? "lvl-map" : ""}`} data-screen="map">
        <button type="button" className="link" onClick={backToCurated}>Back to the curated burst</button>
        <h1 className="question">{shownQ}</h1>
        {topics && <p className="sub" data-subtopics>{topics.length ? <>Subtemas: {topics.join(" · ")}</> : "Esta pregunta no separó subtemas."}</p>}
        {!liveResult && <p className="warm" role="status">{say(phase || (engine === "preparando" ? "wake" : "search"))}</p>}
        {phase === "layout" && liveResult && <p className="warm" role="status">{say("layout")}</p>}
        {liveErr && <Notice kind="fault" code={liveCode} />}
        {liveErr && debug && <p className="fail-reason">{liveErr}</p>}
        {liveResult && <LiveCoverage ids={liveIds} states={rowState} />}
        {liveResult && liveIds.length === 0 && <p className="muted" role="status">The burst found no papers for this question. Try other words.</p>}
        {liveResult && liveIds.length > 0 && !liveIds.every((id: string) => settled(rowState[id]?.status)) && impatient && !forced && (
          <p className="muted small" role="status">Some papers are still queued or being read. <button type="button" className="link" onClick={() => setForced(true)}>Build the Panorama with the papers already read</button> (the rest do not count as “the paper does not say it”).</p>
        )}
        {liveResult && liveIds.length > 0 && (forced || liveIds.every((id: string) => settled(rowState[id]?.status))) && (
          <SimPanorama key={`${liveQ}|${forced}`} autorun question={liveQ} ids={liveIds} states={rowState} getDoc={async (id: string) => { try { return (await fetchPaper(id)).paper; } catch { return null; } }} nameOf={liveName} open={(id, b) => go({ p: id, b })} />
        )}
        {liveResult && <LiveCircle papers={liveResult.papers || []} edges={liveResult.edges || []} states={rowState} onOpen={(id) => go({ p: id })} />}
      </section>
    );
  }

  const papers = liveResult?.papers || [];
  const onMap = (atlasCtx.papers || []).length;
  const groups = liveResult?.layout?.groups || [];
  const refining = Boolean(liveResult?.layout?.pending_vectors?.length);
  const full = papers.filter((paper: any) => isFull(paper, rowState[paperKey(paper)])).length;
  const empty = Boolean(liveResult) && papers.length === 0 && !pending;
  const waiting = !liveErr && !empty && papers.length === 0;

  return (
    <section className="s-map" data-screen="map">
      <header className="map-head">
        <div>
          <h1>{shownQ}</h1>
          {papers.length > 0 && (
            <p className="map-stats tnum">
              {onMap || papers.length} papers · {groups.length} {groups.length === 1 ? "group" : "groups"}{full ? ` · full text of ${full}` : ""}
            </p>
          )}
        </div>
        {papers.length > 0 && (
          <div className="tabs" role="tablist" aria-label="View">
            <button type="button" className="press" aria-selected={!asList} onClick={() => setAsList(false)}>Atlas</button>
            <button type="button" className="press" aria-selected={asList} onClick={() => setAsList(true)}>List</button>
          </div>
        )}
      </header>
      {jump}
      {labelNote && <Notice kind="absence">{labelNote}</Notice>}
      {liveResult?.topic_note && <Notice kind="absence">{liveResult.topic_note}</Notice>}
      {waiting && (
        <>
          <Skeleton lines={5} />
          <Pulse mode="loading" detail={say(phase || "search")} />
          <BootPanel engine={engine} phase={phase} pending={pending} compact />
        </>
      )}
      {liveErr && <Pulse mode="error" detail={liveErr} />}
      {liveErr && <Notice kind="fault" code={liveCode} />}
      {papers.length > 0 && (refining || pending) && <Pulse mode="loading" compact detail="Arranging the atlas…" />}
      {empty && (
        <div data-screen="vacio">
          <Notice kind="absence">The burst found no papers for this question.</Notice>
        </div>
      )}
      {papers.length > 0 && (
        asList
          ? <Boundary name="core-list"><CoreList papers={papers} states={rowState} onOpen={(id: string) => atlasCtx.onOpen(id, "from the map")} onWant={atlasCtx.onWant} /></Boundary>
          : <Boundary name="map-body"><MapBody atlasCtx={atlasCtx} onLayout={onLayout} /></Boundary>
      )}
      <p className="b1-foot"><span>Papers and citations: <a href="https://www.semanticscholar.org/">Semantic Scholar</a></span></p>
    </section>
  );
}
