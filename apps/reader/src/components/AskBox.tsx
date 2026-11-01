"use client";
import { useEffect, useState } from "react";
import { Rich } from "@/lib/math";
import { ask } from "@/lib/backend.js";

const PARTS = [
  ["coincide", "Coincide"],
  ["contradice", "Contradice"],
  ["sin_respaldo", "Sin respaldo"],
  ["te_falto", "Te faltó"],
] as const;

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

export default function AskBox({ sectionLabel, ids, onOpen, closed, onSkip, onPromote }: {
  sectionLabel: string;
  ids?: string[];
  onOpen?: (id: string, why: string) => void;
  closed?: boolean;
  onSkip?: () => void;
  onPromote?: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [store, setStore] = useState<any>(null);
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState("");
  const key = (ids || []).join(",");
  useEffect(() => {
    if (!key) return;
    let stop = false;
    let timer = 0;
    const tick = async () => {
      try {
        const body = await ask(ids || [], "");
        if (stop) return;
        setStore(body?.store || null);
        if (body?.store && body.store.ready < body.store.total) timer = window.setTimeout(tick, 2000);
      } catch { /* el envío dice si no hubo almacén */ }
    };
    tick();
    return () => { stop = true; window.clearTimeout(timer); };
  }, [key]);
  const send = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr("");
    setProgress("buscando frases en los papers…");
    onPromote?.();
    try {
      const ranked = await ask(ids || [], text, "frases");
      setResult(ranked);
      if (ranked?.store) setStore(ranked.store);
      if (ranked?.empty) return;
      setProgress("revisando cada cita…");
      const body = await ask(ids || [], text, "revisar");
      setResult(body);
      if (body?.store) setStore(body.store);
    } catch {
      setErr("No pude buscar en las frases guardadas.");
    } finally {
      setBusy(false);
      setProgress("");
    }
  };
  const groups = group(result?.extracts || []);
  const parts = result?.parts || {};
  const hasParts = PARTS.some(([id]) => (parts[id] || []).length);
  const shown = (result?.extracts || []).length;
  return (
    <form className="ask-card" onSubmit={send}>
      {closed && (
        <p className="ask-offer">Cerraste una sección. Puedes escribir o seguir.
          <button type="button" className="link" onClick={onSkip}>Seguir</button>
        </p>
      )}
      <p className="small">Sección: {sectionLabel}. Se puede seguir sin llenar la caja.</p>
      {store && store.total > 0 && <p className="small" role="status">En el almacén: {store.ready} de {store.total}.</p>}
      <textarea aria-label="Qué entendiste" value={text} onChange={(event) => setText(event.target.value)} placeholder="En tus palabras. El LaTeX va entre $." />
      {text.trim() && <div className="ask-preview" aria-hidden="true"><Rich text={text} /></div>}
      <button type="submit" disabled={busy || !text.trim()}>Enviar</button>
      {progress && <p className="small" role="status">{progress}</p>}
      {err && <p className="fail-reason">{err}</p>}
      {result?.empty && <p role="status">{result.note || "No hay frases guardadas de estos papers."}</p>}
      {result && !result.empty && (
        <div className="extracts">
          <p className="ask-label">estos papers dicen ({result.papers})</p>
          {result.matched > shown && <p className="small">Había {result.matched}. Muestro {shown}.</p>}
          {groups.map(([id, rows]) => (
            <section key={id} className="extract">
              <button type="button" className="link" onClick={() => onOpen?.(id, "cita en la caja")}>{id}</button>
              {rows.map((row: any, index: number) => <blockquote key={index}>{row.text}</blockquote>)}
            </section>
          ))}
        </div>
      )}
      {!result?.empty && (result?.note || hasParts) && (
        <div className="feedback generated">
          <p><span className="chip chip-simulado">generado</span></p>
          {result?.note && <p>{result.note}</p>}
          {PARTS.map(([id, label]) => (parts[id] || []).length ? (
            <section key={id}>
              <h3>{label}</h3>
              {(parts[id] || []).map((item: any, index: number) => (
                <p key={index}>
                  {item.text}
                  {item.cite && <> <q>{item.cite}</q></>}
                  {item.paper_id && <button type="button" className="link" onClick={() => onOpen?.(String(item.paper_id), "cita en la caja")}>{item.paper_id}</button>}
                  {item.verified && <span className="chip chip-simulado">verificado contra la cita</span>}
                  {id === "sin_respaldo" && <span className="small"> Ningún paper analizado lo menciona.</span>}
                </p>
              ))}
            </section>
          ) : null)}
        </div>
      )}
    </form>
  );
}
