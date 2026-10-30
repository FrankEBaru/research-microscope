"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Block, Inline, Paper } from "@/lib/types";
import { Tex, Rich, Sym } from "@/lib/math";
import { ProvChip } from "./Bits";
import Instrument from "./Instrument";
import { bibtex } from "@/lib/bibtex.js";
import { eqTex, figureUrl, paperKey, refText } from "@/lib/backend.js";
import { createTracker } from "@/lib/companion.js";
import { analyze, bars } from "@/lib/tablechart.js";
import Companion, { Offer } from "./Companion";

/* ---------- utilidades ---------- */
const countNotes = (inls: Inline[]): number =>
  (inls || []).reduce((n, x) => n + (x.t === "note" ? 1 : Array.isArray(x.c) ? countNotes(x.c) : 0), 0);

export function plainOf(inls: Inline[]): string {
  return (inls || []).map((x) => x.t === "text" ? x.v : x.t === "math" ? `$${x.v}$` : x.t === "cite" ? "" : x.t === "note" ? "" : Array.isArray(x.c) ? plainOf(x.c) : x.v || "").join("").replace(/\s+/g, " ").trim();
}

interface Ctx { figs?: Set<string>; syms: Sym[]; refIndex: Record<string, number>; refLabels?: Record<string, string>; xref?: Record<string, string>; counter: { n: number } }

function Inlines({ inls, ctx }: { inls: Inline[]; ctx: Ctx }) {
  return <>{(inls || []).map((x, i) => <One key={i} x={x} ctx={ctx} />)}</>;
}

function One({ x, ctx }: { x: Inline; ctx: Ctx }) {
  switch (x.t) {
    case "text": return <>{x.v}</>;
    case "math": return <Tex tex={x.v} display={false} syms={ctx.syms} />;
    case "em": return <em><Inlines inls={x.c} ctx={ctx} /></em>;
    case "strong": return <strong><Inlines inls={x.c} ctx={ctx} /></strong>;
    case "span": return <Inlines inls={x.c} ctx={ctx} />;
    case "code": return <code>{x.v}</code>;
    case "link": {
      if (x.href.startsWith("#")) {
        const lab = x.href.slice(1), shown = ctx.xref?.[lab];
        const raw = plainOf(x.c);  // pandoc deja «[etiqueta]» cuando no resuelve la referencia
        return <a href={x.href} className="xref" data-xref={lab} {...(ctx.figs?.has(lab) ? { "data-pop": `f|${lab}`, tabIndex: 0 } : {})}>{shown && (raw === `[${lab}]` || raw === lab) ? shown : <Inlines inls={x.c} ctx={ctx} />}</a>;
      }
      return <a href={x.href} target="_blank" rel="noreferrer"><Inlines inls={x.c} ctx={ctx} /></a>;
    }
    case "cite": {
      const lab = x.keys.map((k: string) => ctx.refLabels?.[k] ?? ctx.refIndex[k] ?? "?");
      return <span className="cite" tabIndex={0} data-pop={`c|${x.keys.join(",")}`}>[{lab.join("; ")}]</span>;
    }
    case "note": {
      const n = ++ctx.counter.n;
      return <sup className="fn" tabIndex={0} data-pop={`n|${n}`}>{n}</sup>;
    }
    case "ref": {
      const label = x.label || "";
      const text = refText(x, ctx.xref);
      const href = x.target ? `#blk-${x.target}` : `#${label}`;
      return <a href={href} className="xref" data-xref={label}>{text}</a>;
    }
    default: return null;
  }
}

/* ---------- popover ---------- */
type PopState = { key: string; rect: DOMRect } | null;

function Popover({ pop, paper, model, content }: { pop: NonNullable<PopState>; paper: Paper; model: any; content: any }) {
  const [kind, ...r] = pop.key.split("|");
  const ctx: Ctx = { syms: model.syms, refIndex: model.refIndex, counter: { n: 0 } };
  let body: any = null;
  if (kind === "c") {
    body = r[0].split(",").map((k) => <p key={k} className="pop-ref"><b>[{paper.refLabels?.[k] ?? model.refIndex[k] ?? "?"}]</b> {paper.refs[k] || "referencia no encontrada en el paper"}</p>);
    body = <>{body}<div className="pop-meta"><ProvChip kind="paper" text="bibliografía del paper" /></div></>;
  } else if (kind === "y") {
    const s = content.attention.symbols.find((s: any) => s.id === r[0]);
    body = (
      <>
        <p className="pop-title"><Tex tex={s.latex} /> · {s.name}</p>
        <p className="pop-quote">Definido en el paper: «<Rich text={s.def.quote} />»</p>
        <div className="pop-meta"><ProvChip kind="curado" text="símbolo y color curados" /><span>clic: ir a la definición</span></div>
      </>
    );
  } else if (kind === "n") {
    const note = model.notes[+r[0] - 1];
    body = <><p className="pop-title">Nota al pie {r[0]}</p><p><Inlines inls={note.blocks.flatMap((b: Block) => b.inlines || [])} ctx={ctx} /></p><div className="pop-meta"><ProvChip kind="paper" /></div></>;
  } else if (kind === "s") {
    const b = model.byId[r[0]]; const s = b.sents[+r[1]];
    const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const symsIn = model.syms.filter((y: Sym) => s.some((x: Inline) => x.t === "math" && new RegExp(`(^|[^A-Za-z\\\\^_])${esc(y.latex)}`).test(x.v)));
    const cites = s.filter((x: Inline) => x.t === "cite").flatMap((x: Inline) => x.keys);
    body = (
      <>
        <p className="pop-title">§{model.secOf[b.id] || "—"} · oración {+r[1] + 1} de {b.sents.length}</p>
        {symsIn.length > 0 && <p className="pop-line">Símbolos: {symsIn.map((y: Sym) => <span key={y.id} className="sym-pill" style={{ color: y.color }}><Tex tex={y.latex} /></span>)}</p>}
        {cites.length > 0 && <p className="pop-line">Cita: {cites.slice(0, 2).map((k: string) => paper.refs[k]?.split(".")[0] + "…").join(" · ")}</p>}
        <div className="pop-sim"><ProvChip kind="simulado" /><span>Aquí el motor mostrará de qué otros papers sale esta oración y quién la apoya o la matiza. Todavía no está conectado.</span></div>
      </>
    );
  } else if (kind === "f") {
    const f = model.byLabel[r[0]];
    body = (
      <>
        <div className="pop-figs">{f.images.slice(0, 2).map((src: string) => <FigImg key={src} paper={paper} name={src} alt={plainOf(f.caption)} />)}</div>
        <p className="pop-line"><b>Figura {model.figN[f.id]}.</b> <Inlines inls={f.caption} ctx={ctx} /></p>
        <div className="pop-meta"><ProvChip kind="paper" text="figura original, sin redibujar" /><span>clic: ir a la figura</span></div>
      </>
    );
  } else if (kind === "t") {
    const t = model.byId[r[0]]; const an = t.an; const ri = +r[1], col = +r[2];
    const row = an.bodyRows[ri]; const cell = row.find((c: any) => c.col === col) || row[0];
    body = (
      <>
        <p className="pop-title">Tabla · fila «<Inlines inls={row[0].c} ctx={ctx} />»</p>
        <p className="pop-line">Columna «{an.headers[col] || "—"}»: <b><Inlines inls={cell.c} ctx={ctx} /></b></p>
        <div className="pop-sim"><ProvChip kind="simulado" /><span>Lectura simulada: el motor explicará qué mide esta celda y con qué texto del paper se relaciona.</span></div>
      </>
    );
  }
  const above = pop.rect.bottom > window.innerHeight * 0.6;
  const left = Math.min(Math.max(12, pop.rect.left), window.innerWidth - 372);
  const style: any = { left, ...(above ? { top: pop.rect.top - 8, transform: "translateY(-100%)" } : { top: pop.rect.bottom + 8 }) };
  return <div className="popover" style={style} role="tooltip">{body}</div>;
}

/* ---------- tabla (+ gráfica viva) ---------- */
function TableChart({ model, n }: { model: any; n: number }) {
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
      <div className="tpredict">
        <label className="chk"><input type="checkbox" checked={ask} onChange={(e) => setAsk(e.target.checked)} /> predecir antes de ver <ProvChip kind="hipotesis" text="hipótesis" /></label>
        {hide && <span role="status">¿Cuál crees que tiene el valor más alto en «{model.headers[col]}»? Haz clic en una fila.</span>}
        {ask && guess !== null && top && <span role="status" className="tp-result">{guess === top.label ? `Acertaste: ${top.label} (${top.raw}).` : `Elegiste ${guess}; el más alto es ${top.label} (${top.raw}).`}</span>}
      </div>
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

function Table({ b, ctx, n }: { b: Block; ctx: Ctx; n: number }) {
  const [hc, setHc] = useState<number | null>(null);
  const [showChart, setShowChart] = useState(false);
  const [hl, setHl] = useState("");
  const model = b.an;
  const chartable = model.numericCols.length > 0 && bars(model, model.numericCols[0]).length >= 3;
  useEffect(() => { const f = (e: any) => setHl(e.detail || ""); window.addEventListener("rrm-row", f); return () => window.removeEventListener("rrm-row", f); }, []);
  return (
    <figure className="table-fig" id={b.label || undefined} data-tab={b.id}>
      {chartable && <div className="tchart-bar"><button className="tchart-toggle" aria-pressed={showChart} onClick={() => setShowChart((v) => !v)}>{showChart ? "Ocultar gráfica" : "Ver como gráfica"}</button></div>}
      {showChart && <TableChart model={model} n={n} />}
      <div className="table-wrap" onMouseLeave={() => setHc(null)}>
        <table data-hc={hc ?? undefined}>
          <thead>{model.headRows.map((hr: any[], ri: number) => (
            <tr key={ri}>{hr.map((c: any, ci: number) => <th key={ci} colSpan={c.span} data-c={c.col} className={hc !== null && hc >= c.col && hc < c.col + c.span ? "col-on" : ""} onMouseEnter={() => setHc(c.col)}><Inlines inls={c.c} ctx={ctx} /></th>)}</tr>
          ))}</thead>
          <tbody>
            {model.bodyRows.map((r: any[], ri: number) => (
              <tr key={ri} className={hl && plainOf(r[0].c).replace(/\[cite\]/g, "").trim() === hl ? "row-on" : ""} style={{ animationDelay: `${ri * 35}ms` }}>
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

const FILE_NAME = /^[A-Za-z0-9._-]{1,180}$/;

/** Figura con zonas: cajas sobre la figura ORIGINAL (marcadas a mano) que enlazan cada parte con la frase del paper que la explica. */
function ZoneFig({ paper, name, alt, zones, onGo }: { paper: Paper; name: string; alt: string; zones: any[]; onGo: (blockId: string) => void }) {
  const [on, setOn] = useState<string | null>(null);
  const z = zones.find((x) => x.id === on);
  return (
    <div className="zonefig">
      <div className="zone-box" onMouseLeave={() => setOn(null)}>
        <FigImg paper={paper} name={name} alt={alt} />
        {zones.map((x) => (
          <button key={x.id} className={`zone ${on === x.id ? "on" : ""}`} data-zone={x.id} aria-label={x.label} onMouseEnter={() => setOn(x.id)} onFocus={() => setOn(x.id)} onClick={() => setOn(x.id)}
            style={{ left: `${x.box[0] * 100}%`, top: `${x.box[1] * 100}%`, width: `${(x.box[2] - x.box[0]) * 100}%`, height: `${(x.box[3] - x.box[1]) * 100}%` }} />
        ))}
      </div>
      <div className="zone-card" role="status" aria-live="polite">
        {z ? (<><b>{z.label}</b><blockquote>«{z.quote}»</blockquote><button className="link" onClick={() => onGo(z.anchor.blockId)}>ver dónde lo dice →</button></>)
          : <span className="muted">Pasa el cursor por una parte de la figura para ver qué dice el paper de ella.</span>}
      </div>
      <div className="chips"><ProvChip kind="curado" text="zonas marcadas a mano, sin modelo; la figura no se modifica" /></div>
    </div>
  );
}

function FigImg({ paper, name, alt }: { paper: Paper; name: string; alt: string }) {
  const [broken, setBroken] = useState(false);
  const bare = FILE_NAME.test(name) && !name.includes("..");
  if (paper.stage === "sections" || broken || (!name.startsWith("/") && !bare)) {
    return <div className="fig-loading">cargando figura</div>;
  }
  return <img src={figureUrl(paperKey(paper), name)} alt={alt} loading="lazy" onError={() => setBroken(true)} />;
}

function autoSentence(text: string) {
  const parts = String(text || "").split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
  return parts.find((s) => /we propose|we present|we show|we introduce/i.test(s)) || parts[0] || "";
}

export function mountKey(paper: Paper) {
  if (!paper.stage || paper.stage === "stub") return "stub";
  return paper.upgraded_from ? "body-up" : "body";
}

/* ---------- vista principal ---------- */
export default function PaperView({ paper, content, focus, companion, onHideCompanion, remote }: { paper: Paper; content: any; focus?: string; companion?: boolean; onHideCompanion?: () => void; remote?: { status?: string; stage?: string; reason?: string; source?: string } | null }) {
  const art = useRef<HTMLElement>(null);
  const [pop, setPop] = useState<PopState>(null);
  const timer = useRef<any>(null);
  const [active, setActive] = useState<string>("");
  const tracker = useRef(createTracker());
  const [offer, setOffer] = useState<Offer | null>(null);
  const [point, setPoint] = useState<string | null>(null); // bloque al que el compañero señala (se suelta solo)
  useEffect(() => { if (!point) return; const el = document.getElementById(point); el?.classList.remove("flash"); void el?.offsetWidth; el?.classList.add("flash"); const t = setTimeout(() => setPoint(null), 12000); return () => clearTimeout(t); }, [point]);
  useEffect(() => { if (companion && focus) setPoint(`blk-${focus}`); }, [focus, companion, paper.arxivId]);
  const [breakdown, setBreakdown] = useState<string | null>(null); // bloque `eq` cuyo desglose está abierto
  useEffect(() => { tracker.current.reset(); setOffer(null); }, [paper.arxivId, paper.stage, paper.upgraded_from, companion]);

  const att = content.attention?.paper === paper.arxivId ? content.attention : null;
  const model = useMemo(() => {
    const syms: Sym[] = att ? att.symbols : [];
    const refIndex: Record<string, number> = {};
    Object.keys(paper.refs || {}).forEach((k, i) => (refIndex[k] = i + 1));
    const byLabel: Record<string, any> = {}, figs = new Set<string>();
    const byId: Record<string, any> = {}, secOf: Record<string, string> = {}, nums: Record<string, string> = {};
    const notes: { blocks: Block[] }[] = [];
    const noteBase: Record<string, number> = {};
    const toc: { id: string; label: string; level: number }[] = [];
    let h = [0, 0, 0], cur = "", fig = 0, tab = 0, app = false;
    const xref: Record<string, string> = {}, target: Record<string, string> = {};
    const letter = (n: number) => String.fromCharCode(64 + n);
    const figN: Record<string, number> = {}, tabN: Record<string, number> = {};
    const walk = (inls: Inline[]) => (inls || []).forEach((x) => { if (x.t === "note") notes.push({ blocks: x.blocks }); else if (Array.isArray(x.c)) walk(x.c); });
    for (const b of paper.blocks) {
      byId[b.id] = b; noteBase[b.id] = notes.length;
      if (b.kind === "h" && b.unnumbered) {
        cur = ""; toc.push({ id: b.id, label: plainOf(b.inlines), level: 1 });
        if (/^(appendix|ap[ée]ndice)/i.test(plainOf(b.inlines))) { app = true; h = [0, 0, 0]; }
      }
      else if (b.kind === "h" && b.level <= 3) {
        if (b.number != null) cur = String(b.number);
        else {
          h[b.level - 1]++; for (let j = b.level; j < 3; j++) h[j] = 0;
          cur = h.slice(0, b.level).map((n, i) => (app && i === 0 ? letter(n) : n)).join(".");
        }
        nums[b.id] = cur;
        if (b.label) { xref[b.label] = `${app ? "Apéndice" : "Sección"} ${cur}`; target[b.label] = `sec-${b.id}`; }
        if (b.level <= 2) toc.push({ id: b.id, label: `${cur} ${plainOf(b.inlines)}`, level: b.level });
      }
      secOf[b.id] = cur;
      if (b.kind === "fig") { figN[b.id] = ++fig; if (b.label) { xref[b.label] = `Figura ${fig}`; byLabel[b.label] = b; figs.add(b.label); } }
      if (b.kind === "eq") {
        const tg = /\\tag\{([^}]*)\}/.exec(b.tex);
        (b.labels || []).forEach((l: string) => {
          if (b.number != null) xref[l] = String(l).startsWith("eq") ? `(${b.number})` : String(b.number);
          else xref[l] = tg ? `(${tg[1]})` : "ecuación";
          target[l] = `blk-${b.id}`;
        });
      }
      if (b.kind === "table") {
        b.an = analyze(b as any);
        tabN[b.id] = ++tab; if (b.label) xref[b.label] = `Tabla ${tab}`;
        const all: Inline[][][] = [...(b.head || []), ...(b.body || [])];
        // cabecera de varias líneas (p. ej. «Sequential» / «Operations»): se funden las filas casi vacías que siguen a la primera
        const hdr = all[0].map((c) => [...c]);
        let k = 1;
        while (k < all.length - 1 && plainOf(all[k][0]) === "" && all[k].filter((c) => plainOf(c) !== "").length <= 2 && !all[k].some((c) => /\d/.test(plainOf(c)))) {
          all[k].forEach((c, ci) => { if (plainOf(c)) hdr[ci] = [...hdr[ci], { t: "text", v: " " }, ...c]; });
          k++;
        }
        b.hdr = hdr; b.rows = [hdr, ...all.slice(k)];
      }
      walk(b.inlines);
    }
    return { syms, refIndex, byId, secOf, nums, notes, noteBase, toc, figN, tabN, xref, target, byLabel, figs };
  }, [paper, att]);

  // handlers
  const onOver = (e: React.MouseEvent | React.FocusEvent) => {
    const el = (e.target as HTMLElement).closest("[data-pop],[data-sym]") as HTMLElement | null;
    clearTimeout(timer.current);
    if (!el) return;
    const key = el.dataset.pop || `y|${el.dataset.sym}`;
    if (companion) signal(key);
    const show = () => setPop({ key, rect: el.getBoundingClientRect() });
    if (key.startsWith("s|")) timer.current = setTimeout(show, 380); else show();
  };
  // el compañero solo mira repeticiones de lo que el lector ya hace con el ratón; nada sale de esta pestaña
  const signal = (key: string) => {
    const [kind, a, b] = key.split("|");
    const sk = kind === "y" ? `sym:${a}` : kind === "f" ? `fig:${a}` : kind === "t" ? `row:${a}:${b}` : "";
    if (!sk) return;
    const hit = tracker.current.track(sk);
    if (!hit) return;
    if (kind === "y" && att) {
      const sy = att.symbols.find((q: any) => q.id === a);
      setOffer({ key: hit, text: `Llevas un rato con «${sy.name}». ¿Te llevo a donde el paper lo define?`, accept: "Sí, llévame", onAccept: () => goTo(sy.def.anchor.blockId) });
    } else if (kind === "f") {
      setOffer({ key: hit, text: `Has vuelto varias veces a la ${model.xref[a]}. ¿Te llevo a ella?`, accept: "Sí, llévame", onAccept: () => document.getElementById(a)?.scrollIntoView({ behavior: "smooth", block: "center" }) });
    } else if (kind === "t") {
      setOffer({ key: hit, text: "Estás recorriendo esta tabla. ¿Te llevo a su leyenda, que explica qué mide?", accept: "Sí, llévame", onAccept: () => document.querySelector(`[data-tab="${a}"] figcaption`)?.scrollIntoView({ behavior: "smooth", block: "center" }) });
    }
  };
  const touched = useRef(0); // con el dedo no hay «salir del elemento»: el popover se abre al tocar y se cierra al tocar fuera
  const onOut = () => { if (Date.now() - touched.current < 800) return; clearTimeout(timer.current); setPop(null); };
  useEffect(() => {
    const away = (e: TouchEvent) => { const t = e.target as HTMLElement; if (!t.closest?.("[data-pop],[data-sym],.popover")) setPop(null); };
    document.addEventListener("touchstart", away, { passive: true }); return () => document.removeEventListener("touchstart", away);
  }, []);
  const onClick = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    if (Date.now() - touched.current < 800 && !t.closest("[data-sym],[data-xref]")) { const el = t.closest("[data-pop]") as HTMLElement | null; if (el && !el.dataset.pop!.startsWith("s|")) setPop({ key: el.dataset.pop!, rect: el.getBoundingClientRect() }); }
    const sym = t.closest("[data-sym]") as HTMLElement | null;
    if (sym && att) { const s = att.symbols.find((y: any) => y.id === sym.dataset.sym); if (s) goTo(s.def.anchor.blockId); return; }
    const xr = t.closest("[data-xref]") as HTMLElement | null;
    if (xr) { e.preventDefault(); const el = document.getElementById(model.target[xr.dataset.xref!] || xr.dataset.xref!); el?.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    const cp = t.closest("[data-copy]") as HTMLElement | null;
    if (cp) { const old = cp.textContent; navigator.clipboard?.writeText(cp.dataset.copy!); cp.textContent = "copiado"; setTimeout(() => (cp.textContent = old), 1200); }
  };
  const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const symsInTex = (tex: string): Sym[] => (att ? att.symbols : []).filter((y: Sym) => new RegExp(`(^|[^A-Za-z\\\\^_])${esc(y.latex)}`).test(tex));
  // permanencia: una ecuación completa en pantalla y sin scroll durante DWELL ms -> una oferta (no interrumpe: la acepta o no el lector)
  useEffect(() => {
    if (!companion || !att) return;
    const DWELL = (window as any).__RRM_DWELL_MS || 15000;
    const vis = new Map<string, number>(); let current: string | null = null; let timer: any;
    const arm = () => {
      clearTimeout(timer); if (!current) return; const id = current;
      timer = setTimeout(() => {
        const b = model.byId[id.replace("blk-", "")]; if (!b || symsInTex(b.tex).length === 0) return;
        const hit = tracker.current.offer(`dwell:${id}`); if (!hit) return;
        setOffer({ key: hit, text: "Llevas un rato en esta ecuación. ¿Te desgloso sus símbolos con lo que dice el paper?", accept: "Sí, desglósala", onAccept: () => { setBreakdown(b.id); setPoint(`blk-${b.id}`); setTimeout(() => document.getElementById(`bd-${b.id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 80); } });
      }, DWELL);
    };
    const io = new IntersectionObserver((es) => {
      es.forEach((e) => vis.set(e.target.id, e.intersectionRatio));
      current = [...vis].filter(([, r]) => r >= 0.9).map(([k]) => k)[0] || null; arm();
    }, { threshold: [0, 0.5, 0.9, 1] });
    document.querySelectorAll<HTMLElement>(".eq.blk").forEach((e) => io.observe(e));
    window.addEventListener("scroll", arm, { passive: true });
    return () => { clearTimeout(timer); io.disconnect(); window.removeEventListener("scroll", arm); };
  }, [companion, paper.arxivId, att]);
  const goTo = (id: string) => {
    const el = document.getElementById("blk-" + id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  };
  useEffect(() => { if (focus) setTimeout(() => goTo(focus), 250); }, [focus, paper.arxivId]);
  useEffect(() => {
    const hs = Array.from(document.querySelectorAll<HTMLElement>("[data-toc]"));
    const io = new IntersectionObserver((es) => { es.forEach((e) => e.isIntersecting && setActive(e.target.id)); }, { rootMargin: "-10% 0px -80% 0px" });
    hs.forEach((h) => io.observe(h));
    return () => io.disconnect();
  }, [paper]);

  const instAfter = att?.instrument.claim.anchor.blockId;
  const authors = paper.authors.length > 4 ? `${paper.authors.slice(0, 3).join(", ")} y ${paper.authors.length - 3} más` : paper.authors.join(", ");

  return (
    <div className="paper-layout">
      {model.toc.length > 0 && (
        <nav className="toc" aria-label="Secciones">
          {model.toc.map((t) => (
            <a key={t.id} href={`#sec-${t.id}`} className={`toc-${t.level} ${active === `sec-${t.id}` ? "on" : ""}`}
              onClick={(e) => { e.preventDefault(); document.getElementById(`sec-${t.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>{t.label}</a>
          ))}
        </nav>
      )}
      <article key={mountKey(paper)} ref={art} className="paper" onTouchStart={() => (touched.current = Date.now())} onMouseOver={onOver} onMouseOut={onOut} onFocus={onOver} onBlur={onOut} onClick={onClick}>
        <header className="paper-head">
          <div className="chips">
            <ProvChip kind="paper" text={paper.arxivId ? `arXiv:${paper.arxivId}` : `corpus:${paper.corpusid ?? ""}`} />
            {!paper.full && !remote && <ProvChip kind="curado" text="solo abstract en esta ráfaga" />}
            {remote?.stage === "stub" && <span className="chip chip-curado">solo abstract · cargando texto completo…</span>}
            {(remote?.status === "abstract_only" || remote?.stage === "abstract_only") && <span className="chip chip-curado">solo abstract: sin LaTeX ni PDF usable</span>}
          </div>
          <h1>{paper.title}</h1>
          <p className="authors">{authors}</p>
          <p className="meta">{paper.date?.slice(0, 4)}{paper.arxivId && <> · <a href={`https://arxiv.org/abs/${paper.arxivId}`} target="_blank" rel="noreferrer">ver original en arXiv</a></>}{paper.full && paper.arxivId && <> · <a href={`https://arxiv.org/pdf/${paper.arxivId}`} target="_blank" rel="noreferrer">PDF</a></>}{(remote?.status === "abstract_only" || remote?.status === "failed" || remote?.stage === "abstract_only") && !paper.arxivId && paper.corpusid != null && <> · <a href={`https://www.semanticscholar.org/paper/${paper.corpusid}`} target="_blank" rel="noreferrer">Semantic Scholar</a></>}{paper.arxivId && <> · <button className="link bib" data-bibtex={bibtex(paper)} data-copy={bibtex(paper)} title="Copiar la ficha BibTeX de arXiv">BibTeX</button></>}</p>
          {remote?.status === "failed" && <p className="fail-reason">{remote.reason}</p>}
          {remote?.source === "ocr" && <p className="ocr-band">leído por OCR: puede haber errores en ecuaciones</p>}
          {remote && autoSentence(paper.abstract) && <blockquote><span className="qlab">frase del abstract (automática)</span>«{autoSentence(paper.abstract)}»</blockquote>}
          {paper.license && <p className="license">{paper.license}</p>}
          {paper.authorNotes?.length > 0 && (
            <details className="author-notes"><summary>Notas de autoría del paper</summary>{paper.authorNotes.map((n: string, i: number) => <p key={i}>{n}</p>)}</details>
          )}
        </header>

        {paper.blocks.map((b) => {
          const ctx: Ctx = { syms: model.syms, refIndex: model.refIndex, refLabels: paper.refLabels, xref: model.xref, figs: model.figs, counter: { n: model.noteBase[b.id] } };
          let el: any = null;
          if (b.kind === "h") {
            const Tag: any = b.level === 1 ? "h2" : b.level === 2 ? "h3" : "h4";
            const num = model.nums[b.id];
            el = <Tag id={`sec-${b.id}`} data-toc className={`h-${b.level}`}>{num && <span className="num">{num}</span>}<Inlines inls={b.inlines} ctx={ctx} /></Tag>;
          } else if (b.kind === "p") {
            const nb = countNotes(b.inlines);
            el = (
              <div id={`blk-${b.id}`} className={`blk ${b.abs ? "abstract" : ""} ${b.raw ? "raw" : ""}`}>
                {b.abs && <div className="abs-label">Resumen</div>}
                <p>{(b.sents || [b.inlines]).map((s: Inline[], i: number) => <span key={i} className="sent" data-pop={`s|${b.id}|${i}`}><Inlines inls={s} ctx={ctx} /></span>)}</p>
                {b.abs && remote && paper.tldr && <p className="tldr"><span className="chip chip-simulado">TLDR de Semantic Scholar (modelo)</span> {paper.tldr}</p>}
                {nb > 0 && <ol className="notes" start={model.noteBase[b.id] + 1}>{model.notes.slice(model.noteBase[b.id], model.noteBase[b.id] + nb).map((n, i) => <li key={i} value={model.noteBase[b.id] + i + 1}><Inlines inls={n.blocks.flatMap((x: Block) => x.inlines || [])} ctx={{ ...ctx, counter: { n: 999 } }} /></li>)}</ol>}
              </div>
            );
          } else if (b.kind === "eq") {
            el = (
              <div id={`blk-${b.id}`} className="eq blk">
                <Tex tex={eqTex(b)} display syms={model.syms} />
                {b.katex_ok === false && <span className="math-hint">no se pudo dibujar; TeX original</span>}
                <button className="copy" data-copy={b.tex} aria-label="Copiar LaTeX">LaTeX</button>
              </div>
            );
          } else if (b.kind === "list") {
            el = <ul id={`blk-${b.id}`} className="blk list">{b.items.map((it: Inline[], i: number) => <li key={i}><Inlines inls={it} ctx={ctx} /></li>)}</ul>;
          } else if (b.kind === "fig") {
            el = (
              <figure id={b.label || `blk-${b.id}`} className="fig blk">
                <div className="fig-imgs">{b.images.map((src: string, i: number) => { const zs = i === 0 && b.label ? (content.zones?.figures || []).find((f: any) => f.paper === paper.arxivId && f.fig === b.label)?.zones : null;
                  return zs ? <ZoneFig key={src} paper={paper} name={src} alt={plainOf(b.caption)} zones={zs} onGo={goTo} /> : <FigImg key={src} paper={paper} name={src} alt={plainOf(b.caption)} />; })}</div>
                <figcaption><b>Figura {model.figN[b.id]}.</b> <Inlines inls={b.caption} ctx={ctx} /> <ProvChip kind="paper" text="figura original, sin redibujar" /></figcaption>
              </figure>
            );
          } else if (b.kind === "table") {
            el = <Table b={b} ctx={ctx} n={model.tabN[b.id]} />;
          }
          return (
            <div key={b.id} className="row">
              {el}
              {breakdown === b.id && b.kind === "eq" && (
                <aside id={`bd-${b.id}`} className="breakdown" aria-label="Desglose de la ecuación">
                  <div className="chips"><ProvChip kind="curado" text="desglose curado: símbolos y definiciones del paper, no texto generado" /></div>
                  <ul>{symsInTex(b.tex).map((y: Sym) => (
                    <li key={y.id}><span className="sym-pill" style={{ color: y.color }}><Tex tex={y.latex} /></span> <b>{y.name}</b> · <em>«<Rich text={att.symbols.find((q: any) => q.id === y.id).def.quote} />»</em> <button className="link" onClick={() => goTo(att.symbols.find((q: any) => q.id === y.id).def.anchor.blockId)}>ver dónde se define</button></li>
                  ))}</ul>
                  {/sqrt\{d_k\}/.test(b.tex) && <p className="small">Esta ecuación divide por √d_k: <button className="link" onClick={() => document.querySelector(".instrument")?.scrollIntoView({ behavior: "smooth", block: "start" })}>ábrelo en el instrumento</button> y compruébalo.</p>}
                  <button className="link" onClick={() => setBreakdown(null)}>cerrar</button>
                </aside>
              )}
              {att && b.id === instAfter && <Instrument content={att} goTo={goTo} />}
            </div>
          );
        })}
        <footer className="paper-foot">
          <p>Texto, ecuaciones, figuras y tablas son los del e-print de arXiv:{paper.arxivId}, convertidos desde LaTeX sin resumir ni parafrasear. Lo que no es del paper lleva una etiqueta de procedencia.</p>
        </footer>
      </article>
      {pop && <Popover pop={pop} paper={paper} model={model} content={content} />}
      {companion && <Companion offer={offer} target={point} onAnswer={() => setOffer(null)} onHide={() => onHideCompanion?.()} />}
    </div>
  );
}
