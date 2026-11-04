"use client";
import { Block, Inline, Paper } from "@/lib/types";
import { Tex, Rich, Sym } from "@/lib/math";
import { ProvChip } from "../Bits";
import { Cap, Prov } from "@/components/ui";
import { UNDEFINED, equationHover, symbolHover, tableHover } from "@/lib/hover.js";
import { briefRef } from "@/lib/cite.js";
import { resolveCite } from "@/lib/path.js";
import { Inlines } from "../Paper";
import { Ctx, plainOf } from "./inline";
import { GapView, repeatsBlock } from "./GapNotes";
import { FigImg } from "./Figures";

export type PopState = { key: string; rect: DOMRect } | null;

export default function Popover({ pop, paper, model, content, core, pack, titleOf, onOpen }: { pop: NonNullable<PopState>; paper: Paper; model: any; content: any; core?: boolean; pack?: any; titleOf?: (id: string) => string; onOpen?: (id: string, why: string) => void }) {
  const [kind, ...r] = pop.key.split("|");
  const ctx: Ctx = { syms: model.syms, refIndex: model.refIndex, counter: { n: 0 } };
  let body: any = null;
  if (kind === "c") {
    const keys = r[0].split(",");
    const openId = keys.map((k) => resolveCite(k, paper.citeMap)).find(Boolean) || "";
    body = (
      <>
        {keys.map((k) => {
          const brief = briefRef(paper.refs[k] || "");
          const n = paper.refLabels?.[k] ?? model.refIndex[k] ?? k;
          return (
            <p key={k} className="pop-ref">
              {brief.who ? <b className="pop-who">{brief.who}</b> : <b className="pop-who">{`Reference ${n}`}</b>}
              {brief.title ? <span>{brief.title}</span> : <span>title not found in the reference</span>}
            </p>
          );
        })}
        <div className="pop-f">
          <Prov kind="paper" text="from the paper’s references" />
          {openId && onOpen && <button type="button" className="pop-go press" onClick={() => onOpen(openId, "cita en el paper")}>Open →</button>}
        </div>
      </>
    );
  } else if (kind === "m" && core) {
    let tex = r[2] || "";
    try { tex = decodeURIComponent(tex); } catch { /* el LaTeX se muestra igual */ }
    const hit = symbolHover(paper.blocks, tex, { block: r[0], index: Number(r[1]) });
    if (!hit.here && hit.text !== UNDEFINED) {
      body = <><p className="pop-quote"><Rich text={hit.shown || hit.text} /></p><div className="pop-meta"><Prov kind="paper" text="author’s sentence" /></div></>;
    }
  } else if (kind === "e" && core) {
    const card = (pack?.notes || []).find((n: any) => n.block_id === r[0]);
    const art = (pack?.artifacts || []).find((n: any) => n.block_id === r[0]);
    if (card || art) {
      body = <GapView note={card} art={art} host={plainOf((paper.blocks || []).find((b) => b.id === r[0])?.inlines || [])} self={String(paper.corpusid ?? "")} titleOf={titleOf} onOpen={onOpen} />;
    } else {
    const hit = equationHover(paper.blocks, r[0]);
    const lines = hit.shown?.length ? hit.shown : hit.texts;
    body = <><p className="pop-title">Where it comes from</p>{lines.map((text: string, i: number) => <p key={i} className="pop-quote"><Rich text={text} /></p>)}{!lines.length && <p className="pop-quote">the paper does not define it</p>}<div className="pop-meta"><ProvChip kind="paper" text="author’s sentence" /></div></>;
    }
  } else if (kind === "s" && core && pack) {
    const host = (paper.blocks || []).find((b) => b.id === r[0]);
    const card = (pack.notes || []).find((n: any) => n.block_id === r[0] && n.sent_index === +r[1] && !(host && repeatsBlock(n, host)));
    if (card) body = <GapView note={card} host={plainOf((paper.blocks || []).find((b) => b.id === r[0])?.inlines || [])} self={String(paper.corpusid ?? "")} titleOf={titleOf} onOpen={onOpen} />;
  } else if (kind === "y") {
    const s = content.attention.symbols.find((s: any) => s.id === r[0]);
    body = (
      <>
        <p className="pop-title"><Tex tex={s.latex} /> · {s.name}</p>
        <p className="pop-quote">Defined in the paper: «<Rich text={s.def.quote} />»</p>
        <div className="pop-meta"><ProvChip kind="curado" text="curated symbol and color" /><span>click: go to the definition</span></div>
      </>
    );
  } else if (kind === "n") {
    const note = model.notes[+r[0] - 1];
    const bits = (note?.blocks || []).flatMap((b: Block) => b.inlines || []);
    body = <><Cap>{`Note ${r[0]}`}</Cap><p>{bits.length ? <Inlines inls={bits} ctx={ctx} /> : "Note not found in the paper."}</p><div className="pop-meta"><Prov kind="paper" text="paper" /></div></>;
  } else if (kind === "s") {
    const b = model.byId[r[0]]; const s = b.sents[+r[1]];
    const esc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const symsIn = model.syms.filter((y: Sym) => s.some((x: Inline) => x.t === "math" && new RegExp(`(^|[^A-Za-z\\\\^_])${esc(y.latex)}`).test(x.v)));
    const cites = s.filter((x: Inline) => x.t === "cite").flatMap((x: Inline) => x.keys);
    body = (
      <>
        <p className="pop-title">§{model.secOf[b.id] || "—"} · sentence {+r[1] + 1} of {b.sents.length}</p>
        {symsIn.length > 0 && <p className="pop-line">Symbols: {symsIn.map((y: Sym) => <span key={y.id} className="sym-pill" style={{ color: y.color }}><Tex tex={y.latex} /></span>)}</p>}
        {cites.length > 0 && <p className="pop-line">Citation: {cites.slice(0, 2).map((k: string) => paper.refs[k]?.split(".")[0] + "…").join(" · ")}</p>}
        <div className="pop-sim"><ProvChip kind="simulado" /><span>The engine will show which other papers this sentence comes from, and who supports or qualifies it. Not connected yet.</span></div>
      </>
    );
  } else if (kind === "f") {
    const f = model.byLabel[r[0]];
    body = (
      <>
        <div className="pop-figs">{f.images.slice(0, 2).map((src: string) => <FigImg key={src} paper={paper} name={src} alt={plainOf(f.caption)} />)}</div>
        <p className="pop-line"><b>Figure {model.figN[f.id]}.</b> <Inlines inls={f.caption} ctx={ctx} /></p>
        <div className="pop-meta"><Prov kind="paper" text="original figure" /><span>click: go to the figure</span></div>
      </>
    );
  } else if (kind === "t") {
    const t = model.byId[r[0]]; const an = t.an; const ri = +r[1], col = +r[2];
    const row = an.bodyRows[ri]; const cell = row.find((c: any) => c.col === col) || row[0];
    const told = core ? tableHover(paper.blocks, r[0]) : null;
    const tableNo = model.tabN?.[r[0]];
    body = core ? (
      <>
        <p className="pop-title">{tableNo ? `Table ${tableNo}` : "Table"}</p>
        {(told.captionShown || told.caption) && <p className="pop-quote"><Rich text={told.captionShown || told.caption} /></p>}
        {told.sentenceShown || told.sentence ? <p className="pop-quote"><Rich text={told.sentenceShown || told.sentence} /></p> : <p className="pop-line">The paper does not discuss it in a sentence.</p>}
        <div className="pop-meta"><Prov kind="paper" text="caption and author’s sentence" /></div>
      </>
    ) : (
      <>
        <p className="pop-title">Table · row «<Inlines inls={row[0].c} ctx={ctx} />»</p>
        <p className="pop-line">Column «{an.headers[col] || "—"}»: <b><Inlines inls={cell.c} ctx={ctx} /></b></p>
        <div className="pop-sim"><ProvChip kind="simulado" /><span>Simulated reading: the engine will explain what this cell measures and which sentence in the paper it relates to.</span></div>
      </>
    );
  }
  if (!body) return null;
  const narrow = typeof window !== "undefined" && window.innerWidth <= 760;
  let style: any;
  if (narrow) {
    style = { left: 12, right: 12, bottom: 12, top: "auto", width: "auto", transform: "none", maxHeight: "46vh", overflow: "auto" };
  } else if (kind === "t") {
    const host = typeof document !== "undefined" ? document.querySelector(`[data-tab="${r[0]}"]`) : null;
    const box = host?.getBoundingClientRect();
    const width = 320;
    if (box) {
      const left = Math.max(12, Math.min(box.left, window.innerWidth - width - 12));
      const below = box.bottom + 8;
      const placeAbove = below + 150 > window.innerHeight && box.top > 180;
      style = placeAbove
        ? { left, top: Math.max(12, box.top - 8), transform: "translateY(-100%)", width, maxHeight: "40vh", overflow: "auto" }
        : { left, top: Math.max(12, below), width, maxHeight: "40vh", overflow: "auto" };
    } else {
      style = { left: 12, top: 12, width };
    }
  } else {
    const above = pop.rect.bottom > window.innerHeight * 0.6;
    const left = Math.min(Math.max(12, pop.rect.left), window.innerWidth - 372);
    style = { left, width: 360, ...(above ? { top: pop.rect.top - 8, transform: "translateY(-100%)" } : { top: pop.rect.bottom + 8 }) };
  }
  return <div className="popover pop" style={style} role="tooltip">{body}</div>;
}
