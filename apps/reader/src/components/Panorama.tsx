"use client";
import { Rich } from "@/lib/math";
import { convergence } from "@/lib/convergence.js";
import { proposeClaims, museMode } from "@/lib/muse.js";
import { coverage } from "@/lib/panorama.js";
import { ProvChip } from "./Bits";
import { useState } from "react";
import SimPanorama from "./SimPanorama";

const pct = (x: number) => `${Math.round(100 * x)}%`;

/** Panorama (revisión viva): frases literales de cada paper, matriz de evidencia y convergencia CONTADA. Sin veredicto. */
export default function Panorama({ q, papers, content, go }: any) {
  const [mode, setMode] = useState<"curada" | "libre">("curada");
  const ids0: string[] = q.clusters.flatMap((c: any) => c.papers.map((p: any) => p.id));
  const owner = (id: string) => q.clusters.find((c: any) => c.papers.some((p: any) => p.id === id));
  const states = Object.fromEntries(ids0.map((i) => [i, { status: papers[i].full ? "done" : "abstract_only" }]));
  const nm = (id: string) => `${papers[id].authors[0]?.split(" ").pop()} ${papers[id].date?.slice(0, 4)}`;
  const modes = (
    <div className="view-toggle" role="tablist" aria-label="Tipo de Panorama">
      <button className={mode === "curada" ? "on" : ""} onClick={() => setMode("curada")}>Curada</button>
      <button className={mode === "libre" ? "on" : ""} onClick={() => setMode("libre")}>Cualquier pregunta <span className="chip chip-simulado">simulado</span></button>
    </div>
  );
  if (mode === "libre") return <>{modes}<SimPanorama question={q.text} ids={ids0} states={states} getDoc={async (id: string) => papers[id]} nameOf={nm} open={(id, b) => go({ q: q.id, c: owner(id).id, p: id, b })} /></>;
  const pan = proposeClaims(content, q.id);
  const ids: string[] = q.clusters.flatMap((c: any) => c.papers.map((p: any) => p.id));
  const clusterOf = (id: string) => q.clusters.find((c: any) => c.papers.some((p: any) => p.id === id));
  if (!pan) return <>{modes}<p className="muted">Todavía no hay Panorama curado para esta pregunta.</p></>;
  const name = (id: string) => `${papers[id].authors[0]?.split(" ").pop()} ${papers[id].date?.slice(0, 4)}`;
  const full = ids.filter((i) => papers[i].full).length;
  const open = (id: string, blockId: string) => go({ q: q.id, c: clusterOf(id).id, p: id, b: blockId });
  return (
    <>{modes}<section className="pano" aria-label="Panorama">
      <div className="chips">
        <ProvChip kind="curado" text="enunciados y agrupación curados" />
        <ProvChip kind="simulado" text={`paso de Muse Spark: ${museMode()}`} />
      </div>
      <p className="pano-lead">Revisión viva de <b>{ids.length} papers leídos</b> ({full} con texto completo, {ids.length - full} solo abstract). Cada frase es literal y el compilador comprueba que exista en su paper. <b>No es un veredicto</b>: «convergencia» cuenta cuántos de los papers leídos tienen una frase que respalda el enunciado.</p>
      {pan.claims.map((c: any) => {
        const cv = convergence(c, ids.length); const have = new Set(c.evidence.map((e: any) => e.paper));
        const missing = ids.filter((i) => !have.has(i));
        return (
          <article key={c.id} className="pano-claim">
            <h3>{c.statement}</h3>
            <div className="conv" role="img" aria-label={`${cv.k} de ${cv.n} papers`}>
              <div className="conv-track"><i style={{ width: pct(cv.p) }} /><b className="whisker" style={{ left: pct(cv.lo), width: `${Math.max(1, Math.round(100 * (cv.hi - cv.lo)))}%` }} /></div>
              <span><b>{cv.k} de {cv.n}</b> papers leídos · intervalo de Wilson 95%: {pct(cv.lo)}–{pct(cv.hi)}</span>
            </div>
            <ul className="evi">
              {c.evidence.map((e: any, i: number) => (
                <li key={i}><span className="who">{name(e.paper)}</span><blockquote>«<Rich text={e.quote} />»</blockquote>
                  <button className="link" onClick={() => open(e.paper, e.anchor.blockId)}>ver dónde lo dice →</button></li>
              ))}
            </ul>
            {missing.length > 0 && <p className="muted small">Sin frase en lo leído: {missing.map(name).join(", ")}. (No es lo mismo que «no lo dice»: solo se leyó el abstract de la mayoría.)</p>}
          </article>
        );
      })}
      <h3 className="pano-h">Matriz de evidencia</h3>
      <div className="matrix-wrap"><table className="matrix">
        <thead><tr><th></th>{pan.claims.map((c: any) => <th key={c.id} title={c.statement}>{c.statement.split(" ").slice(0, 5).join(" ")}…</th>)}</tr></thead>
        <tbody>{ids.map((id) => (
          <tr key={id}><th scope="row">{name(id)}</th>
            {pan.claims.map((c: any) => { const e = c.evidence.find((x: any) => x.paper === id);
              return <td key={c.id}>{e ? <button className="dot yes" title={e.quote.replace(/\$/g, "")} aria-label={`${name(id)}: tiene frase`} onClick={() => open(id, e.anchor.blockId)}>●</button> : <span className="dot no" title="sin frase en lo leído">○</span>}</td>; })}
          </tr>))}</tbody>
      </table></div>
      <p className="small">● con frase literal (clic para verla en el paper) · ○ sin frase en lo leído. En el motor real, <b>Muse Spark propondría las selecciones</b> (índices de frases, nunca texto nuevo) y esta misma compuerta las validaría; hoy el paso está simulado y no se llama a ningún modelo.</p>
    </section></>
  );
}

/** Panorama en vivo: HOY solo la cobertura (qué papers de la ráfaga cuentan como leídos). Los enunciados llegan con el paso real de Muse Spark. */
export function LiveCoverage({ ids, states }: { ids: string[]; states: Record<string, any> }) {
  if (!ids.length) return null;
  const c = coverage(ids, states);
  const rows: [string, number][] = [["texto completo", c.full], ["solo abstract", c.abstract], ["no se pudo leer", c.failed], ["en cola o leyendo", c.pending]];
  return (
    <section className="pano live-cov" aria-label="Cobertura del Panorama">
      <div className="chips"><ProvChip kind="calculo" text="cuenta sobre el estado del motor" /></div>
      <p className="pano-lead">Panorama de esta ráfaga: <b>{c.n} de {c.total} papers leídos</b>. La convergencia se contará solo sobre los leídos; los que fallaron o siguen en cola no entran al denominador ni cuentan como «no lo dice».</p>
      <ul className="cov-rows">{rows.map(([k, v]) => <li key={k} data-k={k}><b>{v}</b> {k}</li>)}</ul>
      {c.abstract > 0 && <p className="muted small">«Solo abstract»: sus frases vendrán del abstract y se rotularán así.</p>}
      <p className="small">Los enunciados y sus frases literales requieren el paso de Muse Spark en el backend (no se llama sin permiso de Franklin); la UI validará cada frase contra su paper antes de mostrarla.</p>
    </section>
  );
}
