"use client";
import { Rich } from "@/lib/math";
import { convergence } from "@/lib/convergence.js";
import { proposeClaims, museMode } from "@/lib/muse.js";
import { coverage } from "@/lib/panorama.js";
import { ProvChip } from "./Bits";
import { useMemo, useState } from "react";
import SimPanorama from "./SimPanorama";

const pct = (x: number) => `${Math.round(100 * x)}%`;

/** Panorama (revisión viva): frases literales de cada paper, matriz de evidencia y convergencia CONTADA. Sin veredicto. */
export default function Panorama({ q, papers, content, go }: any) {
  const [mode, setMode] = useState<"curada" | "libre">("curada");
  const ids0: string[] = q.clusters.flatMap((c: any) => c.papers.map((p: any) => p.id));
  const owner = (id: string) => q.clusters.find((c: any) => c.papers.some((p: any) => p.id === id));
  const states = useMemo(() => Object.fromEntries(ids0.map((i) => [i, { status: papers[i].full ? "done" : "abstract_only" }])), [papers, q]);
  const nm = (id: string) => `${papers[id].authors[0]?.split(" ").pop()} ${papers[id].date?.slice(0, 4)}`;
  const modes = (
    <div className="view-toggle" role="tablist" aria-label="Panorama type">
      <button className={mode === "curada" ? "on" : ""} onClick={() => setMode("curada")}>Curated</button>
      <button className={mode === "libre" ? "on" : ""} onClick={() => setMode("libre")}>Any question <span className="chip chip-simulado">simulated</span></button>
    </div>
  );
  if (mode === "libre") return <>{modes}<SimPanorama question={q.text} ids={ids0} states={states} getDoc={async (id: string) => papers[id]} nameOf={nm} open={(id, b) => go({ q: q.id, c: owner(id).id, p: id, b })} /></>;
  const pan = proposeClaims(content, q.id);
  const ids: string[] = q.clusters.flatMap((c: any) => c.papers.map((p: any) => p.id));
  const clusterOf = (id: string) => q.clusters.find((c: any) => c.papers.some((p: any) => p.id === id));
  if (!pan) return <>{modes}<p className="muted">There is no curated Panorama for this question yet.</p></>;
  const name = (id: string) => `${papers[id].authors[0]?.split(" ").pop()} ${papers[id].date?.slice(0, 4)}`;
  const full = ids.filter((i) => papers[i].full).length;
  const open = (id: string, blockId: string) => go({ q: q.id, c: clusterOf(id).id, p: id, b: blockId });
  return (
    <>{modes}<section className="pano" aria-label="Panorama">
      <div className="chips">
        <ProvChip kind="curado" text="curated statements and grouping" />
        <ProvChip kind="simulado" text={`paso de Muse Spark: ${museMode()}`} />
      </div>
      <p className="pano-lead">A live review of <b>{ids.length} papers read</b> ({full} with full text, {ids.length - full} abstract only). Each sentence is verbatim and the compiler checks that it exists in its paper. <b>This is not a verdict</b>: “convergence” counts how many of the papers read have a sentence that supports the statement.</p>
      {pan.claims.map((c: any) => {
        const cv = convergence(c, ids.length); const have = new Set(c.evidence.map((e: any) => e.paper));
        const missing = ids.filter((i) => !have.has(i));
        return (
          <article key={c.id} className="pano-claim">
            <h3>{c.statement}</h3>
            <div className="conv" role="img" aria-label={`${cv.k} of ${cv.n} papers`}>
              <div className="conv-track"><i style={{ width: pct(cv.p) }} /><b className="whisker" style={{ left: pct(cv.lo), width: `${Math.max(1, Math.round(100 * (cv.hi - cv.lo)))}%` }} /></div>
              <span><b>{cv.k} of {cv.n}</b> papers read · Wilson 95% interval: {pct(cv.lo)}–{pct(cv.hi)}</span>
            </div>
            <ul className="evi">
              {c.evidence.map((e: any, i: number) => (
                <li key={i}><span className="who">{name(e.paper)}</span><blockquote>«<Rich text={e.quote} />»</blockquote>
                  <button className="link" onClick={() => open(e.paper, e.anchor.blockId)}>see where it says this →</button></li>
              ))}
            </ul>
            {missing.length > 0 && <p className="muted small">No sentence in what was read: {missing.map(name).join(", ")}. (That is not the same as “the paper does not say it”: only the abstract was read for most of them.)</p>}
          </article>
        );
      })}
      <h3 className="pano-h">Evidence matrix</h3>
      <div className="matrix-wrap"><table className="matrix">
        <thead><tr><th></th>{pan.claims.map((c: any) => <th key={c.id} title={c.statement}>{c.statement.split(" ").slice(0, 5).join(" ")}…</th>)}</tr></thead>
        <tbody>{ids.map((id) => (
          <tr key={id}><th scope="row">{name(id)}</th>
            {pan.claims.map((c: any) => { const e = c.evidence.find((x: any) => x.paper === id);
              return <td key={c.id}>{e ? <button className="dot yes" title={e.quote.replace(/\$/g, "")} aria-label={`${name(id)}: has a sentence`} onClick={() => open(id, e.anchor.blockId)}>●</button> : <span className="dot no" title="no sentence in what was read">○</span>}</td>; })}
          </tr>))}</tbody>
      </table></div>
      <p className="small">● verbatim sentence (click to see it in the paper) · ○ no sentence in what was read. In the real engine, <b>Muse Spark would propose the selections</b> (sentence indexes, never new text) and this same gate would check them; today that step is simulated and no model is called.</p>
    </section></>
  );
}

/** Panorama en vivo: HOY solo la cobertura (qué papers de la ráfaga cuentan como leídos). Los enunciados llegan con el paso real de Muse Spark. */
export function LiveCoverage({ ids, states }: { ids: string[]; states: Record<string, any> }) {
  if (!ids.length) return null;
  const c = coverage(ids, states);
  const rows: [string, number][] = [["full text", c.full], ["abstract only", c.abstract], ["could not be read", c.failed], ["queued or reading", c.pending]];
  return (
    <section className="pano live-cov" aria-label="Panorama coverage">
      <div className="chips"><ProvChip kind="calculo" text="counted from the engine state" /></div>
      <p className="pano-lead">Panorama for this burst: <b>{c.n} of {c.total} papers read</b>. Convergence counts only papers that were read; failed or queued papers stay out of the denominator and do not count as “the paper does not say it”.</p>
      <ul className="cov-rows">{rows.map(([k, v]) => <li key={k} data-k={k}><b>{v}</b> {k}</li>)}</ul>
      {c.abstract > 0 && <p className="muted small">“Abstract only”: sentences will come from the abstract and be labeled that way.</p>}
      <p className="small">Statements and verbatim sentences need the Muse Spark step on the backend; the UI checks each sentence against its paper before showing it.</p>
    </section>
  );
}
