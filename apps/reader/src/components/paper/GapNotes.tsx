"use client";
import { useState } from "react";
import { Tex, Rich } from "@/lib/math";
import { compareOf, matrixOf } from "@/lib/artifacts.js";
import { Prov } from "@/components/ui";
import { plainOf } from "./inline";

export function drawnOf(art: any) {
  if (!art) return null;
  if (art.kind === "pasos" || art.kind === "casos") return art;
  const drawn = art.type === "matriz"
    ? (matrixOf(art.tex) || art.grid || null)
    : art.type === "con_sin"
      ? (art.preferScale ? art.scale : (compareOf(art.tex) || art.scale || null))
      : null;
  return drawn ? { ...drawn, tag: art.tag || drawn.tag, why: art.why_look || "", quote: art.quote || drawn.quote || "" } : null;
}

export function MathBit({ text }: { text: string }) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  if (/\\|_|\^/.test(raw)) return <Tex tex={raw} />;
  return <>{raw}</>;
}

export function Stepper({ drawn }: { drawn: any }) {
  const [i, setI] = useState(0);
  const n = drawn.steps.length;
  const cur = Math.min(i, Math.max(0, n - 1));
  return (
    <div className="gap-art" data-artifact="pasos">
      <p className="gap-tag">illustrative</p>
      {drawn.title && <p>{drawn.title}</p>}
      {drawn.inputs?.length > 0 && <p className="gap-src">{drawn.inputs.map((line: string, k: number) => <span key={k}>{k ? " · " : ""}<Rich text={line} /></span>)}</p>}
      <ol className="step-list">{drawn.steps.map((line: string, k: number) => (
        <li key={k} className={k === cur ? "on" : ""}><Rich text={line} /></li>
      ))}</ol>
      <p className="gap-src">
        <button type="button" className="link" onClick={() => setI((v) => Math.max(0, v - 1))}>Previous</button>
        {" "}step {cur + 1}/{n}{" "}
        <button type="button" className="link" onClick={() => setI((v) => Math.min(n - 1, v + 1))}>Next</button>
      </p>
    </div>
  );
}

export function ArtifactView({ drawn }: { drawn: any }) {
  if (drawn.kind === "pasos") return <Stepper drawn={drawn} />;
  if (drawn.kind === "casos") {
    return (
      <div className="gap-art" data-artifact="casos">
        <p className="gap-tag">branches from the paper</p>
        <ul className="case-list">{drawn.branches.map((row: any, i: number) => (
          <li key={i} className="case-row"><span><MathBit text={row.expr} /></span>{row.cond && <span className="case-cond"><MathBit text={row.cond} /></span>}</li>
        ))}</ul>
      </div>
    );
  }
  if (drawn.kind === "matriz") {
    return (
      <div className="gap-art" data-artifact="matriz">
        <p className="gap-tag">{drawn.tag || "Nota de IA"}</p>
        <table className="gap-matrix"><tbody>{drawn.rows.map((row: any, ri: number) => (
          <tr key={ri}>{row.cells.map((v: number, i: number) => {
            const t = Math.max(0, Math.min(1, (v + 1) / 2));
            const p = Math.round(t * 100);
            return <td key={i} style={{ background: `color-mix(in oklab, var(--accent) ${p}%, var(--sheet))` }} />;
          })}</tr>
        ))}</tbody></table>
        {drawn.freq && <p className="gap-src">{drawn.freq}</p>}
        <p className="gap-src">{drawn.legend}</p>
        {drawn.quote && <p className="gap-src"><Rich text={drawn.quote} /></p>}
      </div>
    );
  }
  const max = Math.max(...drawn.with, ...drawn.without, 0.01);
  const bars = (xs: number[]) => xs.map((v, i) => <div key={i} className="gap-bar"><i style={{ width: `${(v / max) * 100}%` }} /></div>);
  return (
    <div className="gap-art" data-artifact="con_sin">
      <p className="gap-tag">{drawn.tag || "Nota de IA"}</p>
      <p>{drawn.withLabel}</p>{bars(drawn.with)}
      <p>{drawn.withoutLabel}</p>{bars(drawn.without)}
      <p className="gap-src">{drawn.look}</p>
      <p className="gap-src">{drawn.legend}</p>
      {drawn.quote && <p className="gap-src"><Rich text={drawn.quote} /></p>}
    </div>
  );
}

export function ShapePill({ arts }: { arts: any[] }) {
  const hit = (arts || []).find((item) => item.type === "forma" && item.label);
  if (!hit) return null;
  return <span className="shape-pill" data-artifact="forma">{hit.tex ? <Tex tex={hit.tex} /> : hit.label}</span>;
}

export function repeatsBlock(note: any, block: any, arts: any[]) {
  if (!(arts || []).some((item) => item.type === "forma")) return false;
  const quote = String(note?.cite || note?.note || "").replace(/\s+/g, " ").trim();
  const host = plainOf(block?.inlines || []);
  return quote.length > 24 && (host === quote || host.includes(quote));
}

export function artsAt(id: string, pack: any, local: any) {
  const mine = (local?.artifacts || []).filter((item: any) => item.block_id === id);
  const remote = (pack?.artifacts || []).filter((item: any) => item.block_id === id);
  return [...mine, ...remote.filter((item: any) => !mine.some((got: any) => got.type === item.type))];
}

export function notesAt(id: string, pack: any, local: any) {
  const remote = (pack?.notes || []).filter((item: any) => item.block_id === id);
  const mine = (local?.notes || []).filter((item: any) => item.block_id === id && !remote.some((got: any) => got.note === item.note));
  return [...mine, ...remote];
}

export function GapView({ note, art, self, onOpen }: { note?: any; art?: any; self: string; onOpen?: (id: string, why: string) => void }) {
  const drawn = drawnOf(art);
  if (!note && !drawn) return null;
  const other = Boolean(note && note.paper && String(note.paper) !== self);
  const supuesto = note?.kind === "supuesto";
  const generated = note ? note.generated !== false && !supuesto : Boolean(drawn);
  return (
    <aside className={`gap-card${supuesto ? " is-paper" : generated ? " is-ai" : ""}`}>
      {supuesto && <Prov kind="paper" text="paper phrase" />}
      {generated && <Prov kind="simulado" text="AI note" />}
      {note && note.note && <p><Rich text={note.note} /></p>}
      {note && note.generated !== false && note.cite && <p className="gap-cite"><Rich text={note.cite} /></p>}
      {note && (note.section || note.paper) && (
        <p className="gap-src">
          {note.section || ""}{note.paper ? ` · ${note.paper}` : ""}
          {other && onOpen && <button type="button" className="link" onClick={() => onOpen(String(note.paper), "nota")}>Open</button>}
        </p>
      )}
      {drawn && <ArtifactView drawn={drawn} />}
    </aside>
  );
}
