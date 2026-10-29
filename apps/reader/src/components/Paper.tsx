"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Block, Inline, Paper } from "@/lib/types";
import { Tex, Rich, Sym } from "@/lib/math";
import { ProvChip } from "./Bits";
import Instrument from "./Instrument";
import { bibtex } from "@/lib/bibtex.js";

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
        <div className="pop-figs">{f.images.slice(0, 2).map((src: string) => <img key={src} src={src} alt={plainOf(f.caption)} />)}</div>
        <p className="pop-line"><b>Figura {model.figN[f.id]}.</b> <Inlines inls={f.caption} ctx={ctx} /></p>
        <div className="pop-meta"><ProvChip kind="paper" text="figura original, sin redibujar" /><span>clic: ir a la figura</span></div>
      </>
    );
  } else if (kind === "t") {
    const t = model.byId[r[0]]; const ri = +r[1], ci = +r[2];
    const rows = t.rows; const head = t.hdr; const cell = rows[ri][ci];
    body = (
      <>
        <p className="pop-title">Tabla · fila «<Inlines inls={rows[ri][0]} ctx={ctx} />»</p>
        <p className="pop-line">Columna «<Inlines inls={head[ci] || []} ctx={ctx} />»: <b><Inlines inls={cell} ctx={ctx} /></b></p>
        <div className="pop-sim"><ProvChip kind="simulado" /><span>Lectura simulada: el motor explicará qué mide esta celda y con qué texto del paper se relaciona.</span></div>
      </>
    );
  }
  const above = pop.rect.bottom > window.innerHeight * 0.6;
  const left = Math.min(Math.max(12, pop.rect.left), window.innerWidth - 372);
  const style: any = { left, ...(above ? { top: pop.rect.top - 8, transform: "translateY(-100%)" } : { top: pop.rect.bottom + 8 }) };
  return <div className="popover" style={style} role="tooltip">{body}</div>;
}

/* ---------- tabla ---------- */
function Table({ b, ctx, n }: { b: Block; ctx: Ctx; n: number }) {
  const [hc, setHc] = useState<number | null>(null);
  const rows: Inline[][][] = b.rows;
  const headRow = b.hdr;
  return (
    <figure className="table-fig" id={b.label || undefined}>
      <div className="table-wrap" onMouseLeave={() => setHc(null)}>
        <table data-hc={hc ?? undefined}>
          <thead><tr>{headRow.map((c, ci) => <th key={ci} data-c={ci} className={hc === ci ? "col-on" : ""} onMouseEnter={() => setHc(ci)}><Inlines inls={c} ctx={ctx} /></th>)}</tr></thead>
          <tbody>
            {rows.slice(1).map((r, ri) => (
              <tr key={ri} style={{ animationDelay: `${ri * 35}ms` }}>
                {r.map((c, ci) => <td key={ci} data-c={ci} className={hc === ci ? "col-on" : ""} onMouseEnter={() => setHc(ci)} data-pop={`t|${b.id}|${ri + 1}|${ci}`} tabIndex={0}><Inlines inls={c} ctx={ctx} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption><b>Tabla {n}.</b> <Inlines inls={b.caption} ctx={ctx} /></figcaption>
    </figure>
  );
}

/* ---------- vista principal ---------- */
export default function PaperView({ paper, content, focus }: { paper: Paper; content: any; focus?: string }) {
  const art = useRef<HTMLElement>(null);
  const [pop, setPop] = useState<PopState>(null);
  const timer = useRef<any>(null);
  const [active, setActive] = useState<string>("");

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
        h[b.level - 1]++; for (let j = b.level; j < 3; j++) h[j] = 0;
        cur = h.slice(0, b.level).map((n, i) => (app && i === 0 ? letter(n) : n)).join("."); nums[b.id] = cur;
        if (b.label) { xref[b.label] = `${app ? "Apéndice" : "Sección"} ${cur}`; target[b.label] = `sec-${b.id}`; }
        if (b.level <= 2) toc.push({ id: b.id, label: `${cur} ${plainOf(b.inlines)}`, level: b.level });
      }
      secOf[b.id] = cur;
      if (b.kind === "fig") { figN[b.id] = ++fig; if (b.label) { xref[b.label] = `Figura ${fig}`; byLabel[b.label] = b; figs.add(b.label); } }
      if (b.kind === "eq") { const tg = /\\tag\{([^}]*)\}/.exec(b.tex); (b.labels || []).forEach((l: string) => { xref[l] = tg ? `(${tg[1]})` : "ecuación"; target[l] = `blk-${b.id}`; }); }
      if (b.kind === "table") {
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
    const show = () => setPop({ key, rect: el.getBoundingClientRect() });
    if (key.startsWith("s|")) timer.current = setTimeout(show, 380); else show();
  };
  const onOut = () => { clearTimeout(timer.current); setPop(null); };
  const onClick = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement;
    const sym = t.closest("[data-sym]") as HTMLElement | null;
    if (sym && att) { const s = att.symbols.find((y: any) => y.id === sym.dataset.sym); if (s) goTo(s.def.anchor.blockId); return; }
    const xr = t.closest("[data-xref]") as HTMLElement | null;
    if (xr) { e.preventDefault(); const el = document.getElementById(model.target[xr.dataset.xref!] || xr.dataset.xref!); el?.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    const cp = t.closest("[data-copy]") as HTMLElement | null;
    if (cp) { const old = cp.textContent; navigator.clipboard?.writeText(cp.dataset.copy!); cp.textContent = "copiado"; setTimeout(() => (cp.textContent = old), 1200); }
  };
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
      <article ref={art} className="paper" onMouseOver={onOver} onMouseOut={onOut} onFocus={onOver} onBlur={onOut} onClick={onClick}>
        <header className="paper-head">
          <div className="chips"><ProvChip kind="paper" text={`arXiv:${paper.arxivId}`} />{!paper.full && <ProvChip kind="curado" text="solo abstract en esta ráfaga" />}</div>
          <h1>{paper.title}</h1>
          <p className="authors">{authors}</p>
          <p className="meta">{paper.date?.slice(0, 4)} · <a href={`https://arxiv.org/abs/${paper.arxivId}`} target="_blank" rel="noreferrer">ver original en arXiv</a>{paper.full && <> · <a href={`https://arxiv.org/pdf/${paper.arxivId}`} target="_blank" rel="noreferrer">PDF</a></>} · <button className="link bib" data-bibtex={bibtex(paper)} data-copy={bibtex(paper)} title="Copiar la ficha BibTeX de arXiv">BibTeX</button></p>
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
              <div id={`blk-${b.id}`} className={`blk ${b.abs ? "abstract" : ""}`}>
                {b.abs && <div className="abs-label">Resumen</div>}
                <p>{(b.sents || [b.inlines]).map((s: Inline[], i: number) => <span key={i} className="sent" data-pop={`s|${b.id}|${i}`}><Inlines inls={s} ctx={ctx} /></span>)}</p>
                {nb > 0 && <ol className="notes" start={model.noteBase[b.id] + 1}>{model.notes.slice(model.noteBase[b.id], model.noteBase[b.id] + nb).map((n, i) => <li key={i} value={model.noteBase[b.id] + i + 1}><Inlines inls={n.blocks.flatMap((x: Block) => x.inlines || [])} ctx={{ ...ctx, counter: { n: 999 } }} /></li>)}</ol>}
              </div>
            );
          } else if (b.kind === "eq") {
            el = (
              <div id={`blk-${b.id}`} className="eq blk">
                <Tex tex={b.tex} display syms={model.syms} />
                <button className="copy" data-copy={b.tex} aria-label="Copiar LaTeX">LaTeX</button>
              </div>
            );
          } else if (b.kind === "list") {
            el = <ul id={`blk-${b.id}`} className="blk list">{b.items.map((it: Inline[], i: number) => <li key={i}><Inlines inls={it} ctx={ctx} /></li>)}</ul>;
          } else if (b.kind === "fig") {
            el = (
              <figure id={b.label || `blk-${b.id}`} className="fig blk">
                <div className="fig-imgs">{b.images.map((src: string) => <img key={src} src={src} alt={plainOf(b.caption)} loading="lazy" />)}</div>
                <figcaption><b>Figura {model.figN[b.id]}.</b> <Inlines inls={b.caption} ctx={ctx} /> <ProvChip kind="paper" text="figura original, sin redibujar" /></figcaption>
              </figure>
            );
          } else if (b.kind === "table") {
            el = <Table b={b} ctx={ctx} n={model.tabN[b.id]} />;
          }
          return (
            <div key={b.id} className="row">
              {el}
              {att && b.id === instAfter && <Instrument content={att} goTo={goTo} />}
            </div>
          );
        })}
        <footer className="paper-foot">
          <p>Texto, ecuaciones, figuras y tablas son los del e-print de arXiv:{paper.arxivId}, convertidos desde LaTeX sin resumir ni parafrasear. Lo que no es del paper lleva una etiqueta de procedencia.</p>
        </footer>
      </article>
      {pop && <Popover pop={pop} paper={paper} model={model} content={content} />}
    </div>
  );
}
