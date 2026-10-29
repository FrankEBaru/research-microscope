// Adaptador de Muse (Meta) para el Panorama. HOY: modo SIMULADO (sin llamadas; el navegador nunca habla con Meta).
// Contrato futuro (lo llamaría el backend con permiso de Franklin, no la UI): Muse Spark recibe el texto completo de
// cada paper y devuelve SOLO selecciones: [{ paper, quote }] = frases que ya existen en el paper, agrupadas por enunciado.
// `validateSelections` es la compuerta: una frase que no exista exactamente una vez en su paper se rechaza.

export const museMode = () => "simulado";

export const text = (inls) => (inls || []).map((x) => x.t === "text" ? x.v : x.t === "math" ? `$${x.v}$` : x.t === "cite" || x.t === "note" ? "" : Array.isArray(x.c) ? text(x.c) : x.v || "").join("");
export const blockText = (b) => (b.kind === "p" || b.kind === "h" ? text(b.inlines) : b.kind === "eq" ? `$${b.tex}$` : b.kind === "list" ? (b.items || []).map(text).join(" ") : text(b.caption)).replace(/\s+/g, " ").trim();

/** @returns {{ok: {paper: string, quote: string, blockId: string}[], rejected: {paper: string, quote: string, reason: string}[]}} */
export function validateSelections(papers, selections) {
  const ok = [], rejected = [];
  for (const s of selections) {
    const p = papers[s.paper];
    if (!p) { rejected.push({ ...s, reason: "paper desconocido" }); continue; }
    const q = s.quote.replace(/\s+/g, " ").trim();
    let hits = (p.blocks || []).filter((b) => q && blockText(b).includes(q));
    if (hits.length > 1 && hits.filter((b) => b.abs).length === 1) hits = hits.filter((b) => b.abs); // frase del abstract que reaparece
    if (hits.length === 1) ok.push({ paper: s.paper, quote: q, blockId: hits[0].id });
    else rejected.push({ ...s, reason: hits.length === 0 ? "la frase no existe en el paper" : `aparece ${hits.length} veces` });
  }
  return { ok, rejected };
}

/** Modo simulado: devuelve el Panorama curado (ya validado al compilar). */
export function proposeClaims(content, questionId) {
  return (content.panorama && content.panorama[questionId]) || null;
}
