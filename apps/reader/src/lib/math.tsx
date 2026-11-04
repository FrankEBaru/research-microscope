import katex from "katex";
import { useMemo } from "react";
import { displayTex, katexSource } from "@/lib/backend.js";
import { presentInlines } from "@/lib/prose.js";
import { reportFault } from "@/lib/faults.js";

export interface Sym { id: string; latex: string; name: string; color: string; cls?: string }

const SKIP_BRACE = ["\\mathrm", "\\text", "\\textbf", "\\mathbf", "\\operatorname", "\\mathit"];

/** Envuelve símbolos conocidos con color constante y un data-sym para el hover. */
export function colorize(tex: string, syms: Sym[]): string {
  if (!syms.length) return tex;
  const multi = syms.filter((s) => s.latex.length > 1).sort((a, b) => b.latex.length - a.latex.length);
  const single = Object.fromEntries(syms.filter((s) => s.latex.length === 1).map((s) => [s.latex, s]));
  // Automatic symbols (RRM-95) carry a CSS class instead of a color and no data-sym, so the core hover keeps keying on data-tex.
  const wrap = (s: Sym) => (s.cls ? `\\htmlClass{${s.cls}}{${s.latex}}` : `\\htmlData{sym=${s.id}}{\\textcolor{${s.color}}{${s.latex}}}`);
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

/** Display math goes through displayTex (alignment, split, tag). Inline stays a single run. */
function katexInput(tex: string, display: boolean) {
  return display ? displayTex(tex) : katexSource(tex);
}

/** Llaves que no cierran o sobran: las equilibra para un segundo intento de KaTeX. */
export function balanceBraces(tex: string): string {
  let out = "";
  let depth = 0;
  for (let i = 0; i < tex.length; i++) {
    const c = tex[i];
    if (c === "\\") { out += tex.slice(i, i + 2); i += 1; continue; }
    if (c === "{") depth += 1;
    else if (c === "}") {
      if (!depth) continue;
      depth -= 1;
    }
    out += c;
  }
  return out + "}".repeat(depth);
}

/** Texto limpio de un TeX que KaTeX no compila: sin comandos, llaves ni _ ^. */
export function plainTex(tex: string): string {
  return String(tex || "")
    .replace(/\\(?:mathrm|mathbf|mathit|mathsf|text|textrm|textbf|operatorname|boldsymbol|mathcal|left|right|Big|big|Bigg|bigg)\b/g, "")
    .replace(/\\([A-Za-z]+)/g, "$1")
    .replace(/\\(.)/g, "$1")
    .replace(/[{}]/g, "")
    .replace(/[_^]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function renderTex(tex: string, display: boolean, syms: Sym[]) {
  return katex.renderToString(colorize(katexInput(tex, display), syms), { displayMode: display, throwOnError: true, trust: true, strict: "ignore" });
}

/** `plain`: if the TeX does not compile even with balanced braces, show clean text, never raw TeX (notes, titles, quotes). */
export function Tex({ tex, display = false, syms = [] as Sym[], className = "", plain = false }: { tex: string; display?: boolean; syms?: Sym[]; className?: string; plain?: boolean }) {
  const html = useMemo(() => {
    try {
      return { ok: true, h: renderTex(tex, display, syms) };
    } catch {
      const fixed = balanceBraces(String(tex ?? ""));
      if (fixed !== tex) {
        try { return { ok: true, h: renderTex(fixed, display, syms) }; } catch { /* sigue al aviso */ }
      }
      reportFault({ code: "F-KATEX", where: "Tex", detail: String(tex ?? "").slice(0, 120) });
      return { ok: false, h: "" };
    }
  }, [tex, display, syms]);
  if (!html.ok && plain) return <span className={`math-plain ${className}`.trim()}>{plainTex(tex)}</span>;
  if (!html.ok) return <code className="math-fail" title="No se pudo renderizar; se muestra el LaTeX original">{tex}</code>;
  return <span className={className} dangerouslySetInnerHTML={{ __html: html.h }} />;
}

type ProseNode = { t: string; v?: string; c?: ProseNode[]; display?: boolean };

/** Same nodes the paper body uses (`presentInlines`), then the same KaTeX `Tex`. */
function Bits({ nodes }: { nodes: ProseNode[] }) {
  return <>{nodes.map((x, i) => {
    if (!x) return null;
    if (x.t === "text") return <span key={i}>{String(x.v || "").replaceAll("~", "\u00a0")}</span>;
    if (x.t === "math") return <Tex key={i} tex={String(x.v || "")} display={Boolean(x.display)} plain />;
    if (x.t === "em") return <em key={i}><Bits nodes={x.c || []} /></em>;
    if (x.t === "strong") return <strong key={i}><Bits nodes={x.c || []} /></strong>;
    if (x.t === "code") return <code key={i}>{x.v}</code>;
    if (x.t === "span" || x.t === "link") return <Bits key={i} nodes={x.c || []} />;
    return null;
  })}</>;
}

/** Titles, quotes, and table labels. One path with the body: parse, then KaTeX. */
export function Rich({ text }: { text: string }) {
  const nodes = useMemo(() => presentInlines([{ t: "text", v: String(text ?? "") }]) as ProseNode[], [text]);
  return <Bits nodes={nodes} />;
}
