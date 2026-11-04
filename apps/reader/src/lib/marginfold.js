// RRM-103b: margin notes stack under each other so they never overlap; in a dense stretch the stack drifted far from
// its marks (Attention §3.2: 1.7k px). foldPlan places the notes top-down and, while some note would sit more than
// `limit` px below its mark, folds the tallest foldable note in the pile pushing it (or the note itself).
// Pure, so node tests can run it. rows: [{ id, raw, h }] sorted by raw (raw = mark top in column px).

function layout(rows, folded, foldH, gap) {
  const tops = {};
  const bottom = {};
  let floor = -Infinity;
  for (const row of rows) {
    const h = folded.has(row.id) ? Math.min(row.h, foldH) : row.h;
    const top = Math.max(row.raw, floor);
    tops[row.id] = top;
    bottom[row.id] = top + h;
    floor = top + h + gap;
  }
  return { tops, bottom };
}

/**
 * @param {{ id: string, raw: number, h: number }[]} rows
 * @param {{ limit?: number, foldH?: number, gap?: number, canFold?: (id: string) => boolean }} [opts]
 */
export function foldPlan(rows, { limit = 250, foldH = 64, gap = 12, canFold = (_id) => true } = {}) {
  const folded = new Set();
  const can = (row) => canFold(row.id) && row.h > foldH + 16 && !folded.has(row.id);
  let plan = layout(rows, folded, foldH, gap);
  const pileOf = (bad) => {
    // The pile pushing it: the chain of touching notes above it (each one pushed by the one before), and itself.
    const chain = [rows[bad]];
    for (let j = bad; j > 0; j--) {
      const cur = rows[j], prev = rows[j - 1];
      if (plan.tops[cur.id] - cur.raw < 1 || plan.bottom[prev.id] + gap < plan.tops[cur.id] - 1) break;
      chain.push(prev);
    }
    return chain.filter(can);
  };
  for (let iter = 0; iter < rows.length; iter++) {
    // Every note too far from its mark, top-down; the first one whose pile can still fold gets a fold.
    // (A footnote pushed by a widget hook has nothing to fold: skip it, do not stop there.)
    let pile = [];
    for (let i = 0; i < rows.length && !pile.length; i++) {
      if (plan.tops[rows[i].id] - rows[i].raw > limit) pile = pileOf(i);
    }
    if (!pile.length) break;
    pile.sort((x, y) => y.h - x.h);
    folded.add(pile[0].id);
    plan = layout(rows, folded, foldH, gap);
  }
  const drift = Math.max(0, ...rows.map((row) => plan.tops[row.id] - row.raw));
  return { tops: plan.tops, folded: rows.filter((row) => folded.has(row.id)).map((row) => row.id), drift };
}
