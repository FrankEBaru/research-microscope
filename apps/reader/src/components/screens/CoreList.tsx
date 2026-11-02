"use client";
import { paperKey } from "@/lib/backend.js";
import { phaseOf } from "@/lib/qcache.js";

export default function CoreList({ papers, states, onOpen, onWant }: { papers: any[]; states: Record<string, any>; onOpen: (id: string) => void; onWant: (id: string) => void }) {
  const ordered = [...papers].sort((a, b) => Number(Boolean(a.retracted)) - Number(Boolean(b.retracted)));
  return (
    <ol className="core-list">
      {ordered.map((p) => {
        const id = paperKey(p);
        const phase = phaseOf(states[id]?.status);
        const reason = states[id]?.reason;
        return (
          <li key={id} className={p.retracted ? "is-sunk" : undefined}>
            <p className={`phase phase-${phase.id}`} data-phase={phase.id}>{phase.label}{phase.id === "fallo" && reason ? ` (${reason})` : ""}</p>
            <h2><button type="button" className="link" onClick={() => onOpen(id)}>{p.title || id}</button></h2>
            <p className="authors">{[p.year, p.citationcount != null ? `${p.citationcount} citas` : null, p.venue].filter((x) => x != null && x !== "").join(" · ")}</p>
            {p.survey && <p className="survey-tag">survey</p>}
            {p.retracted && <p className="retract">retractado</p>}
            {p.abstract ? <p className="core-blurb">{p.abstract}</p> : p.tldr ? <p className="core-blurb"><span className="chip chip-simulado">generado</span> {p.tldr}</p> : <p className="small">Sin abstract en el índice.</p>}
            <button type="button" onClick={() => onWant(id)}>quiero leer este</button>
          </li>
        );
      })}
    </ol>
  );
}
