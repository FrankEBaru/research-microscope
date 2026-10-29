// «Convergencia»: cuántos de los papers leídos tienen una frase que respalda un enunciado. Es una CUENTA, no la
// probabilidad de un modelo. Con pocos papers el intervalo es ancho y se muestra tal cual (Wilson, 95%).
export function wilson(k, n, z = 1.96) {
  if (n <= 0) return { p: 0, lo: 0, hi: 1 };
  const p = k / n, z2 = z * z, d = 1 + z2 / n;
  const c = (p + z2 / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / d;
  return { p, lo: Math.max(0, c - h), hi: Math.min(1, c + h) };
}

/** Cuenta por enunciado: k = papers distintos con al menos una frase; n = papers leídos. */
export function convergence(claim, nRead) {
  const k = new Set((claim.evidence || []).map((e) => e.paper)).size;
  return { k, n: nRead, ...wilson(k, nRead) };
}
