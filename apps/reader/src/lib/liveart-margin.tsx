"use client";
// RRM-98 · RRM-96 live figures in the reader margin, behind NEXT_PUBLIC_RRM_LIVEART=1.
// Imported once by Paper.tsx. The bundle (compass data, never in git) loads async from
// NEXT_PUBLIC_RRM_LIVEART_BASE (default /liveart96, see scripts/liveart_assets.sh); when it arrives,
// refreshMarginExtras() makes Paper ask again.
//
// Attention: one topic, one hook. "Why divide by √dₖ?" sits in the margin next to "To counteract this effect…",
// and opens the large panel with the RRM-95 instrument first and the Muse attn-scale figure second. The paper
// then draws neither the inline instrument nor the local "dividing by √dₖ" drawing (takes).
import { refreshMarginExtras, registerMarginExtra, type MarginExtraItem } from "@/lib/marginExtras";
import { LIVEART_ON, liveNotes } from "@/components/liveart/liveNotes";
import LiveHook from "@/components/liveart/LiveHook";
import DkInstrument, { dkAnchor } from "@/components/paper/DkInstrument";
import { loadBundle, type LiveEntry } from "@/lib/liveart/live96";
import { Tex } from "@/lib/math";
import { scanIds } from "@/lib/scan.js";
import "@/styles/liveart-b1.css";

let entries: LiveEntry[] = [];
let asked = false;

function plain(inls: any[]): string {
  return (inls || []).map((x) => (typeof x?.v === "string" ? x.v : Array.isArray(x?.c) ? plain(x.c) : "")).join("");
}

function load() {
  if (asked || !LIVEART_ON || typeof window === "undefined") return;
  asked = true;
  loadBundle().then((e) => { entries = e; refreshMarginExtras(); }).catch(() => {});
}

const DK_LEAD = { label: "Instrument", title: <>Why divide by <Tex tex="\sqrt{d_k}" />?</>, node: <DkInstrument /> };

function dkItem(paper: any, attn: LiveEntry, fallback?: string): MarginExtraItem | null {
  const at = dkAnchor(paper, plain) || fallback || "";
  if (!at) return null;
  // The local drawing of Eq. 1 ("dividing by √dₖ", lib/artifacts.js) lives on the equation block.
  const eqs = (paper.blocks || []).filter((b: any) => b.kind === "eq" && /\\sqrt\s*\{\s*d_\{?k\}?\s*\}/.test(String(b.tex || b.latex || "")));
  return {
    id: "lv-dk",
    anchor: `[data-blk="${at}"]`,
    kind: "lv",
    inline: true,
    block: at,
    takes: ["dk-instrument", ...eqs.map((b: any) => `art:${b.id}:con_sin`)],
    body: <LiveHook entry={attn} lead={DK_LEAD} />,
  };
}

if (LIVEART_ON) {
  registerMarginExtra(({ paper, core, reading }) => {
    load();
    if (!entries.length) return [];
    // Scan mode draws only some blocks: a hook whose block is not drawn would have nothing to align with.
    const shown: Set<string> | null = core && !reading ? scanIds(paper.blocks) : null;
    const notes = liveNotes(paper.blocks, paper.arxivId, entries).map((n) => ({ ...n, inline: true, block: n.anchor.slice(11, -2) }));
    const attn = entries.find((e) => e.id === "attn-scale");
    const dk = core && attn ? dkItem(paper, attn, notes.find((n) => n.id === "lv-attn-scale")?.block) : null;
    const out = dk ? [...notes.filter((n) => n.id !== "lv-attn-scale"), dk] : notes;
    return shown ? out.filter((n) => shown.has(n.block)) : out;
  });
}
