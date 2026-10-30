export type Inline = any;
export interface Block { id: string; kind: "p" | "h" | "eq" | "list" | "fig" | "table"; [k: string]: any }
export interface Paper {
  arxivId: string; title: string; authors: string[]; date: string; abstract: string;
  license?: string | null; authorNotes?: string[]; full: boolean; refs: Record<string, string>; refLabels?: Record<string, string>; blocks: Block[];
  corpusid?: number; tldr?: string; stage?: string; source?: string; upgraded_from?: string;
}
export interface Anchor { paper: string; quote: string; anchor: { blockId: string; where: string; quote: string } }
export type Prov = "paper" | "curado" | "simulado" | "calculo" | "hipotesis";
