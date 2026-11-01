// Scan: abstract, figuras, tablas y la sección de conclusión.

function textOf(nodes) {
  return (nodes || []).map((node) => {
    if (!node || typeof node !== "object") return "";
    if (node.t === "text") return node.v || "";
    if (Array.isArray(node.c)) return textOf(node.c);
    return "";
  }).join(" ");
}

export function conclusionTitle(text) {
  return /^\s*(?:\d+(?:\.\d+)*\.?\s+)?(conclusions?|concluding remarks|conclusiones|conclusión|discussion|summary|resumen)\b/i.test(text || "");
}

export function hasConclusion(blocks) {
  return (blocks || []).some((block) => block.kind === "h" && conclusionTitle(textOf(block.inlines)));
}

export function scanIds(blocks) {
  const list = blocks || [];
  const ids = new Set();
  let start = -1;
  let level = 1;
  list.forEach((block, index) => {
    if (block.kind === "h" && conclusionTitle(textOf(block.inlines))) {
      start = index;
      level = block.level || 1;
    }
  });
  let inside = false;
  list.forEach((block, index) => {
    if (block.abs || block.kind === "fig" || block.kind === "table") ids.add(block.id);
    if (start < 0) return;
    if (index === start) {
      inside = true;
      ids.add(block.id);
      return;
    }
    if (!inside) return;
    if (block.kind === "h" && (block.level || 1) <= level) {
      inside = false;
      return;
    }
    ids.add(block.id);
  });
  return ids;
}
