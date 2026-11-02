"use client";
import { useEffect, useMemo, useState } from "react";
import { Block } from "@/lib/types";
import { Rich } from "@/lib/math";
import { ProvChip } from "../Bits";
import { bars } from "@/lib/tablechart.js";
import { Inlines } from "../Paper";
import { Ctx, plainOf } from "./inline";

export function TableChart({ model, n, predict = true }: { model: any; n: number; predict?: boolean }) {
  const [col, setCol] = useState<number>(model.numericCols[0]);
  const [sort, setSort] = useState<"original" | "desc" | "asc">("original");
  const [log, setLog] = useState(false);
  const data = useMemo(() => bars(model, col, { sort, log }), [model, col, sort, log]);
  const [ask, setAsk] = useState(false);               // hipótesis: predecir antes de ver
  const [guess, setGuess] = useState<string | null>(null);
  const top = useMemo(() => bars(model, col, { sort: "desc" })[0], [model, col]);
  const hide = ask && guess === null;
  useEffect(() => setGuess(null), [col, ask]);
  return (
    <div className="tchart" role="group" aria-label={`Gráfica de la Tabla ${n}`}>
      <div className="chips"><ProvChip kind="paper" text={`gráfica de la Tabla ${n}: valores del paper, sin cambiar`} /></div>
      <div className="tchart-tools">
        <div className="pills" role="tablist" aria-label="Columna">{model.numericCols.map((c: number) => <button key={c} role="tab" aria-selected={c === col} className={c === col ? "on" : ""} onClick={() => setCol(c)}>{model.headers[c] || `col. ${c + 1}`}</button>)}</div>
        <label>orden <select value={sort} onChange={(e) => setSort(e.target.value as any)}><option value="original">como en la tabla</option><option value="desc">mayor a menor</option><option value="asc">menor a mayor</option></select></label>
        <label className="chk"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> escala logarítmica</label>
      </div>
      {predict && <div className="tpredict">
        <label className="chk"><input type="checkbox" checked={ask} onChange={(e) => setAsk(e.target.checked)} /> predecir antes de ver <ProvChip kind="hipotesis" text="hipótesis" /></label>
        {hide && <span role="status">¿Cuál crees que tiene el valor más alto en «{model.headers[col]}»? Haz clic en una fila.</span>}
        {ask && guess !== null && top && <span role="status" className="tp-result">{guess === top.label ? `Acertaste: ${top.label} (${top.raw}).` : `Elegiste ${guess}; el más alto es ${top.label} (${top.raw}).`}</span>}
      </div>}
      <div className="tbars">
        {data.map((d: any) => (
          <div key={d.row} className={`tbar-row ${hide ? "hid" : ""} ${ask && guess === d.label ? "guess" : ""} ${ask && guess !== null && top && d.label === top.label ? "truth" : ""}`} data-row-label={d.label} onClick={hide ? () => setGuess(d.label) : undefined} onMouseEnter={() => window.dispatchEvent(new CustomEvent("rrm-row", { detail: d.label }))} onMouseLeave={() => window.dispatchEvent(new CustomEvent("rrm-row", { detail: "" }))}>
            <span className="tb-label" title={d.label}>{d.label}</span>
            <span className="tb-track"><i style={{ width: hide ? 0 : `${Math.max(1.5, d.frac * 100)}%` }} /></span>
            <span className="tb-val">{hide ? "?" : <Rich text={d.raw} />}</span>
          </div>
        ))}
      </div>
      <p className="small">{log ? "Escala logarítmica: la longitud no es proporcional al valor." : "Longitud proporcional al valor."} Se omiten las filas sin valor en esta columna. Para ver todo, la tabla sigue debajo.</p>
    </div>
  );
}

export function Table({ b, ctx, n, predict = true, still = false }: { b: Block; ctx: Ctx; n: number; predict?: boolean; still?: boolean }) {
  const [hc, setHc] = useState<number | null>(null);
  const [showChart, setShowChart] = useState(false);
  const [hl, setHl] = useState("");
  const [filter, setFilter] = useState("");
  const model = b.an;
  const chartable = model.numericCols.length > 0 && bars(model, model.numericCols[0]).length >= 3;
  useEffect(() => { const f = (e: any) => setHl(e.detail || ""); window.addEventListener("rrm-row", f); return () => window.removeEventListener("rrm-row", f); }, []);
  return (
    <figure className="table-fig" id={b.label || undefined} data-tab={b.id}>
      {chartable && !ctx.core && <div className="tchart-bar"><button className="tchart-toggle" aria-pressed={showChart} onClick={() => setShowChart((v) => !v)}>{showChart ? "Ocultar gráfica" : "Ver como gráfica"}</button></div>}
      {ctx.core && <input className="table-filter" aria-label="Filtrar filas" value={filter} placeholder="Filtrar filas" onChange={(e) => setFilter(e.target.value)} />}
      {showChart && !ctx.core && <TableChart model={model} n={n} predict={predict} />}
      <div className="table-wrap" onMouseLeave={() => setHc(null)}>
        <table data-hc={hc ?? undefined}>
          <thead>{model.headRows.map((hr: any[], ri: number) => (
            <tr key={ri}>{hr.map((c: any, ci: number) => <th key={ci} colSpan={c.span} data-c={c.col} className={hc !== null && hc >= c.col && hc < c.col + c.span ? "col-on" : ""} onMouseEnter={() => setHc(c.col)}><Inlines inls={c.c} ctx={ctx} /></th>)}</tr>
          ))}</thead>
          <tbody>
            {model.bodyRows.filter((r: any[]) => {
              const needle = filter.trim().toLowerCase();
              return !needle || r.some((c: any) => plainOf(c.c).toLowerCase().includes(needle));
            }).map((r: any[], ri: number) => (
              <tr key={ri} className={hl && plainOf(r[0].c).replace(/\[cite\]/g, "").trim() === hl ? "row-on" : ""} style={still ? undefined : { animationDelay: `${ri * 35}ms` }}>
                {r.map((c: any, ci: number) => <td key={ci} colSpan={c.span} data-c={c.col} className={hc !== null && hc >= c.col && hc < c.col + c.span ? "col-on" : ""} onMouseEnter={() => setHc(c.col)} data-pop={`t|${b.id}|${ri}|${c.col}`} tabIndex={0}><Inlines inls={c.c} ctx={ctx} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption><b>Tabla {n}.</b> <Inlines inls={b.caption} ctx={ctx} /></figcaption>
    </figure>
  );
}

export default Table;
