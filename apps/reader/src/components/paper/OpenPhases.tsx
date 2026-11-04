"use client";
import { useEffect, useState } from "react";
import "@/styles/inicio.css";
import { Icon } from "../ui";
import { clockText, phaseRows } from "@/lib/opening.js";

export type OpenTrack = { t0: number; log: { phase: string; at: number }[]; route: string };

/** RRM-97: one row per real backend phase while a paper opens, each with its time (same rows as «Starting up»). */
export default function OpenPhases({ track, compact = false }: { track: OpenTrack | null; compact?: boolean }) {
  const [now, setNow] = useState(0);
  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(id);
  }, []);
  if (!track) return null;
  const at = now || track.t0;
  const rows = phaseRows(track.log, at, track.route);
  const total = Math.max(0, (at - track.t0) / 1000);
  return (
    <section className={`boot open-phases${compact ? " boot--compact" : ""}`} aria-live="polite" aria-label="Opening the paper" data-phase={rows.find((r: any) => r.state === "run")?.id || ""}>
      <header className="boot-h">
        <h2>Opening the paper</h2>
        <p className="b1-clock tnum">{clockText(total)}</p>
      </header>
      <ol className="b1-steps">
        {rows.map((row: any) => (
          <li key={row.id} data-row={row.id} className={row.state === "done" ? "is-done" : row.state === "run" ? "is-run" : undefined}>
            <span className="st-i" aria-hidden="true">{row.state === "done" && <Icon name="check" size={13} />}</span>
            <span className="st-t">{row.label}</span>
            <span className="st-v tnum">{row.state === "done" && row.sec == null ? "" : clockText(row.sec)}</span>
            <span className="st-bar" />
          </li>
        ))}
      </ol>
    </section>
  );
}
