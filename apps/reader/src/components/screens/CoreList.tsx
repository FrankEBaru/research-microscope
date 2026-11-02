"use client";
import { useState } from "react";
import "@/styles/inicio.css";
import { paperKey } from "@/lib/backend.js";
import { phaseOf } from "@/lib/qcache.js";
import { Button, Prov } from "../ui";

const PHASE_EN: Record<string, string> = {
  listo: "Ready",
  fallo: "Failed",
  preparando: "Preparing",
  encontrado: "Found",
};

export default function CoreList({ papers, states, onOpen, onWant }: { papers: any[]; states: Record<string, any>; onOpen: (id: string) => void; onWant: (id: string) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const ordered = [...papers].sort((a, b) => Number(Boolean(a.retracted)) - Number(Boolean(b.retracted)));
  return (
    <ol className="core-list">
      {ordered.map((p) => {
        const id = paperKey(p);
        const phase = phaseOf(states[id]?.status);
        const reason = states[id]?.reason;
        const phaseLabel = `${PHASE_EN[phase.id] || phase.label}${phase.id === "fallo" && reason ? ` (${reason})` : ""}`;
        const meta = [phaseLabel, p.year, p.citationcount != null ? `${p.citationcount} citations` : null, p.venue].filter((x) => x != null && x !== "").join(" · ");
        const body = p.abstract || p.tldr || "";
        const expanded = Boolean(open[id]);
        const long = String(body).length > 220;
        return (
          <li key={id} className={p.retracted ? "is-sunk" : undefined}>
            <div>
              <p className="row-meta">
                <span className="cap">{meta}</span>
                {p.survey && <span className="row-flag">survey</span>}
                {p.retracted && <span className="row-flag">retracted</span>}
              </p>
              <h2><button type="button" onClick={() => onOpen(id)}>{p.title || id}</button></h2>
              {p.abstract ? (
                <>
                  <p className={expanded ? "row-blurb" : "row-blurb is-clamp"}>{p.abstract}</p>
                  {long && !expanded && <button type="button" className="row-more" onClick={() => setOpen((cur) => ({ ...cur, [id]: true }))}>more</button>}
                </>
              ) : p.tldr ? (
                <>
                  <p className={expanded ? "row-blurb" : "row-blurb is-clamp"}>
                    <Prov kind="simulado" text="generated" title="generated" />
                    {p.tldr}
                  </p>
                  {long && !expanded && <button type="button" className="row-more" onClick={() => setOpen((cur) => ({ ...cur, [id]: true }))}>more</button>}
                </>
              ) : (
                <p className="row-empty">No abstract in the index.</p>
              )}
            </div>
            <div className="row-actions">
              <Button variant="line" size="sm" onClick={() => onOpen(id)}>Scan</Button>
              <Button variant="primary" size="sm" onClick={() => { onWant(id); onOpen(id); }}>Read in full</Button>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
