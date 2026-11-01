// Hover sobre el texto del autor. Sin números nuevos y sin el fixture curado.

export const UNDEFINED = "el paper no lo define";

function textOf(nodes) {
  return (nodes || []).map((node) => {
    if (!node || typeof node !== "object") return "";
    if (node.t === "math") return node.v || "";
    if (node.t === "text" || node.t === "code") return node.v || "";
    if (Array.isArray(node.c)) return textOf(node.c);
    return "";
  }).join("");
}

function mathOf(nodes) {
  const bits = [];
  for (const node of nodes || []) {
    if (!node || typeof node !== "object") continue;
    if (node.t === "math" && node.v) bits.push(String(node.v));
    if (Array.isArray(node.c)) bits.push(...mathOf(node.c));
  }
  return bits;
}

function clean(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

export function sentences(blocks) {
  const out = [];
  let section = "";
  for (const block of blocks || []) {
    if (block.kind === "h") {
      section = clean(textOf(block.inlines)) || section;
      continue;
    }
    if (block.kind !== "p") continue;
    const sents = block.sents && block.sents.length ? block.sents : [block.inlines || []];
    sents.forEach((sent, index) => {
      out.push({ block: block.id, index, section, text: clean(textOf(sent)), math: mathOf(sent) });
    });
  }
  return out;
}

function hasSymbol(sentence, tex) {
  const needle = String(tex || "").replace(/\s+/g, "");
  if (!needle) return false;
  const blobs = [sentence.text, ...(sentence.math || [])];
  return blobs.some((blob) => String(blob).replace(/\s+/g, "").includes(needle));
}

export function symbolHover(blocks, tex, at) {
  const seq = sentences(blocks);
  let cursor = seq.length - 1;
  if (at) {
    const pos = seq.findIndex((row) => row.block === at.block && row.index === at.index);
    if (pos >= 0) cursor = pos;
  }
  let found = null;
  seq.forEach((row, index) => {
    if (index <= cursor && hasSymbol(row, tex)) found = row;
  });
  if (!found) return { text: UNDEFINED };
  return { text: found.text, section: found.section };
}

export function equationHover(blocks, blockId) {
  const list = blocks || [];
  const at = list.findIndex((block) => block.id === blockId);
  const prev = at > 0 ? list[at - 1] : null;
  if (!prev || prev.kind !== "p") return { texts: [] };
  const sents = prev.sents && prev.sents.length ? prev.sents : [prev.inlines || []];
  return { texts: sents.map((sent) => clean(textOf(sent))).filter(Boolean) };
}

export function tableHover(blocks, blockId) {
  const list = blocks || [];
  const at = list.findIndex((block) => block.id === blockId);
  const table = at >= 0 ? list[at] : null;
  const caption = clean(textOf(table && table.caption));
  const label = (table && table.label) || "";
  const seq = sentences(list);
  let best = null;
  let bestDist = Infinity;
  seq.forEach((row) => {
    const where = list.findIndex((block) => block.id === row.block);
    const mentions = (label && row.text.includes(label)) || /tabla|table/i.test(row.text);
    if (!mentions || where < 0) return;
    const dist = Math.abs(where - at);
    if (dist < bestDist) {
      bestDist = dist;
      best = row;
    }
  });
  return { caption, sentence: best ? best.text : "" };
}
