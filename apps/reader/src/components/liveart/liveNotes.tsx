// RRM-96 · Integration point for the reader (Paper.tsx, owned by RRM-95). Behind NEXT_PUBLIC_RRM_LIVEART=1:
//   const live = useLiveEntries();                                   // once per paper view
//   side.push(...liveNotes(paper.blocks, paper.arxivId, live));      // next to the other margin notes
// A hook appears only for a widget that passed the verifier and the sandbox, on the block that holds its claim.
import { useEffect, useState } from "react";
import { loadBundle, type LiveEntry } from "@/lib/liveart/live96";
import LiveHook from "./LiveHook";

export const LIVEART_ON = process.env.NEXT_PUBLIC_RRM_LIVEART === "1";

type Block = { id?: string; kind?: string; inlines?: { t: string; v?: string }[] };

const words = (s: string) => s.replace(/\$[^$]*\$/g, " ").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

function blockText(b: Block) {
  return words((b.inlines || []).map((x) => (x.t === "text" ? x.v || "" : " ")).join(""));
}

export function useLiveEntries() {
  const [entries, setEntries] = useState<LiveEntry[]>([]);
  useEffect(() => {
    if (!LIVEART_ON) return;
    loadBundle().then(setEntries).catch(() => setEntries([]));
  }, []);
  return entries;
}

export function liveNotes(blocks: Block[] | undefined, arxivId: string | undefined, entries: LiveEntry[]) {
  if (!LIVEART_ON || !arxivId || !blocks?.length) return [];
  const id = String(arxivId).replace(/v\d+$/, "");
  const notes = [];
  for (const e of entries) {
    if (e.meta.arxiv !== id) continue;
    // The first six words of the quote, math left out: enough to find the paragraph, robust to KaTeX.
    const key = words(e.widget.anchor?.quote || "").split(" ").slice(0, 6).join(" ");
    const hit = key && blocks.find((b) => b.id && b.kind === "p" && blockText(b).includes(key));
    if (!hit) continue;
    notes.push({ id: `lv-${e.id}`, anchor: `[data-blk="${hit.id}"]`, kind: "lv", body: <LiveHook entry={e} /> });
  }
  return notes;
}
