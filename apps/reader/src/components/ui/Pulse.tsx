"use client";
import { useEffect, useState } from "react";

const SAY = {
  loading: "Loading the paper…",
  ai: "Working…",
  ready: "Ready",
  error: "Couldn’t finish",
};

export type PulseMode = "loading" | "ai" | "ready" | "error";

export function Pulse({ mode, detail, compact = false }: { mode: PulseMode; detail?: string; compact?: boolean }) {
  const clock = mode === "loading" || mode === "ai";
  const hasTime = /\d+\s*s\b/.test(detail || "");
  const [sec, setSec] = useState(0);
  useEffect(() => {
    setSec(0);
    if (!clock || hasTime) return;
    const id = window.setInterval(() => setSec((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [mode, detail, clock, hasTime]);
  const base = detail || SAY[mode];
  const say = clock && !hasTime ? `${base} ${sec} s` : base;
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
