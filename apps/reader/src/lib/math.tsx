import katex from "katex";
import { useMemo } from "react";
import { katexSource } from "@/lib/backend.js";

export interface Sym { id: string; latex: string; name: string; color: string }

const SKIP_BRACE = ["\\mathrm", "\\text", "\\textbf", "\\mathbf", "\\operatorname", "\\mathit"];

/** Envuelve símbolos conocidos con color constante y un data-sym para el hover. */
export function colorize(tex: string, syms: Sym[]): string {
  if (!syms.length) return tex;
  const multi = syms.filter((s) => s.latex.length > 1).sort((a, b) => b.latex.length - a.latex.length);
  const single = Object.fromEntries(syms.filter((s) => s.latex.length === 1).map((s) => [s.latex, s]));
  const wrap = (s: Sym) => `\\htmlData{sym=${s.id}}{\\textcolor{${s.color}}{${s.latex}}}`;
  let out = "";
  let i = 0;
  while (i < tex.length) {
    const rest = tex.slice(i);
    const skip = SKIP_BRACE.find((c) => rest.startsWith(c + "{"));
    if (skip) {
      let depth = 0, j = i + skip.length;
      do { if (tex[j] === "{") depth++; else if (tex[j] === "}") depth--; j++; } while (depth > 0 && j < tex.length);
      out += tex.slice(i, j); i = j; continue;
    }
    if (tex[i] === "\\") {
      const m = /^\\([A-Za-z]+|.)/.exec(rest);
      out += m[0]; i += m[0].length; continue;
    }
    const prev = i > 0 ? tex[i - 1] : "";
    const ms = multi.find((s) => rest.startsWith(s.latex) && !/[A-Za-z]/.test(prev));
    if (ms) { out += wrap(ms); i += ms.latex.length; continue; }
    const ss = single[tex[i]];
    if (ss && prev !== "^" && prev !== "_" && !/[A-Za-z]/.test(tex[i + 1] || "") ) { out += wrap(ss); i++; continue; }
    if (ss && prev !== "^" && prev !== "_") { out += wrap(ss); i++; continue; }
    out += tex[i]; i++;
  }
  return out;
}

/** Alineaciones de LaTeX sin entorno: KaTeX solo acepta & dentro de aligned. El \\tag queda fuera. */
function katexInput(tex: string, display: boolean) {
  let s = katexSource(tex);
  if (!display || /\\begin\{/.test(s)) return s;
  const tag = s.match(/\\tag\{[^{}]*\}$/);
  let body = s;
  let suffix = "";
  if (tag && tag.index != null) {
    body = s.slice(0, tag.index);
    suffix = tag[0];
  }
  if (body.includes("&") || body.includes("\\\\")) s = `\\begin{aligned}${body}\\end{aligned}${suffix}`;
  return s;
}

export function Tex({ tex, display = false, syms = [] as Sym[], className = "" }: { tex: string; display?: boolean; syms?: Sym[]; className?: string }) {
  const html = useMemo(() => {
    try {
      return { ok: true, h: katex.renderToString(colorize(katexInput(tex, display), syms), { displayMode: display, throwOnError: true, trust: true, strict: "ignore" }) };
    } catch {
      return { ok: false, h: "" };
    }
  }, [tex, display, syms]);
  if (!html.ok) return <code className="math-fail" title="No se pudo renderizar; se muestra el LaTeX original">{tex}</code>;
  return <span className={className} dangerouslySetInnerHTML={{ __html: html.h }} />;
}

/** Texto con $math$ (citas literales de abstracts). */
export function Rich({ text }: { text: string }) {
  const parts = text.split(/(\$[^$]+\$)/g).filter(Boolean);
  return <>{parts.map((p, i) => (p.startsWith("$") && p.endsWith("$") && p.length > 2 ? <Tex key={i} tex={p.slice(1, -1)} /> : <span key={i}>{p}</span>))}</>;
}
