// RRM-95 · hook for extra margin items (RRM-96 widgets plug in here).
//
//   import { registerMarginExtra } from "@/lib/marginExtras";
//   registerMarginExtra(({ paper, reading }) => reading ? [{
//     id: "w-b26",                       // unique per paper
//     anchor: '[data-blk="b26"]',        // CSS selector inside the article; the item aligns with it
//     kind: "extra",                     // → class sn--extra (add your own: sn--<kind>)
//     body: <MyWidgetHook />,            // any React node; clicks are yours
//   }] : []);
//
// Items join the same margin column as the notes, so they align with their
// anchor and never overlap other notes. Under 1280 px the margin column is not
// drawn; items with `inline: true` are rendered under their block instead.
//
// Extras that load data async (RRM-96 widgets) call refreshMarginExtras() when it arrives; Paper subscribes
// with useMarginExtrasVersion() and asks every extra again (a re-render, not only a re-layout).
// An item may list `takes`: things the paper should not draw itself because this extra replaces them
// ("dk-instrument", "art:<block>:<type>"), so one topic shows up once.
import { useSyncExternalStore, type ReactNode } from "react";

export type MarginExtraCtx = { paper: any; reading: boolean; core: boolean };
export type MarginExtraItem = { id: string; anchor: string; dy?: number; kind?: string; inline?: boolean; block?: string; takes?: string[]; body: ReactNode };
export type MarginExtra = (ctx: MarginExtraCtx) => MarginExtraItem[];

const extras: MarginExtra[] = [];
const listeners = new Set<() => void>();
let version = 0;

export function refreshMarginExtras() {
  version += 1;
  listeners.forEach((l) => l());
}

export function registerMarginExtra(fn: MarginExtra) {
  extras.push(fn);
  refreshMarginExtras();
  return () => { const i = extras.indexOf(fn); if (i >= 0) { extras.splice(i, 1); refreshMarginExtras(); } };
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

/** Re-render the caller whenever an extra registers or refreshes. Returns a number that changes each time. */
export function useMarginExtrasVersion() {
  return useSyncExternalStore(subscribe, () => version, () => 0);
}

/** Everything the items of this paper replace (see `takes`). */
export function marginTakes(items: MarginExtraItem[]) {
  return new Set(items.flatMap((x) => x.takes || []));
}

/** Never throws: a broken extra drops out instead of taking the paper with it. */
export function marginExtras(ctx: MarginExtraCtx): MarginExtraItem[] {
  const out: MarginExtraItem[] = [];
  for (const fn of extras) {
    try { out.push(...(fn(ctx) || [])); } catch { /* skip this extra */ }
  }
  return out;
}
