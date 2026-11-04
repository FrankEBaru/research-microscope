import katex from "katex";
import { useMemo } from "react";
import { displayTex, katexSource } from "@/lib/backend.js";
import { presentInlines } from "@/lib/prose.js";
import { reportFault } from "@/lib/faults.js";

export interface Sym { id: string; latex: string; name: string; color: string; cls?: string }

export { colorize, TEX_MACROS } from "@/lib/texcolor.js";
import { colorize, TEX_MACROS, texFix } from "@/lib/texcolor.js";

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
  const src = texFix(katexInput(tex, display));
  const opts = { displayMode: display, throwOnError: true, trust: true, strict: "ignore" as const };
  try {
    return katex.renderToString(colorize(src, syms), { ...opts, macros: { ...TEX_MACROS } });
  } catch {
    // Symbol color must never cost an equation: same TeX, no color.
    return katex.renderToString(src, { ...opts, macros: { ...TEX_MACROS } });
  }
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
