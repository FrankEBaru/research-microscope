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
        (err: any) => run.current === my && setSrv({ state: "off", claims: [], note: `Could not ask the server for Panorama (${explain(err)}). Using the in-browser simulator; both are simulated.` }),
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
    <section className="pano sim" aria-label="Panorama for any question">
      <div className="chips">
        <ProvChip kind="simulado" text={srv.state === "wait" ? "Asking the server for Panorama…" : serverMeta ? "Muse Spark on the server: model statements, verbatim quotes" : serverFallback ? "The model did not answer: simulated selection on the server" : srv.state === "ok" ? "Simulated selection on the server: term match, not a model" : "Muse Spark simulated: term match, not a model"} />
        <ProvChip kind="curado" text={serverMeta ? "statements written by Muse Spark" : "statements = terms from your question"} />
      </div>
      {srv.state === "wait" && <p className="warm" role="status" data-panorama-wait>Asking the server for Panorama. This can take up to 45 s. If Muse does not answer, the simulated selection is shown.</p>}
      {srv.note && <p className="muted small" role="status" data-srv-fallback>{srv.note}</p>}
      <form className="sim-ask" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setAsked(draft.trim()); }}>
        <input aria-label="Question for Panorama" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type a question" />
        <button type="submit">{asked === null ? "Build Panorama" : "Build again"}</button>
      </form>
      <div className="sim-opts">
        <label className="chk"><input type="checkbox" checked={predictOn} onChange={(e) => setPredictOn(e.target.checked)} /> predict before you look <ProvChip kind="hipotesis" text="hypothesis" /></label>
        <label className="chk"><input type="checkbox" checked={faults} onChange={(e) => setFaults(e.target.checked)} /> simulate model failures (to see the gate)</label>
      </div>
      {asked === null && <p className="muted">This burst has {ids.length} papers ({readable.length} readable{notRead ? `, ${notRead} could not be read or are still queued` : ""}). Ask anything: each paper contributes verbatim sentences and the matrix fills as they are read.</p>}
      {asked !== null && (
        <>
          <div className="sim-progress" role="status" aria-live="polite">
            <div className="coverage-bar"><div style={{ width: `${readable.length ? (100 * done) / readable.length : 100}%` }} /></div>
            <span>{finished ? `${nRead} of ${ids.length} papers read` : `reading… ${done} of ${readable.length}`}{notRead ? ` · ${notRead} unread (they do not count as “the paper does not say it”)` : ""}</span>
          </div>
          {finished && nRead === 0 && <p className="muted" role="alert">No paper in this burst could be read: there is nothing to count yet.</p>}
          {finished && predictOn && nRead > 0 && built.claims.some((c: any) => pred[c.id] === undefined) && (
            <div className="predict-banner" role="note"><b>Before you look, predict.</b> For each theme, choose how many of the {nRead} papers read you think contain a sentence. Then it is revealed and compared. <ProvChip kind="hipotesis" text="hypothesis: no evidence yet that it helps" />
              <button className="link" onClick={() => setPred(Object.fromEntries(built.claims.map((c: any) => [c.id, "skip"])))}>show all without predicting</button></div>
          )}
          {themes.length === 0 && finished && <p className="muted">No content terms in the question. Try words like “attention” or “scaling”.</p>}
          {built.claims.map((c: any) => {
            const cv = convergence(c, Math.max(nRead, 1)); const p = pred[c.id];
            const hidden = predictOn && finished && nRead > 0 && p === undefined;
            return (
              <article key={c.id} className="pano-claim" data-claim={c.id}>
                <h3>{c.statement}</h3>
                {hidden ? (
                  <div className="predict" role="group" aria-label="Predict before you look">
                    <span className="predict-q">In how many of the <b>{nRead}</b> papers do you think it appears?</span>
                    <span className="pills">{Array.from({ length: nRead + 1 }, (_, k) => <button key={k} aria-label={`I predict ${k}`} onClick={() => setPred((x) => ({ ...x, [c.id]: k }))}>{k}</button>)}</span>
                    <button className="link" onClick={() => setPred((x) => ({ ...x, [c.id]: "skip" }))}>show without predicting</button>
                  </div>
                ) : (
                  <>
                    <div className="conv" role="img" aria-label={`${cv.k} of ${cv.n} papers`}>
                      <div className="conv-track"><i style={{ width: pct(cv.p) }} />
                        {typeof p === "number" && nRead > 0 && <b className="guess" title="your prediction" style={{ left: pct(p / nRead) }} />}</div>
                      <span><b>{cv.k} of {cv.n}</b> papers read · Wilson 95%: {pct(cv.lo)}–{pct(cv.hi)}{typeof p === "number" ? ` · your prediction: ${p}${p === cv.k ? " (exact)" : ` (off by ${Math.abs(p - cv.k)})`}` : ""}</span>
                    </div>
                    <ul className="evi">
                      {c.evidence.map((e: any, i: number) => (
                        <li key={i}><span className="who">{nameOf(e.paper)}</span><blockquote>«<Rich text={e.quote} />»</blockquote>
                          <button className="link" onClick={() => open(e.paper, e.anchor.blockId)}>see where it says this →</button></li>
                      ))}
                      {!c.evidence.length && finished && <li className="muted small">No paper that was read has a sentence with this term. That does not mean the paper does not say it.</li>}
                    </ul>
                  </>
                )}
              </article>
            );
          })}
          {finished && (
            <p className="gate small" data-rejected={built.rejected.length}>
              <b>Gate:</b> {built.rejected.length ? `rejected ${built.rejected.length} selections that are not verbatim in their paper or come from a paper that was not read.` : "every selection exists verbatim in its paper."}
              {built.rejected.length > 0 && <details><summary>see what was rejected</summary><ul>{built.rejected.map((r: any, i: number) => <li key={i}><i>{r.reason}</i>: «{String(r.quote).slice(0, 90)}…»</li>)}</ul></details>}
            </p>
          )}
          {built.claims.length > 0 && (
            <>
              <h3 className="pano-h">Evidence matrix</h3>
              <div className="matrix-wrap"><table className="matrix">
                <thead><tr><th></th>{built.claims.map((c: any) => <th key={c.id} title={c.statement}>{termOf(c)}</th>)}</tr></thead>
                <tbody>{ids.map((id) => {
                  const st = readState(states[id]?.status); const arrived = id in docs;
                  return (
                    <tr key={id}><th scope="row">{nameOf(id)}{st === "abstract" ? " · abstract" : ""}</th>
                      {built.claims.map((c: any) => { const e = c.evidence.find((x: any) => x.paper === id);
                        return <td key={c.id}>{e ? <button className="dot yes" title={e.quote.replace(/\$/g, "")} aria-label={`${nameOf(id)}: has a sentence`} onClick={() => open(id, e.anchor.blockId)}>●</button>
                          : st === "failed" ? <span className="dot na" title="could not be read">×</span> : !arrived ? <span className="dot wait" title="reading">…</span> : <span className="dot no" title="no sentence in what was read">○</span>}</td>; })}
                    </tr>);
                })}</tbody>
              </table></div>
              <p className="small">● verbatim sentence (click to see it in the paper) · ○ no sentence in what was read · × could not be read · … reading. No supports/contradicts verdict: it only counts who has a sentence.</p>
            </>
          )}
        </>
      )}
    </section>
  );
}
