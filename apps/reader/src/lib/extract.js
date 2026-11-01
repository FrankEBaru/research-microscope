// Extractos de la caja: quita restos de LaTeX que el lector no debería ver (RRM-47).

/** «Table tab:op_complexities», «Table~tab:x», «[cite]», «\cite{..}» → texto legible. Deja $…$ para <Rich>. */
export function cleanExtract(text) {
  return String(text || "")
    .replace(/\\(?:cite[pt]?|ref|eqref|autoref|label)\{[^}]*\}/g, "")
    .replace(/~?\b(?:tab|fig|sec|eq|app|alg):[\w.:-]+/g, "")
    .replace(/\[(?:cite|ref|\?)\]/gi, "")
    .replace(/~/g, " ")
    .replace(/\(\s*\)/g, "")
    .replace(/\s+([,.;:)])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Estado honesto del almacén de frases. `done`: ya no va a cambiar en esta visita. */
export function storeLine(store, done) {
  const ready = Number(store?.ready || 0);
  const total = Number(store?.total || 0);
  if (!total) return "";
  if (ready >= total) return `Frases listas de los ${total} papers.`;
  const rest = total - ready;
  return done
    ? `Frases listas de ${ready} de ${total} papers. ${rest === 1 ? "El otro no tiene" : `Los otros ${rest} no tienen`} texto disponible por ahora.`
    : `Preparando frases: ${ready} de ${total} papers…`;
}

/** RRM-51: a quote that starts mid-sentence gets «…», never a forced capital. NeRF, word2vec stay. */
export function markMidStart(text) {
  const value = String(text || "");
  if (process.env.NEXT_PUBLIC_RRM_CASE === "raw") return value;
  const m = value.match(/^\s*(\S+)/);
  if (!m) return value;
  const word = m[1];
  const first = word.charAt(0);
  if (first.toLowerCase() === first.toUpperCase() || first !== first.toLowerCase()) return value;
  if (/\d/.test(word) || /\p{Lu}/u.test(word.slice(1))) return value;
  return `…${value.trimStart()}`;
}
