"use client";
import type { CSSProperties } from "react";
import { Cap, Button, Prov } from "../ui";
import { phaseOf } from "@/lib/qcache.js";
import { visitWhy } from "@/lib/explore.js";
import { nodeLabel } from "@/lib/layout.js";
import { Rich } from "@/lib/math";

function ink(color: string): CSSProperties {
  return { ["--c" as string]: color } as CSSProperties;
}

const PHASE: Record<string, string> = {
  encontrado: "Found",
  preparando: "Preparing",
  listo: "Ready",
  fallo: "Failed",
};

function clip(text: string, n = 280) {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  if (s.length <= n) return s;
  const cut = s.slice(0, n).replace(/\s+\S*$/, "").trim();
  return `${(cut.length >= 40 ? cut : s.slice(0, n).trim())}…`;
}

function shortName(point: any) {
  const label = nodeLabel({ authors: point.authors, year: point.year, title: point.title });
  if (!point.year) return label;
  return label.replace(new RegExp(`\\s+${point.year}$`), "");
}

export function phaseLabel(status: string | undefined) {
  const phase = phaseOf(status);
  return PHASE[phase.id] || phase.label;
}

export default function Card({
  point, status, phase, linked, path, license, gated, onScan, onRead, onPick, onOpen,
}: {
  point: any;
  status?: string;
  phase?: string;
  linked?: any[];
  path?: { id: string; title: string; why: string }[];
  license?: string;
  gated?: boolean;
  onScan?: (id: string) => void;
  onRead?: (id: string) => void;
  onPick?: (id: string) => void;
  onOpen?: (id: string) => void;
}) {
  if (!point) {
    return (
      <div className="card is-in" data-id="" aria-live="polite">
        <Cap>Your path</Cap>
        <ul className="near">
          {(path || []).map((row) => (
            <li key={row.id}>
              <button type="button" onClick={() => (onOpen ? onOpen(row.id) : onPick?.(row.id))}>
                <span className="near-t"><Rich text={row.title} /></span>
                {row.why ? <span className="near-w">{row.why}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  const mark = [status, phase].filter(Boolean).join(" · ");
  const quote = clip(point.abstract || "");
  const rows = linked || [];
  return (
    <div className="card is-in" data-id={point.id} aria-live="polite">
      <p className="card-grp">
        <i style={ink(point.color)} aria-hidden="true" />
        {point.laneName ? <span>{point.laneName}</span> : null}
        {mark ? <span className="card-st">{mark}</span> : null}
      </p>
      <h2><Rich text={point.title || "Paper"} /></h2>
      {point.authorLine ? <p className="card-a">{point.authorLine}</p> : null}
      <dl className="card-m tnum">
        <div><dt>Year</dt><dd>{point.year ?? "No year"}</dd></div>
        <div><dt>Venue</dt><dd>{point.venue || "—"}</dd></div>
        <div><dt>In this map</dt><dd>{(point.cites?.length || 0) + (point.citedBy?.length || 0)}</dd></div>
      </dl>
      {quote ? (
        <blockquote>
          <p><Rich text={quote} /></p>
          <footer><Prov kind="paper" text="Abstract" /></footer>
        </blockquote>
      ) : null}
      {license ? <p className="card-flag">{gated ? `${license} — abstract + link` : license}</p> : null}
      {point.survey ? <p className="card-flag">Survey</p> : null}
      {point.retracted ? <p className="card-flag">Retracted</p> : null}
      <div className="card-act">
        <Button variant="line" onClick={() => onScan?.(point.id)}>Scan</Button>
        <Button variant="primary" onClick={() => onRead?.(point.id)}>{gated ? "Open" : "Read in full"}</Button>
      </div>
      {rows.length ? (
        <>
          <Cap gap>Linked here</Cap>
          <ul className="near">
            {rows.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => onPick?.(item.id)}>
                  <i style={ink(item.color)} aria-hidden="true" />
                  <span className="near-t">{shortName(item)}</span>
                  {item.year ? <span className="tnum">{item.year}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function statusOf(id: string, hereId: string, suggestId: string, visited: Set<string>) {
  if (!id) return "";
  if (id === hereId) return "You are here";
  if (id === suggestId) return "Suggested start";
  if (visited.has(id)) return "Visited";
  return "";
}

function linkedOf(point: any, by: Map<string, any>) {
  const out: any[] = [];
  const seen = new Set<string>();
  for (const id of [...(point?.cites || []), ...(point?.citedBy || [])]) {
    if (seen.has(id)) continue;
    const other = by.get(id);
    if (!other?.title) continue;
    seen.add(id);
    out.push(other);
    if (out.length === 5) break;
  }
  return out;
}

export function pathOf(explore: { nodes?: any[]; edges?: any[]; q?: string } | null | undefined) {
  return [...(explore?.nodes || [])]
    .map((node) => ({ node, at: node?.at || 0 }))
    .sort((a, b) => a.at - b.at)
    .map(({ node }) => ({
      id: String(node.id),
      title: String(node.title || node.id),
      why: visitWhy(node, explore?.edges || [], explore?.q) || "",
    }));
}

/** Paper card, or the path list when nothing is selected and this question has visits. */
export function AtlasCard({
  model, explore, states, selected, hereId, suggestId, onScan, onRead, onPick, onOpen,
}: {
  model: any;
  explore?: { nodes?: any[]; edges?: any[]; q?: string } | null;
  states?: Record<string, any>;
  selected?: string;
  hereId?: string;
  suggestId?: string;
  onScan?: (id: string) => void;
  onRead?: (id: string) => void;
  onPick?: (id: string) => void;
  onOpen?: (id: string) => void;
}) {
  const visited = new Set<string>(model?.visited || []);
  const here = hereId || "";
  const suggest = suggestId || "";
  const picked = selected || "";
  const showPath = !picked && visited.size > 0;
  const showId = picked || (showPath ? "" : (here || suggest));
  const by = new Map<string, any>((model?.points || []).map((p: any) => [p.id, p]));
  const point = showId ? by.get(showId) : null;
  if (!point) return <Card point={null} path={pathOf(explore)} onPick={onPick} onOpen={onOpen} />;
  const state = states?.[point.id];
  return (
    <Card
      point={point}
      status={statusOf(point.id, here, suggest, visited)}
      phase={phaseLabel(state?.status)}
      license={state?.license || ""}
      gated={Boolean(state?.gated)}
      linked={linkedOf(point, by)}
      onScan={onScan}
      onRead={onRead}
      onPick={onPick}
      onOpen={onOpen}
    />
  );
}
