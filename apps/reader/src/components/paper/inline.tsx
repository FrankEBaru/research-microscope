import type { Inline } from "@/lib/types";
import type { Sym } from "@/lib/math";

export function plainOf(inls: Inline[]): string {
  return (inls || []).map((x) => x.t === "text" ? x.v : x.t === "math" ? `$${x.v}$` : x.t === "cite" ? "" : x.t === "note" ? "" : Array.isArray(x.c) ? plainOf(x.c) : x.v || "").join("").replace(/\s+/g, " ").trim();
}

export interface Ctx {
  figs?: Set<string>;
  syms: Sym[];
  refIndex: Record<string, number>;
  refLabels?: Record<string, string>;
  xref?: Record<string, string>;
  target?: Record<string, string>;
  counter: { n: number };
  core?: boolean;
  block?: string;
  sent?: number;
  popKey?: string;
  pin?: { kind: string; val: string } | null;
}
