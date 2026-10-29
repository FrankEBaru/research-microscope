// Panorama con papers del modo en vivo. Puro y sin red: el paso de Muse Spark lo hará el backend (con permiso de Franklin)
// y devolverá solo selecciones; aquí se decide QUÉ papers cuentan como «leídos» y se pasa todo por la compuerta.
import { validateSelections } from "./muse.js";

/** done → texto completo; abstract_only → solo abstract (cuenta, pero se rotula); failed → no se pudo leer; el resto → pendiente. */
export function readState(status) {
  return status === "done" ? "full" : status === "abstract_only" ? "abstract" : status === "failed" ? "failed" : "pending";
}

/** Cuenta cuántos papers de la ráfaga se leyeron. `n` (los leídos) es el denominador de la convergencia; fallidos y pendientes NO entran. */
export function coverage(ids, states) {
  const c = { full: 0, abstract: 0, failed: 0, pending: 0, total: ids.length };
  for (const id of ids) c[readState(states[id]?.status)]++;
  return { ...c, n: c.full + c.abstract };
}

/**
 * claims: [{ id, statement, selections: [{ paper, quote }] }] (lo que devolvería el backend).
 * docs: { [id]: documento del paper con `blocks` } de los papers ya leídos.
 * Devuelve la misma forma que el Panorama curado (evidence con anchor.blockId) + lo rechazado, para mostrarlo.
 */
export function buildPanorama(claims, docs, states) {
  const readable = (id) => ["full", "abstract"].includes(readState(states[id]?.status)) && docs[id];
  const rejected = [];
  const out = claims.map((c) => {
    const eligible = [], skipped = [];
    for (const s of c.selections || []) (readable(s.paper) ? eligible : skipped).push(s);
    for (const s of skipped) rejected.push({ ...s, claim: c.id, reason: "paper no leído (fallido, pendiente o sin texto)" });
    const v = validateSelections(docs, eligible);
    for (const r of v.rejected) rejected.push({ ...r, claim: c.id });
    return { id: c.id, statement: c.statement, evidence: v.ok.map((o) => ({ paper: o.paper, quote: o.quote, anchor: { blockId: o.blockId } })) };
  });
  return { claims: out, rejected };
}
