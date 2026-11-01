"use client";
import { useEffect, useRef, useState } from "react";
import { Rich } from "@/lib/math";
import { ask, explain, preparePhrases } from "@/lib/backend.js";

const PARTS = [
  ["coincide", "Coincide"],
  ["contradice", "Contradice"],
  ["sin_respaldo", "Sin respaldo"],
  ["te_falto", "Te faltó"],
] as const;

function boxKey(id?: string) {
  return id ? `rrm-ask:${id}` : "";
}

function loadBox(id?: string) {
  const key = boxKey(id);
  if (!key || typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveBox(id: string | undefined, snap: any) {
  const key = boxKey(id);
  if (!key || typeof sessionStorage === "undefined") return;
  try { sessionStorage.setItem(key, JSON.stringify(snap)); } catch { /* el paper sigue; la caja lo dice */ }
}

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

export default function AskBox({ sectionLabel, ids, focusId, onOpen, closed, onSkip, onPromote, onName }: {
  sectionLabel: string;
  ids?: string[];
  focusId?: string;
  onOpen?: (id: string, why: string) => void;
  closed?: boolean;
  onSkip?: () => void;
  onPromote?: () => void;
  onName?: (id: string, section?: string) => string;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [store, setStore] = useState<any>(null);
  const [err, setErr] = useState("");
  const owner = useRef<string | undefined>(undefined);
  const [progress, setProgress] = useState("");
  const [phraseLine, setPhraseLine] = useState("");
  const phrases = useRef<Promise<unknown> | null>(null);
  const key = (ids || []).join(",");
  useEffect(() => {
    if (!focusId) return;
    if (owner.current !== focusId) {
      owner.current = focusId;
      const next = loadBox(focusId);
      setText(next?.text || "");
      setResult(next?.result ?? null);
      setErr(next?.err || "");
      setStore(next?.store ?? null);
      return;
    }
    saveBox(focusId, { text, result, err, store });
  }, [focusId, text, result, err, store]);
  useEffect(() => {
    if (!focusId) { setPhraseLine(""); phrases.current = null; return; }
    let stop = false;
    const t0 = Date.now();
    setPhraseLine("preparando frases de este paper… 0 s");
    const clock = window.setInterval(() => {
      setPhraseLine(`preparando frases de este paper… ${Math.round((Date.now() - t0) / 1000)} s`);
    }, 400);
    const job = preparePhrases(focusId).then(
      () => { if (!stop) { window.clearInterval(clock); setPhraseLine(""); } },
      () => { if (!stop) { window.clearInterval(clock); setPhraseLine(""); } },
    );
    phrases.current = job;
    return () => { stop = true; window.clearInterval(clock); };
  }, [focusId]);
  const keepStore = (body: any) => {
    const next = body?.store;
    if (!next) return;
    setStore((prev: any) => {
      if (!prev || prev.total !== next.total) return next;
      return { ...next, ready: Math.max(prev.ready || 0, next.ready || 0) };
    });
  };
  useEffect(() => {
    if (!key) return;
    let stop = false;
    let timer = 0;
    const tick = async () => {
      try {
        const body = await ask(ids || [], "", "", focusId);
        if (stop) return;
        keepStore(body);
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
    onPromote?.();
    let held = "";
    try {
      if (phrases.current) await phrases.current;
      setPhraseLine("");
      setProgress("buscando frases en los papers…");
      let ranked: any = null;
      for (let attempt = 0; attempt < 60; attempt++) {
        ranked = await ask(ids || [], text, "frases", focusId);
        setResult(ranked);
        keepStore(ranked);
        if (!/Preparando los vectores/.test(ranked?.note || "")) break;
        setProgress("preparando frases de este paper…");
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
      }
      if (ranked?.empty) return;
      setProgress("revisando cada cita…");
      const body = await ask(ids || [], text, "revisar", focusId);
      if (body?.empty) setErr(body.note || "La revisión volvió vacía.");
      else { setResult(body); keepStore(body); }
    } catch (err: any) {
      const timed = err?.kind === "timeout" || err?.name === "AbortError";
      if (timed) held = "Sigue la revisión de las citas. Vuelve a enviar si no aparece.";
      else setErr(explain(err));
    } finally {
      setBusy(false);
      setProgress(held);
    }
  };
  const groups = group(result?.extracts || []);
  const parts = result?.parts || {};
  const hasParts = PARTS.some(([id]) => (parts[id] || []).length);
  const shown = (result?.extracts || []).length;
  const citeOf = (id: string, section?: string) => onName?.(String(id), section) || "paper";
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
      {(phraseLine || progress) && <p className="small" role="status">{phraseLine || progress}</p>}
      {err && <p className="fail-reason">{err}</p>}
      {result?.empty && <p role="status">{result.note || "No hay frases guardadas de estos papers."}</p>}
      {result && !result.empty && (
        <div className="extracts">
          <p className="ask-label">estos papers dicen ({result.papers})</p>
          {result.matched > shown && <p className="small">Encontré {result.matched} frases cercanas. Aquí van las {shown} más próximas a lo que escribiste.</p>}
          {groups.map(([id, rows]) => (
            <section key={id} className="extract">
              <button type="button" className="link" onClick={() => onOpen?.(id, "cita en la caja")}>{citeOf(id, rows[0]?.section)}</button>
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
                  {item.paper_id && <button type="button" className="link" onClick={() => onOpen?.(String(item.paper_id), "cita en la caja")}>{citeOf(String(item.paper_id), item.section)}</button>}
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
