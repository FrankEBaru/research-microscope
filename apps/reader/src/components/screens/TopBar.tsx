"use client";
import type { FormEvent } from "react";

type Step = { n: number; label: string; sub?: string; on?: () => void };

export default function TopBar({ core, live, liveOn, liveId, steps, level, draft, setDraft, onSearch, companion, setCompanion }: {
  core: boolean;
  live: boolean;
  liveOn: boolean;
  liveId: string;
  steps: Step[];
  level: number;
  draft: string;
  setDraft: (value: string) => void;
  onSearch: (e: FormEvent) => void;
  companion: boolean;
  setCompanion: (fn: (v: boolean) => boolean) => void;
}) {
  return (
    <header className="topbar">
      <a className="brand" href="#/" onClick={() => window.scrollTo({ top: 0 })}><span className="lens" aria-hidden="true" />Microscopio de lectura</a>
      {!(core && (liveOn || liveId)) && (
        <nav className="scope" aria-label="Nivel de zoom">
          {steps.map((s) => (
            <button key={s.n} className={`step ${level === s.n ? "on" : ""} ${level > s.n ? "past" : ""}`} disabled={!s.on || level === s.n} onClick={s.on} title={s.sub || ""}>
              <span className="dot">{s.n}</span><span className="lbl">{s.label}</span>
            </button>
          ))}
        </nav>
      )}
      {live && !(core && !liveOn && !liveId) && (
        <form className="live-search" onSubmit={onSearch}>
          <input aria-label="Pregunta" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Pregunta" />
          <button type="submit">Buscar</button>
        </form>
      )}
      {!core && <button className="companion-toggle" aria-pressed={companion} onClick={() => setCompanion((v) => !v)} title="Compañero de lectura opcional: ofrece ayuda, nunca interrumpe, no guarda nada (tecla C)">Compañero {companion ? "activado" : "apagado"}</button>}
      {!(live && process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") && <span className="proto">prototipo · datos locales</span>}
    </header>
  );
}
