// Hover sobre el texto del autor. Sin números nuevos y sin el fixture curado.

export const UNDEFINED = "the paper does not define it";

function textOf(nodes) {
  return (nodes || []).map((node) => {
    if (!node || typeof node !== "object") return "";
    if (node.t === "math") return node.v || "";
    if (node.t === "text" || node.t === "code") return node.v || "";
    if (Array.isArray(node.c)) return textOf(node.c);
    return "";
  }).join("");
}

/** Misma frase, con el math envuelto para que el globo pase por KaTeX. */
function showOf(nodes) {
  return (nodes || []).map((node) => {
    if (!node || typeof node !== "object") return "";
    if (node.t === "math") {
      const v = String(node.v || "");
      if (!v) return "";
      return node.display ? `\\[${v}\\]` : `$${v}$`;
    }
    if (node.t === "text" || node.t === "code") return node.v || "";
    if (Array.isArray(node.c)) return showOf(node.c);
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
      out.push({ block: block.id, index, section, text: clean(textOf(sent)), shown: showOf(sent).trim(), math: mathOf(sent) });
    });
  }
  return out;
}

function hasSymbol(sentence, tex) {
  const needle = String(tex || "").replace(/\s+/g, "");
  if (!needle) return false;
  // $H$ es un símbolo. La letra H dentro de una palabra ("Here") no lo es.
  if (needle.length <= 2 && /^[A-Za-z]+$/.test(needle)) {
    return (sentence.math || []).some((blob) => String(blob).replace(/\s+/g, "") === needle);
  }
  const blobs = [sentence.text, ...(sentence.math || [])];
  return blobs.some((blob) => String(blob).replace(/\s+/g, "").includes(needle));
}

/** La frase aporta algo además del símbolo (no es solo "$H$"). */
function explains(sentence, tex) {
  const needle = String(tex || "").replace(/\s+/g, "");
  const rest = String(sentence.text || "").replace(/\s+/g, "").split(needle).join("");
  return rest.replace(/[^A-Za-z]+/g, "").length > 12;
}

export function symbolHover(blocks, tex, at) {
  const seq = sentences(blocks);
  let cursor = seq.length - 1;
  if (at) {
    const pos = seq.findIndex((row) => row.block === at.block && row.index === at.index);
    if (pos >= 0) cursor = pos;
  }
  const hits = [];
  seq.forEach((row, index) => {
    if (index <= cursor && hasSymbol(row, tex)) hits.push(row);
  });
  if (!hits.length) return { text: UNDEFINED };
  const last = hits[hits.length - 1];
  const onIt = Boolean(at && last.block === at.block && last.index === at.index);
  if (!onIt) return { text: last.text, shown: last.shown, section: last.section, here: false };
  const prior = hits.slice(0, -1).reverse().find((row) => explains(row, tex));
  if (prior) return { text: prior.text, shown: prior.shown, section: prior.section, here: false };
  return { text: last.text, shown: last.shown, section: last.section, here: true };
}

export function equationHover(blocks, blockId) {
  const list = blocks || [];
  const at = list.findIndex((block) => block.id === blockId);
  const prev = at > 0 ? list[at - 1] : null;
  if (!prev || prev.kind !== "p") return { texts: [] };
  const sents = prev.sents && prev.sents.length ? prev.sents : [prev.inlines || []];
  return {
    texts: sents.map((sent) => clean(textOf(sent))).filter(Boolean),
    shown: sents.map((sent) => showOf(sent).trim()).filter(Boolean),
  };
}

export function tableHover(blocks, blockId) {
  const list = blocks || [];
  const at = list.findIndex((block) => block.id === blockId);
  const table = at >= 0 ? list[at] : null;
  const caption = clean(textOf(table && table.caption));
  const captionShown = showOf(table && table.caption).trim();
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
  return { caption, captionShown, sentence: best ? best.text : "", sentenceShown: best ? best.shown : "" };
}
