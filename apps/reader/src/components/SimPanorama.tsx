"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Rich } from "@/lib/math";
import { convergence } from "@/lib/convergence.js";
import { runSimulated, assemble, themesOf, addFaults } from "@/lib/musesim.js";
import { explain, liveEnabled, panorama as fetchPanorama } from "@/lib/backend.js";
import { buildPanorama, readState } from "@/lib/panorama.js";
import { ProvChip } from "./Bits";

const pct = (x: number) => `${Math.round(100 * x)}%`;

/**
 * Panorama para CUALQUIER pregunta con Muse Spark SIMULADO. Los papers entran uno a uno (la matriz se llena en vivo); cada selección
 * pasa por la compuerta (`buildPanorama`). Hipótesis en prueba: «predecir antes de ver» (opcional).
 */
export default function SimPanorama({ question, ids, states, getDoc, nameOf, open, autorun }: {
  question: string; ids: string[]; states: Record<string, any>; getDoc: (id: string) => Promise<any>; nameOf: (id: string) => string; open: (id: string, blockId: string) => void; autorun?: boolean;
}) {
  const [draft, setDraft] = useState(question);
  const [asked, setAsked] = useState<string | null>(autorun ? question : null);
  // En la ráfaga curada las fallas empiezan prendidas para ver la compuerta. En vivo quedan apagadas: si no, tapan el Panorama de Muse.
  const [faults, setFaults] = useState(!liveEnabled());
  const [predictOn, setPredictOn] = useState(true);
  const [docs, setDocs] = useState<Record<string, any>>({});
  const [per, setPer] = useState<Record<string, any[]>>({});
  const [done, setDone] = useState(0);
  const [pred, setPred] = useState<Record<string, number | "skip">>({});
  const [themes, setThemes] = useState<any[]>([]);
  // Selecciones SIMULADAS del servidor (POST /panorama). wait: pedido en curso; ok: se usan; off: no aplica o cayó al simulador del navegador.
  const [srv, setSrv] = useState<{ state: "off" | "wait" | "ok"; claims: any[]; note: string }>({ state: "off", claims: [], note: "" });
  const run = useRef(0);
  const readable = useMemo(() => ids.filter((i) => ["full", "abstract"].includes(readState(states[i]?.status))), [ids, states]);

  useEffect(() => {
    if (asked === null) return;
    const my = ++run.current; setDocs({}); setPer({}); setDone(0); setPred({});
    const viaServer = liveEnabled() && readable.length > 0 && readable.every((i) => /^\d+$/.test(i));
    setSrv({ state: viaServer ? "wait" : "off", claims: [], note: "" });
    if (viaServer) {
      fetchPanorama(asked, readable).then(
        (claims: any[]) => run.current === my && setSrv({ state: "ok", claims: Array.isArray(claims) ? claims : [], note: "" }),
        (err: any) => run.current === my && setSrv({ state: "off", claims: [], note: `No se pudo pedir el Panorama al servidor (${explain(err)}) Se usa el simulador del navegador; ambos son simulados.` }),
      );
    }
    runSimulated({
      question: asked, ids: readable, getDoc, latencyMs: (window as any).__RRM_SIM_MS ?? 220, cancelled: () => run.current !== my,
      onPaper: (id: string, doc: any, sel: any[] | null) => { setDocs((d) => ({ ...d, [id]: doc })); setPer((p) => ({ ...p, [id]: sel || [] })); setDone((n) => n + 1); },
    }).then((t: any[]) => run.current === my && setThemes(t));
    setThemes(themesOf(asked));
  }, [asked, readable.join(",")]);

  const finished = asked !== null && done >= readable.length && srv.state !== "wait";
  const claims = useMemo(
    () => srv.state === "ok" ? (faults ? addFaults(srv.claims, readable[0] || "") : srv.claims) : srv.state === "wait" ? [] : assemble(themes, per, faults, readable[0] || ""),
    [themes, per, faults, srv, readable.join(",")],
  );
  const termOf = (c: any) => {
    const marked = /«([^»]*)»/.exec(c.statement || "")?.[1];
    if (marked) return marked;
    if (c.mode === "meta" && c.statement) return c.statement.slice(0, 48);
    return themes.find((t) => t.id === c.id)?.term ?? c.id;
  };
  const serverMeta = srv.state === "ok" && srv.claims.some((c) => c.mode === "meta" && !c.fallback);
  const serverFallback = srv.state === "ok" && srv.claims.some((c) => c.fallback);
  const built = useMemo(() => buildPanorama(claims, docs, states), [claims, docs, states]);
  const nRead = Object.values(docs).filter(Boolean).length;
  const notRead = ids.length - readable.length;

  return (
    <section className="pano sim" aria-label="Panorama con cualquier pregunta">
      <div className="chips">
        <ProvChip kind="simulado" text={srv.state === "wait" ? "Pidiendo el Panorama al servidor…" : serverMeta ? "Muse Spark en el servidor: enunciados del modelo, citas literales" : serverFallback ? "El modelo no respondió: selección simulada en el servidor" : srv.state === "ok" ? "Selección simulada en el servidor: coincidencia de términos, no un modelo" : "Muse Spark simulado: coincidencia de términos, no un modelo"} />
        <ProvChip kind="curado" text={serverMeta ? "enunciados escritos por Muse Spark" : "enunciados = términos de tu pregunta"} />
      </div>
      {srv.state === "wait" && <p className="warm" role="status" data-panorama-wait>Pidiendo el Panorama al servidor. Puede tardar hasta 45 s. Si Muse no responde, se muestra la selección simulada.</p>}
      {srv.note && <p className="muted small" role="status" data-srv-fallback>{srv.note}</p>}
      <form className="sim-ask" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setAsked(draft.trim()); }}>
        <input aria-label="Pregunta para el Panorama" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Escribe una pregunta (español o inglés)" />
        <button type="submit">{asked === null ? "Armar Panorama" : "Volver a armar"}</button>
      </form>
      <div className="sim-opts">
        <label className="chk"><input type="checkbox" checked={predictOn} onChange={(e) => setPredictOn(e.target.checked)} /> predecir antes de ver <ProvChip kind="hipotesis" text="hipótesis" /></label>
        <label className="chk"><input type="checkbox" checked={faults} onChange={(e) => setFaults(e.target.checked)} /> simular fallas del modelo (para ver la compuerta)</label>
      </div>
      {asked === null && <p className="muted">Hay {ids.length} papers en esta ráfaga ({readable.length} legibles{notRead ? `, ${notRead} no se pudieron leer o siguen en cola` : ""}). Pregunta lo que quieras: cada papel aporta frases literales y la matriz se llena a medida que se leen.</p>}
      {asked !== null && (
        <>
          <div className="sim-progress" role="status" aria-live="polite">
            <div className="coverage-bar"><div style={{ width: `${readable.length ? (100 * done) / readable.length : 100}%` }} /></div>
            <span>{finished ? `${nRead} de ${ids.length} papers leídos` : `leyendo… ${done} de ${readable.length}`}{notRead ? ` · ${notRead} sin leer (no cuentan como «no lo dice»)` : ""}</span>
          </div>
          {finished && nRead === 0 && <p className="muted" role="alert">No se pudo leer ningún paper de la ráfaga: no hay nada que contar todavía.</p>}
          {finished && predictOn && nRead > 0 && built.claims.some((c: any) => pred[c.id] === undefined) && (
            <div className="predict-banner" role="note"><b>Antes de ver, predice.</b> Para cada tema, elige en cuántos de los {nRead} papers leídos crees que hay una frase. Luego se revela y se compara. <ProvChip kind="hipotesis" text="hipótesis: aún sin evidencia de que ayude" />
              <button className="link" onClick={() => setPred(Object.fromEntries(built.claims.map((c: any) => [c.id, "skip"])))}>ver todo sin predecir</button></div>
          )}
          {themes.length === 0 && finished && <p className="muted">No encontré términos de contenido en la pregunta. Prueba con palabras como «attention» o «escalado».</p>}
          {built.claims.map((c: any) => {
            const cv = convergence(c, Math.max(nRead, 1)); const p = pred[c.id];
            const hidden = predictOn && finished && nRead > 0 && p === undefined;
            return (
              <article key={c.id} className="pano-claim" data-claim={c.id}>
                <h3>{c.statement}</h3>
                {hidden ? (
                  <div className="predict" role="group" aria-label="Predice antes de ver">
                    <span className="predict-q">¿En cuántos de los <b>{nRead}</b> papers crees que aparece?</span>
                    <span className="pills">{Array.from({ length: nRead + 1 }, (_, k) => <button key={k} aria-label={`predigo ${k}`} onClick={() => setPred((x) => ({ ...x, [c.id]: k }))}>{k}</button>)}</span>
                    <button className="link" onClick={() => setPred((x) => ({ ...x, [c.id]: "skip" }))}>ver sin predecir</button>
                  </div>
                ) : (
                  <>
                    <div className="conv" role="img" aria-label={`${cv.k} de ${cv.n} papers`}>
                      <div className="conv-track"><i style={{ width: pct(cv.p) }} />
                        {typeof p === "number" && nRead > 0 && <b className="guess" title="tu predicción" style={{ left: pct(p / nRead) }} />}</div>
                      <span><b>{cv.k} de {cv.n}</b> papers leídos · Wilson 95%: {pct(cv.lo)}–{pct(cv.hi)}{typeof p === "number" ? ` · tu predicción: ${p}${p === cv.k ? " (acertaste)" : ` (diferencia ${Math.abs(p - cv.k)})`}` : ""}</span>
                    </div>
                    <ul className="evi">
                      {c.evidence.map((e: any, i: number) => (
                        <li key={i}><span className="who">{nameOf(e.paper)}</span><blockquote>«<Rich text={e.quote} />»</blockquote>
                          <button className="link" onClick={() => open(e.paper, e.anchor.blockId)}>ver dónde lo dice →</button></li>
                      ))}
                      {!c.evidence.length && finished && <li className="muted small">Ningún paper leído tiene una frase con este término. No significa que no lo diga.</li>}
                    </ul>
                  </>
                )}
              </article>
            );
          })}
          {finished && (
            <p className="gate small" data-rejected={built.rejected.length}>
              <b>Compuerta:</b> {built.rejected.length ? `rechazó ${built.rejected.length} selecciones que no existen literalmente en su paper o son de un paper no leído.` : "todas las selecciones existen literalmente en su paper."}
              {built.rejected.length > 0 && <details><summary>ver qué rechazó</summary><ul>{built.rejected.map((r: any, i: number) => <li key={i}><i>{r.reason}</i>: «{String(r.quote).slice(0, 90)}…»</li>)}</ul></details>}
            </p>
          )}
          {built.claims.length > 0 && (
            <>
              <h3 className="pano-h">Matriz de evidencia</h3>
              <div className="matrix-wrap"><table className="matrix">
                <thead><tr><th></th>{built.claims.map((c: any) => <th key={c.id} title={c.statement}>{termOf(c)}</th>)}</tr></thead>
                <tbody>{ids.map((id) => {
                  const st = readState(states[id]?.status); const arrived = id in docs;
                  return (
                    <tr key={id}><th scope="row">{nameOf(id)}{st === "abstract" ? " · abstract" : ""}</th>
                      {built.claims.map((c: any) => { const e = c.evidence.find((x: any) => x.paper === id);
                        return <td key={c.id}>{e ? <button className="dot yes" title={e.quote.replace(/\$/g, "")} aria-label={`${nameOf(id)}: tiene frase`} onClick={() => open(id, e.anchor.blockId)}>●</button>
                          : st === "failed" ? <span className="dot na" title="no se pudo leer">×</span> : !arrived ? <span className="dot wait" title="leyendo">…</span> : <span className="dot no" title="sin frase en lo leído">○</span>}</td>; })}
                    </tr>);
                })}</tbody>
              </table></div>
              <p className="small">● frase literal (clic para verla en el paper) · ○ sin frase en lo leído · × no se pudo leer · … leyendo. Sin veredicto de apoya/contradice: solo se cuenta quién tiene una frase.</p>
            </>
          )}
        </>
      )}
    </section>
  );
}
