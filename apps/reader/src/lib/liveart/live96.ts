// RRM-96: what the reader needs to place a verified rrm-widget/0.4 next to its claim.
// A bundle entry is produced by scripts/liveart_bundle.py from a live Muse run; nothing here is drawn by hand.

export type Knob = {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  kind?: string;
  options?: string[];
  tex?: string;
  color?: string;
};
export type Readout = { id: string; label: string; digits?: number; unit?: string; format?: string; color?: string; show?: boolean };
export type Question = { q: string; why?: string; set?: Record<string, number> };
export type Anchor = { latex?: string; quote?: string; arxiv?: string; section?: string; eq?: string; passage_id?: string };
export type Widget04 = {
  version: string;
  id: string;
  topic: string;
  title: string;
  hook?: string;
  explain: string;
  questions: Question[];
  controls: Knob[];
  readouts?: Readout[];
  legend?: { color: string; text: string; kind?: string }[];
  takeaway?: string | Record<string, string>;
  marks?: { id: string; control?: string; label: string; color?: string }[];
  anchor?: Anchor;
  draw: string;
};
export type Frame = {
  readouts: Record<string, number>;
  say: string | null;
  cmarks: { id: string; control: string; label?: string; value: number; color?: string }[];
} | null;

export type LiveEntry = {
  id: string;
  widget: Widget04;
  meta: { paper: string; authors: string; year: number; arxiv: string; section: string; section_title: string; eq: string };
  verdict: { verify: string; sandbox: string; reasons: string[]; gate: string[]; model_verifier: string; pixels?: number };
  provenance: { model: string; config: string; run: string; date: string; cost_usd: number; contract: string; sha: string };
  // Real text from the paper (offline data in compass), so the sample page reads like the reader.
  // A block is a paragraph (inline $tex$; [[…]] marks the claim sentence) or a numbered display equation.
  passage?: { heading: string; blocks: { p?: string; eq?: string; no?: string; claim?: boolean }[] };
};

const VAR_COLOR: Record<string, string> = { c1: "var(--viz-1)", c2: "var(--viz-2)", c3: "var(--viz-3)", c4: "var(--viz-4)", ref: "var(--viz-ref)", ink: "var(--ink)" };
export function cssColor(name?: string) {
  return (name && VAR_COLOR[name]) || "var(--ink)";
}

export function decimals(step: number) {
  const text = String(step);
  const dot = text.indexOf(".");
  return dot < 0 ? 0 : Math.min(4, text.length - dot - 1);
}

export function fmtRead(r: Readout | undefined, v: number) {
  if (!Number.isFinite(v)) return "—";
  if (r && r.format === "pct") return (v * 100).toFixed(r.digits ?? 0) + "%";
  const d = r && r.digits != null ? r.digits : 2;
  const abs = Math.abs(v);
  // Very large or very small values read better in powers of ten than as a row of zeros.
  if (abs >= 1e6 || (abs > 0 && abs < 1e-3)) {
    const [m, e] = v.toExponential(Math.max(1, Math.min(2, d))).split("e");
    return `${m}×10${superscript(e)}`;
  }
  return v.toFixed(d) + (r && r.unit ? r.unit : "");
}

const SUP: Record<string, string> = { "-": "⁻", "+": "", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
function superscript(e: string) {
  return e.split("").map((c) => SUP[c] ?? c).join("");
}

export function fmtControl(c: Knob, v: number) {
  if (c.kind === "select" && c.options && c.options.length) {
    const i = Math.round((v - c.min) / (c.step || 1));
    return c.options[i] ?? String(v);
  }
  if (c.kind === "toggle") return v >= 0.5 ? "on" : "off";
  return v.toFixed(decimals(c.step));
}

export type TakePart = { text: string; id?: string; color?: string };

// The takeaway is a sentence with {readout} and {control} slots; each slot comes back as its own part
// so the panel can paint the live number in the color of its series.
export function takeawayParts(w: Widget04, frame: Frame, vals: Record<string, number>): TakePart[] {
  if (!frame || !w.takeaway) return [];
  const tpl = typeof w.takeaway === "string" ? w.takeaway : (frame.say && w.takeaway[frame.say]) || Object.values(w.takeaway)[0] || "";
  const parts: TakePart[] = [];
  let last = 0;
  for (const m of tpl.matchAll(/\{(\w+)\}/g)) {
    const k = m[1];
    if (m.index! > last) parts.push({ text: tpl.slice(last, m.index) });
    const r = (w.readouts || []).find((q) => q.id === k);
    if (r && k in frame.readouts) parts.push({ text: fmtRead(r, frame.readouts[k]), id: k, color: r.color });
    else {
      const c = w.controls.find((q) => q.id === k);
      parts.push({ text: c && k in vals ? fmtControl(c, vals[k]) : "", id: k });
    }
    last = m.index! + m[0].length;
  }
  if (last < tpl.length) parts.push({ text: tpl.slice(last) });
  return parts;
}

// Short id shown in the provenance line: stable for the same widget JSON.
export function shortSha(sha: string) {
  return (sha || "").slice(0, 7);
}

export function sectionCite(meta: LiveEntry["meta"]) {
  const bits = [`arXiv ${meta.arxiv}`, meta.section ? `§${meta.section}` : "", meta.eq ? (/^\d+$/.test(meta.eq) ? `Eq. ${meta.eq}` : meta.eq) : ""];
  return bits.filter(Boolean).join(" · ");
}

let fontBytes: Promise<ArrayBuffer | null> | null = null;
// R3: the iframe gets the UI font as bytes; the CSP stays closed.
export function uiFont(base = "/liveart96") {
  if (!fontBytes) fontBytes = fetch(`${base}/ui.woff2`).then((r) => (r.ok ? r.arrayBuffer() : null)).catch(() => null);
  return fontBytes;
}

export async function loadBundle(base = "/liveart96"): Promise<LiveEntry[]> {
  const r = await fetch(`${base}/bundle.json`, { cache: "no-store" });
  if (!r.ok) throw new Error(`bundle ${r.status}`);
  const data = await r.json();
  return Array.isArray(data.entries) ? data.entries : [];
}
