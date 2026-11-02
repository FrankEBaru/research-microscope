"use client";
import { Block, Inline, Paper } from "@/lib/types";
import { Tex, Rich, Sym } from "@/lib/math";
import { ProvChip } from "../Bits";
import { equationHover, symbolHover, tableHover } from "@/lib/hover.js";
import { Inlines } from "../Paper";
import { Ctx, plainOf } from "./inline";
import { GapView } from "./GapNotes";
import { FigImg } from "./Figures";

export type PopState = { key: string; rect: DOMRect } | null;

export default function Popover({ pop, paper, model, content, core, pack, onOpen }: { pop: NonNullable<PopState>; paper: Paper; model: any; content: any; core?: boolean; pack?: any; onOpen?: (id: string, why: string) => void }) {
  const [kind, ...r] = pop.key.split("|");
  const ctx: Ctx = { syms: model.syms, refIndex: model.refIndex, counter: { n: 0 } };
  let body: any = null;
  if (kind === "c") {
    body = r[0].split(",").map((k) => <p key={k} className="pop-ref"><b>[{paper.refLabels?.[k] ?? model.refIndex[k] ?? "?"}]</b> {paper.refs[k] || "referencia no encontrada en el paper"}</p>);
    body = <>{body}<div className="pop-meta"><ProvChip kind="paper" text="bibliografía del paper" /></div></>;
  } else if (kind === "m" && core) {
    let tex = r[2] || "";
    try { tex = decodeURIComponent(tex); } catch { /* el LaTeX se muestra igual */ }
    const hit = symbolHover(paper.blocks, tex, { block: r[0], index: Number(r[1]) });
    body = <><p className="pop-quote">{hit.text}</p><div className="pop-meta"><ProvChip kind="paper" text="frase del autor" /></div></>;
  } else if (kind === "e" && core) {
    const card = (pack?.notes || []).find((n: any) => n.block_id === r[0]);
    const art = (pack?.artifacts || []).find((n: any) => n.block_id === r[0]);
    if (card || art) {
      body = <GapView note={card} art={art} self={String(paper.corpusid ?? "")} onOpen={onOpen} />;
    } else {
    const hit = equationHover(paper.blocks, r[0]);
    body = <><p className="pop-title">De dónde sale</p>{hit.texts.map((text: string, i: number) => <p key={i} className="pop-quote">{text}</p>)}{!hit.texts.length && <p className="pop-quote">el paper no lo define</p>}<div className="pop-meta"><ProvChip kind="paper" text="frase del autor" /></div></>;
    }
  } else if (kind === "s" && core && pack) {
    const card = (pack.notes || []).find((n: any) => n.block_id === r[0] && n.sent_index === +r[1]);
    if (card) body = <GapView note={card} self={String(paper.corpusid ?? "")} onOpen={onOpen} />;
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
    const told = core ? tableHover(paper.blocks, r[0]) : null;
    body = core ? (
      <>
        <p className="pop-title">Tabla</p>
        {told.caption && <p className="pop-quote">{told.caption}</p>}
        {told.sentence ? <p className="pop-quote">{told.sentence}</p> : <p className="pop-line">El paper no la discute en una frase.</p>}
        <div className="pop-meta"><ProvChip kind="paper" text="pie y frase del autor" /></div>
      </>
    ) : (
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
