"use client";
import { useEffect, useState } from "react";

const AI = ["Analizando el paper…", "Buscando extractos…", "Preparando notas…"];
const LOAD = ["Cargando el paper…", "Armando la página…", "Esperando el texto…"];

export type PulseMode = "loading" | "ai" | "ready" | "error";

export function Pulse({ mode, detail, compact = false }: { mode: PulseMode; detail?: string; compact?: boolean }) {
  const lines = mode === "ai" ? AI : mode === "loading" ? (detail ? [detail, ...LOAD] : LOAD) : mode === "error" ? [detail || "No se pudo cargar"] : ["Listo"];
  const [i, setI] = useState(0);
  useEffect(() => { setI(0); }, [mode, detail]);
  useEffect(() => {
    if (lines.length < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => setI((n) => (n + 1) % lines.length), 3200);
    return () => window.clearInterval(id);
  }, [mode, detail, lines.length]);
  const say = lines[i % lines.length];
  return (
    <p className={`pulse${compact ? " is-compact" : ""}`} data-state={mode} role="status">
      {mode === "ready" ? <span className="pulse-mark" aria-hidden="true">✓</span> : mode === "error" ? <span className="pulse-mark" aria-hidden="true">!</span> : (
        <span className="pulse-dots" aria-hidden="true"><i /><i /><i /></span>
      )}
      <span className="pulse-say">{say}</span>
    </p>
  );
}

export function Skeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="sk" aria-hidden="true">
      {Array.from({ length: lines }, (_, n) => <i key={n} style={{ width: `${92 - (n % 3) * 14}%` }} />)}
    </div>
  );
}
