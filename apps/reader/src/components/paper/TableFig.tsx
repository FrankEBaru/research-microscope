"use client";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Block } from "@/lib/types";
import { Rich } from "@/lib/math";
import { axisMarks, bars } from "@/lib/tablechart.js";
import { sortedRows } from "@/lib/tablesort.js";
import { Prov, Switch, Tabs } from "@/components/ui";
import { Inlines } from "../Paper";
import { Ctx, plainOf } from "./inline";
import "@/styles/table.css";

const rowLabel = (cell: any) => plainOf(cell?.c).replace(/\[cite\]/g, "").trim();
const ping = (id: string, label: string) => window.dispatchEvent(new CustomEvent("rrm-row", { detail: { id, label } }));
type Sort = { col: number; dir: "asc" | "desc" } | null;

export function TableChart({ model, n, predict = true, tableId }: { model: any; n: number; predict?: boolean; tableId: string }) {
  const cols = model.numericCols as number[];
  const [col, setCol] = useState<number>(cols[0]);
  const [sort, setSort] = useState<"original" | "desc" | "asc">("original");
  const [log, setLog] = useState(false);
  const [open, setOpen] = useState(false);
  const [ask, setAsk] = useState(false);
  const [guess, setGuess] = useState<string | null>(null);
  const [hot, setHot] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const data = useMemo(() => bars(model, col, { sort, log }), [model, col, sort, log]);
  const top = useMemo(() => bars(model, col, { sort: "desc" })[0], [model, col]);
  const marks = useMemo(() => axisMarks(data, { log }), [data, log]);
  const hide = ask && guess === null;
  const max = top?.value;
  useEffect(() => setGuess(null), [col, ask]);
  useEffect(() => {
    const f = (e: any) => { const d = e.detail; if (!d || d.id !== tableId) return; setHot(d.label || ""); };
    window.addEventListener("rrm-row", f);
    return () => window.removeEventListener("rrm-row", f);
  }, [tableId]);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: PointerEvent) => { if (!menuRef.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);
  return (
    <div className="tchart" role="group" aria-label={`Chart of Table ${n}`}>
      <div className="fig-h chips">
        <h3>Table {n} as a chart</h3>
        <Prov kind="paper" text="paper values" />
      </div>
      <div className="fc">
        <Tabs
          className="pills"
          label="Column"
          value={String(col)}
          onChange={(v) => setCol(Number(v))}
          options={cols.map((c) => ({ value: String(c), label: <Rich text={model.headers[c] || `Column ${c + 1}`} /> }))}
        />
        <div className="fc-r">
          {predict && <Switch checked={ask} onChange={setAsk} label="Predict first" />}
          <div className="tmore" ref={menuRef}>
            <button type="button" className="more press" aria-expanded={open} aria-label="Chart options" onClick={() => setOpen((v) => !v)}>•••</button>
            <div className="tmore-panel" hidden={!open}>
              <label className="torder">Order
                <select value={sort} onChange={(e) => setSort(e.target.value as "original" | "desc" | "asc")}>
                  <option value="original">As in the table</option>
                  <option value="desc">High to low</option>
                  <option value="asc">Low to high</option>
                </select>
              </label>
              <Switch checked={log} onChange={setLog} label="Logarithmic scale" />
            </div>
          </div>
        </div>
      </div>
      {hide && <span className="sr-only" role="status">Choose the row you think is highest in {model.headers[col]}.</span>}
      {ask && guess !== null && top && <p className="fig-msg tp-result" role="status">You chose <b><Rich text={guess} /></b>. The highest is <b><Rich text={top.label} /></b>.</p>}
      <div className={`tbars${hide ? " bars--q" : ""}`}>
        {data.map((d: any) => (
          <div
            key={d.row}
            className={`tbar-row${hide ? " hid" : ""}${!hide && d.value === max ? " is-max" : ""}${hot === d.label ? " is-hover" : ""}`}
            data-row-label={d.label}
            role={hide ? "button" : undefined}
            tabIndex={hide ? 0 : undefined}
            onClick={hide ? () => setGuess(d.label) : undefined}
            onKeyDown={hide ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setGuess(d.label); } } : undefined}
            onMouseEnter={() => ping(tableId, d.label)}
            onMouseLeave={() => ping(tableId, "")}
          >
            <span className="tb-label" title={d.label}><Rich text={d.label} /></span>
            <span className="tb-track">{hide ? <i className="b-q" /> : <i className={`fill${d.value === max ? " is-max" : ""}`} style={{ width: `${Math.max(1.5, d.frac * 100)}%` }} />}</span>
            <span className="tb-val tnum">{hide ? "?" : <Rich text={d.raw} />}</span>
          </div>
        ))}
      </div>
      {!hide && marks.length > 0 && (
        <div className="b-ax" aria-hidden="true">
          <span />
          <div className="b-t">
            {marks.map((m: { at: number; label: string }, i: number) => (
              <i key={i} className="tnum" style={{ left: `${m.at * 100}%`, transform: i === 0 ? "none" : i === marks.length - 1 ? "translateX(-100%)" : "translateX(-50%)" }}>{m.label}</i>
            ))}
          </div>
          <span />
        </div>
      )}
      {log && <p className="tlog">Logarithmic scale</p>}
    </div>
  );
}

export function Table({ b, ctx, n, predict = true, cited = null }: { b: Block; ctx: Ctx; n: number; predict?: boolean; cited?: ReactNode; [extra: string]: unknown }) {
  const [hc, setHc] = useState<number | null>(null);
  const [showChart, setShowChart] = useState(false);
  const [hl, setHl] = useState("");
  const [filter, setFilter] = useState("");
  const [forceChart, setForceChart] = useState(false);
  const [sort, setSort] = useState<Sort>(null);
  const model = b.an;
  const order = useMemo(() => sortedRows(model, sort), [model, sort]);
  const lastHead = model.headRows.length - 1;
  // asc → desc → as in the paper
  const flip = (col: number) => setSort((cur) => (!cur || cur.col !== col ? { col, dir: "asc" } : cur.dir === "asc" ? { col, dir: "desc" } : null));
  const chartable = model.numericCols.length > 0 && bars(model, model.numericCols[0]).length >= 3;
  const offline = process.env.NEXT_PUBLIC_RRM_OFFLINE === "1";
  const withChart = chartable && (!ctx.core || forceChart);
  useEffect(() => {
    if (!offline) return;
    if ((window as unknown as { __RRM_FORCE_CHART?: number }).__RRM_FORCE_CHART) setForceChart(true);
  }, [offline]);
  useEffect(() => {
    const f = (e: any) => { const d = e.detail; if (!d || d.id !== b.id) return; setHl(d.label || ""); };
    window.addEventListener("rrm-row", f);
    return () => window.removeEventListener("rrm-row", f);
  }, [b.id]);
  return (
    <figure className="table-fig" id={b.label || undefined} data-tab={b.id}>
      {withChart && <div className="tchart-bar"><button type="button" className="tchart-toggle press" aria-pressed={showChart} onClick={() => setShowChart((v) => !v)}>{showChart ? "Hide chart" : "Show as chart"}</button></div>}
      {ctx.core && <input className="table-filter" aria-label="Filter rows" value={filter} placeholder="Filter rows" onChange={(e) => setFilter(e.target.value)} />}
      {showChart && withChart && <TableChart model={model} n={n} predict={predict} tableId={b.id} />}
      <div className="table-wrap" onMouseLeave={() => setHc(null)}>
        <table data-hc={hc ?? undefined}>
          <thead>{model.headRows.map((hr: any[], ri: number) => (
            <tr key={ri}>{hr.map((c: any, ci: number) => {
              const on = hc !== null && hc >= c.col && hc < c.col + c.span;
              const sortable = ri === lastHead && c.span === 1 && model.bodyRows.length > 1;
              const dir = sort && sort.col === c.col ? sort.dir : null;
              const label = <Inlines inls={c.c} ctx={ctx} />;
              return (
                <th key={ci} colSpan={c.span} data-c={c.col} className={on ? "col-on" : ""} onMouseEnter={() => setHc(c.col)} aria-sort={sortable ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}>
                  {sortable
                    ? <button type="button" className={`th-sort${dir ? " is-on" : ""}`} onClick={() => flip(c.col)} aria-label={`Sort by ${plainOf(c.c) || `column ${c.col + 1}`}${dir === "asc" ? ", descending next" : dir === "desc" ? ", original order next" : ""}`}>{label}<span className="th-arrow" aria-hidden="true">{dir === "asc" ? "↑" : dir === "desc" ? "↓" : "↕"}</span></button>
                    : label}
                </th>
              );
            })}</tr>
          ))}</thead>
          <tbody>
            {order.filter((ri: number) => {
              const needle = filter.trim().toLowerCase();
              return !needle || model.bodyRows[ri].some((c: any) => plainOf(c.c).toLowerCase().includes(needle));
            }).map((ri: number) => {
              const r = model.bodyRows[ri];
              const label = rowLabel(r[0]);
              return (
                <tr key={ri} className={hl && label === hl ? "row-on" : ""} onMouseEnter={() => ping(b.id, label)} onMouseLeave={() => ping(b.id, "")}>
                  {r.map((c: any, ci: number) => {
                    const on = hc !== null && hc >= c.col && hc < c.col + c.span;
                    const props = { colSpan: c.span, "data-c": c.col, className: on ? "col-on" : "", onMouseEnter: () => setHc(c.col), "data-pop": `t|${b.id}|${ri}|${c.col}`, tabIndex: 0 };
                    const body = <Inlines inls={c.c} ctx={ctx} />;
                    return c.col === 0 ? <th key={ci} {...props} scope="row">{body}</th> : <td key={ci} {...props}>{body}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <figcaption><b>Table {n}.</b> <Inlines inls={b.caption} ctx={ctx} /></figcaption>
      {cited}
    </figure>
  );
}

export default Table;
