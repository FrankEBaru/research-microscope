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
  if (/\\|_|\^/.test(raw)) return <Tex tex={raw} plain />;
  return <>{raw}</>;
}

export function Stepper({ drawn }: { drawn: any }) {
  const [i, setI] = useState(0);
  const n = drawn.steps.length;
  const cur = Math.min(i, Math.max(0, n - 1));
  return (
    <div className="gap-art" data-artifact="pasos">
      <p className="gap-tag">illustrative</p>
      {drawn.title && <p><Rich text={drawn.title} /></p>}
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

function artEn(text: string) {
  return String(text || "")
    .replaceAll("casi todo el peso cae en una sola clave.", "almost all the weight lands on one key.")
    .replaceAll("Cada barra es una coordenada, antes y después de dividir entre σ.", "Each bar is a coordinate, before and after dividing by σ.")
    .replaceAll("Cada fila es una dimensión. La de arriba (i = 0) cambia más rápido.", "Each row is a dimension. The top one (i = 0) changes faster.")
    .replaceAll("Cada fila es un k.", "Each row is a k.")
    .replaceAll("después de dividir entre", "after dividing by")
    .replaceAll("antes de dividir", "before dividing")
    .replaceAll("dividiendo entre", "dividing by")
    .replaceAll("Sin dividir", "Without dividing")
    .replaceAll("sin dividir", "without dividing")
    .replaceAll("ilustrativo", "illustrative")
    .replaceAll("Ilustrativo", "Illustrative")
    .replaceAll("Nota de IA", "AI note");
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
        <p className="gap-tag">{artEn(drawn.tag || "AI note")}</p>
        <table className="gap-matrix"><tbody>{drawn.rows.map((row: any, ri: number) => (
          <tr key={ri}>{row.cells.map((v: number, i: number) => {
            const t = Math.max(0, Math.min(1, (v + 1) / 2));
            const p = Math.round(t * 100);
            return <td key={i} style={{ background: `color-mix(in oklab, var(--accent) ${p}%, var(--sheet))` }} />;
          })}</tr>
        ))}</tbody></table>
        {drawn.freq && <p className="gap-src">{artEn(drawn.freq)}</p>}
        <p className="gap-src">{artEn(drawn.legend)}</p>
        {drawn.quote && <p className="gap-src"><Rich text={drawn.quote} /></p>}
      </div>
    );
  }
  const max = Math.max(...drawn.with, ...drawn.without, 0.01);
  const bars = (xs: number[]) => xs.map((v, i) => <div key={i} className="gap-bar"><i style={{ width: `${(v / max) * 100}%` }} /></div>);
  return (
    <div className="gap-art" data-artifact="con_sin">
      <p className="gap-tag">{artEn(drawn.tag || "AI note")}</p>
      <p>{artEn(drawn.withLabel)}</p>{bars(drawn.with)}
      <p>{artEn(drawn.withoutLabel)}</p>{bars(drawn.without)}
      <p className="gap-src">{artEn(drawn.look)}</p>
      <p className="gap-src">{artEn(drawn.legend)}</p>
      {drawn.quote && <p className="gap-src"><Rich text={drawn.quote} /></p>}
    </div>
  );
}

export function ShapePill({ arts }: { arts: any[] }) {
  const hit = (arts || []).find((item) => item.type === "forma" && item.label);
  if (!hit) return null;
  return <span className="shape-pill" data-artifact="forma">{hit.tex ? <Tex tex={hit.tex} /> : hit.label}</span>;
}

export function normPhrase(s: string) {
  return String(s || "")
    .replace(/\[cite\]/gi, " ")
    .replace(/\$[^$]*\$/g, " ")
    .replace(/\\[a-zA-Z]+/g, " ")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function samePhrase(a: string, b: string) {
  const x = normPhrase(a);
  const y = normPhrase(b);
  if (x.length < 24 || y.length < 24) return false;
  if (x === y || x.includes(y) || y.includes(x)) return true;
  const bag = new Set(x.split(" "));
  const words = y.split(" ").filter((word) => word.length > 3);
  if (words.length < 8) return false;
  const hit = words.filter((word) => bag.has(word)).length;
  return hit / words.length > 0.75;
}

function noNews(bit: string, host: string) {
  const n = normPhrase(bit);
  if (!n || n.length < 12) return true;
  return samePhrase(bit, host);
}

export function repeatsBlock(note: any, block: any, _arts?: any[]) {
  const host = plainOf(block?.inlines || []);
  const bits = [note?.note, note?.cite].map((bit) => String(bit || "").trim()).filter(Boolean);
  if (!bits.length) return false;
  return bits.every((bit) => noNews(bit, host));
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

function cleanNote(s: string) {
  return String(s || "").replace(/\[cite\]/gi, "").replace(/\s+/g, " ").trim();
}

export function GapView({ note, art, self, host = "", titleOf, onOpen }: { note?: any; art?: any; self: string; host?: string; titleOf?: (id: string) => string; onOpen?: (id: string, why: string) => void }) {
  const drawn = drawnOf(art);
  const body = cleanNote(note?.note || "");
  const cite = cleanNote(note?.cite || "");
  const showBody = body && !samePhrase(body, host) && normPhrase(body).length >= 12;
  const showCite = cite && !samePhrase(cite, host) && !samePhrase(cite, body) && normPhrase(cite).length >= 12;
  if (!showBody && !showCite && !drawn) return null;
  const otherId = note && note.paper && String(note.paper) !== String(self || "") ? String(note.paper) : "";
  const otherTitle = otherId ? (titleOf?.(otherId) || "") : "";
  const supuesto = note?.kind === "supuesto";
  const generated = note ? note.generated !== false && !supuesto : Boolean(drawn);
  return (
    <aside className={`gap-card${supuesto ? " is-paper" : generated ? " is-ai" : ""}`}>
      {supuesto && showBody && <Prov kind="paper" text="paper phrase" />}
      {generated && (showBody || showCite || drawn) && <Prov kind="simulado" text="AI note" />}
      {showBody && <p><Rich text={body} /></p>}
      {showCite && <p className="gap-cite"><Rich text={cite} /></p>}
      {(note?.section || otherTitle) && (showBody || showCite) && (
        <p className="gap-src">
          {note?.section || ""}{otherTitle ? `${note?.section ? " · " : ""}${otherTitle}` : ""}
          {otherId && onOpen && <button type="button" className="link" onClick={() => onOpen(otherId, "nota")}>Open</button>}
        </p>
      )}
      {drawn && <ArtifactView drawn={drawn} />}
    </aside>
  );
}
