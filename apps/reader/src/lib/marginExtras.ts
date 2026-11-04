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
import type { ReactNode } from "react";

export type MarginExtraCtx = { paper: any; reading: boolean; core: boolean };
export type MarginExtraItem = { id: string; anchor: string; dy?: number; kind?: string; inline?: boolean; block?: string; body: ReactNode };
export type MarginExtra = (ctx: MarginExtraCtx) => MarginExtraItem[];

const extras: MarginExtra[] = [];

export function registerMarginExtra(fn: MarginExtra) {
  extras.push(fn);
  return () => { const i = extras.indexOf(fn); if (i >= 0) extras.splice(i, 1); };
}

/** Never throws: a broken extra drops out instead of taking the paper with it. */
export function marginExtras(ctx: MarginExtraCtx): MarginExtraItem[] {
  const out: MarginExtraItem[] = [];
  for (const fn of extras) {
    try { out.push(...(fn(ctx) || [])); } catch { /* skip this extra */ }
  }
  return out;
}
