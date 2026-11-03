// Passages that cite a figure or table. Exact target, or exact label when target is absent.

function refPlain(x, xref, prev) {
  const label = x.label || "";
  let text = x.number != null
    ? (String(label).startsWith("eq") ? `(${x.number})` : String(x.number))
    : ((xref && xref[label]) || label);
  // The sentence already says "Figure"; the cross-reference also starts with that word.
  if (/(?:figure|fig\.|table|tab\.|section|sec\.|equation|eq\.|appendix)\s*~?\s*$/i.test(prev || "")
    && /^(Figure|Table|Section|Appendix|equation)\s+/.test(text)) {
    text = text.replace(/^\S+\s+/, "");
  }
  return text;
}

function walk(nodes, fn) {
  for (const x of nodes || []) {
    if (!x || typeof x !== "object") continue;
    fn(x);
    if (Array.isArray(x.c)) walk(x.c, fn);
  }
}

function plainSent(nodes, xref) {
  const parts = [];
  walk(nodes, (x) => {
    if (x.t === "text") parts.push(x.v || "");
    else if (x.t === "math") parts.push(`$${x.v}$`);
    else if (x.t === "ref") parts.push(refPlain(x, xref, parts.join("")));
    else if (x.v && x.t !== "cite" && x.t !== "note" && !Array.isArray(x.c)) parts.push(String(x.v));
  });
  return parts.join("").replace(/~/g, " ").replace(/\s+/g, " ").trim();
}

function clip(text) {
  if (text.length <= 200) return text;
  return `${text.slice(0, 199).trimEnd()}…`;
}

function hits(x, targetId, label) {
  const target = x.target ? String(x.target) : "";
  if (x.t !== "ref") return false;
  if (target) return target === targetId;
  const lab = x.label || "";
  return Boolean(label) && lab === label;
}

function sentencesOf(block) {
  return Array.isArray(block.sents) && block.sents.length ? block.sents : [block.inlines];
}

function rank(rows, max) {
  rows.sort((a, b) => b.mentions - a.mentions || a.dist - b.dist || a.index - b.index);
  const view = rows.map(({ block, sent, text }) => ({ block, sent, text }));
  const cut = max == null ? 2 : Math.max(0, max);
  return { top: view.slice(0, cut), rest: view.slice(cut) };
}

/** @returns {{ top: {block: string, sent: number, text: string}[], rest: {block: string, sent: number, text: string}[] }} */
export function citingPassages(blocks, targetId, label, max = 2, xref) {
  const list = blocks || [];
  const want = targetId == null ? "" : String(targetId);
  const lab = label || "";
  let at = -1;
  list.forEach((b, i) => { if (b && b.id === want) at = i; });
  const rows = [];
  list.forEach((b, index) => {
    if (!b || b.kind !== "p") return;
    let mentions = 0;
    let sent = -1;
    let text = "";
    sentencesOf(b).forEach((nodes, si) => {
      let n = 0;
      walk(nodes, (x) => { if (hits(x, want, lab)) n += 1; });
      if (!n) return;
      mentions += n;
      if (sent < 0) { sent = si; text = clip(plainSent(nodes, xref)); }
    });
    if (!mentions) return;
    rows.push({ block: b.id, sent, text, mentions, dist: at < 0 ? index : Math.abs(index - at), index });
  });
  return rank(rows, max);
}

/** One walk: figure and table ids → { top, rest }. */
export function citingIndex(blocks, xref, max = 2) {
  const list = blocks || [];
  const figs = [];
  list.forEach((b, index) => {
    if (b && (b.kind === "fig" || b.kind === "table")) figs.push({ id: String(b.id), label: b.label || "", index });
  });
  const byId = new Map(figs.map((f) => [f.id, f]));
  const byLabel = new Map();
  figs.forEach((f) => { if (f.label && !byLabel.has(f.label)) byLabel.set(f.label, f.id); });
  const buckets = new Map();
  list.forEach((b, index) => {
    if (!b || b.kind !== "p") return;
    const seen = new Map();
    sentencesOf(b).forEach((nodes, si) => {
      walk(nodes, (x) => {
        if (!x || x.t !== "ref") return;
        const target = x.target ? String(x.target) : "";
        const id = target ? (byId.has(target) ? target : "") : ((x.label && byLabel.get(x.label)) || "");
        if (!id) return;
        let row = seen.get(id);
        if (!row) {
          row = { block: b.id, sent: si, text: clip(plainSent(nodes, xref)), mentions: 0, dist: Math.abs(index - byId.get(id).index), index };
          seen.set(id, row);
        }
        row.mentions += 1;
      });
    });
    for (const [id, row] of seen) {
      if (!buckets.has(id)) buckets.set(id, []);
      buckets.get(id).push(row);
    }
  });
  const out = {};
  for (const [id, rows] of buckets) out[id] = rank(rows, max);
  return out;
}
