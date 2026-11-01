"use client";
import { useState } from "react";
import { Rich } from "@/lib/math";
import { ask } from "@/lib/backend.js";

function group(rows: any[]) {
  const map = new Map<string, any[]>();
  for (const row of rows || []) {
    const key = String(row.paper);
    const list = map.get(key) || [];
    if (!list.some((item) => item.text === row.text)) list.push(row);
    map.set(key, list);
  }
  return [...map.entries()];
}

export default function AskBox({ sectionLabel, ids, onOpen, closed, onSkip }: {
  sectionLabel: string;
  ids?: string[];
  onOpen?: (id: string, why: string) => void;
  closed?: boolean;
  onSkip?: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const send = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr("");
    try {
      setResult(await ask(ids || [], text));
    } catch {
      setErr("No pude buscar en las frases guardadas.");
    } finally {
      setBusy(false);
    }
  };
  const groups = group(result?.extracts || []);
  return (
    <form className="ask-card" onSubmit={send}>
      {closed && (
        <p className="ask-offer">Cerraste una sección. Puedes escribir o seguir.
          <button type="button" className="link" onClick={onSkip}>Seguir</button>
        </p>
      )}
      <p className="small">Sección: {sectionLabel}. Se puede seguir sin llenar la caja.</p>
      <textarea aria-label="Qué entendiste" value={text} onChange={(event) => setText(event.target.value)} placeholder="En tus palabras. El LaTeX va entre $." />
      {text.trim() && <div className="ask-preview" aria-hidden="true"><Rich text={text} /></div>}
      <button type="submit" disabled={busy || !text.trim()}>Enviar</button>
      {err && <p className="fail-reason">{err}</p>}
      {result?.empty && <p role="status">No encontré esas palabras.</p>}
      {result && !result.empty && (
        <div className="extracts">
          <p className="ask-label">estos papers dicen ({result.papers})</p>
          {groups.map(([id, rows]) => (
            <section key={id} className="extract">
              <button type="button" className="link" onClick={() => onOpen?.(id, "cita en la caja")}>{id}</button>
              {rows.map((row: any, index: number) => <blockquote key={index}>{row.text}</blockquote>)}
            </section>
          ))}
        </div>
      )}
      {result?.line ? (
        <details className="generated">
          <summary><span className="chip chip-simulado">generado</span></summary>
          <p>{result.line}</p>
        </details>
      ) : null}
    </form>
  );
}
