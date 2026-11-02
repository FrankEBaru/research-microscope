"use client";
import { useEffect, useState } from "react";
import "@/styles/faults.css";
import { faultLog, sanitize, subscribe } from "@/lib/faults.js";
import { useDebug } from "./useDebug";

type Step = { id: number; name: string; detail: string; state: string; t0: number; t1: number | null };
type DevLog = { steps: Step[]; line: (row: Step, clock?: number) => string };

const hhmmss = (at: number) => new Date(at).toTimeString().slice(0, 8);

/** Fallas y línea de tiempo. Solo con ?debug=1 (o ?dev=1); la tecla d lo abre y lo cierra. */
export default function DiagPanel({ dev, "data-devlog": tick }: { dev: DevLog; "data-devlog"?: number }) {
  const debug = useDebug();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<any[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!debug) return;
    setRows(faultLog());
    let timer = 0;
    // Diferido: una falla se puede reportar durante el render de otra pieza.
    const off = subscribe(() => { window.clearTimeout(timer); timer = window.setTimeout(() => setRows(faultLog()), 0); });
    return () => { off(); window.clearTimeout(timer); };
  }, [debug]);

  useEffect(() => {
    if (!debug) return;
    const k = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|TEXTAREA|SELECT/.test((e.target as HTMLElement)?.tagName || "")) return;
      if (e.key === "d" || e.key === "D") setOpen((v) => !v);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [debug]);

  if (!debug) return null;

  const copy = () => {
    const payload = {
      faults: rows,
      steps: dev.steps.map((row) => sanitize(dev.line(row))),
    };
    navigator.clipboard?.writeText(JSON.stringify(payload, null, 2)).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    }, () => {});
  };

  return (
    <aside className="diag" data-diag={open ? "open" : "closed"} data-devlog={tick} aria-label="Diagnóstico">
      {open && (
        <div className="diag-body">
          <div className="diag-head">
            <h2>Fallas</h2>
            <button type="button" className="diag-copy press" onClick={copy}>{copied ? "Copiado" : "Copiar"}</button>
          </div>
          {rows.length === 0 ? <p className="diag-empty">Sin fallas.</p> : (
            <ol className="diag-faults">
              {rows.map((row, i) => (
                <li key={`${row.at}-${i}`} data-code={row.code}>
                  <span>{hhmmss(row.at)}</span> <b>{row.code}</b>
                  {row.route && <> {row.route}</>}
                  {row.kind && <> · {row.kind}</>}
                  {row.status ? <> · {row.status}</> : null}
                  {row.ms != null && <> · {row.ms} ms</>}
                  {row.where && <> · {row.where}</>}
                  {row.detail && <> · {row.detail}</>}
                </li>
              ))}
            </ol>
          )}
          <h2>Qué está haciendo</h2>
          <ol className="diag-steps">
            {dev.steps.map((row) => <li key={row.id} className={row.state}>{dev.line(row)}</li>)}
          </ol>
        </div>
      )}
      <button type="button" className="diag-toggle press" aria-expanded={open} data-count={rows.length} onClick={() => setOpen((v) => !v)}>
        Diagnóstico · <span className="tnum">{rows.length}</span>
      </button>
    </aside>
  );
}
