"use client";
import type { FormEvent } from "react";

export default function StartScreen({ draft, setDraft, onSearch, pending, engine, phase, since, say }: {
  draft: string;
  setDraft: (value: string) => void;
  onSearch: (e: FormEvent) => void;
  pending: boolean;
  engine: string;
  phase: string;
  since: number;
  say: (phase: string) => string;
}) {
  return (
    <section className="lvl ask" data-screen="start">
      <p className="eyebrow">Una pregunta</p>
      <h1 className="question">Qué quieres entender</h1>
      <form className="ask-box" onSubmit={onSearch}>
        <input aria-label="Pregunta" title={draft || undefined} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Una pregunta, un título, un tema" autoFocus />
        <button type="submit" disabled={pending || !draft.trim()}>Ver el mapa</button>
      </form>
      {(engine === "preparando" || phase === "wake") && <p className="warm" role="status">{say(phase || "wake")}</p>}
      <p className="sub">Los papers aparecen como puntos en cuanto la ráfaga responde. El tamaño es el puesto. El texto completo de los 10 primeros se prepara después, sin bloquear el mapa.</p>
    </section>
  );
}
