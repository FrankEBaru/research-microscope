// Lógica del compañero de lectura (RRM-11). Módulo puro y SIN persistencia: los conteos viven solo en memoria,
// no se guardan en el navegador ni se envían a ningún lado; al recargar o cambiar de paper empiezan de cero.
//
// Una «señal» es una clave (p. ej. "sym:dk" = el lector pasó por el símbolo d_k). Cuando la misma señal se repite
// `threshold` veces dentro de la ventana, el tracker devuelve esa clave UNA vez para ofrecer ayuda. Nunca interrumpe:
// respeta un enfriamiento entre ofertas y no repite una oferta ya descartada o aceptada.

export function createTracker({ threshold = 3, windowMs = 90_000, cooldownMs = 45_000, now = () => Date.now() } = {}) {
  let hits = new Map();       // clave -> instantes (ms) de las señales recientes
  const done = new Set();     // claves ya ofrecidas (aceptadas o descartadas): no se repiten
  let lastOffer = -Infinity;
  return {
    /** Registra una señal. Devuelve la clave a ofrecer o null. */
    track(key) {
      const t = now();
      const arr = (hits.get(key) || []).filter((x) => t - x <= windowMs);
      arr.push(t); hits.set(key, arr);
      if (done.has(key) || arr.length < threshold || t - lastOffer < cooldownMs) return null;
      done.add(key); lastOffer = t; hits.delete(key);
      return key;
    },
    /** Oferta inmediata por permanencia (p. ej. una ecuación quieta en pantalla): mismas reglas de enfriamiento y de no repetir. */
    offer(key) {
      const t = now();
      if (done.has(key) || t - lastOffer < cooldownMs) return null;
      done.add(key); lastOffer = t;
      return key;
    },
    /** Olvida todo (cambio de paper o apagado). */
    reset() { hits = new Map(); done.clear(); lastOffer = -Infinity; },
    /** Para pruebas: cuántas señales recientes hay por clave. */
    pending() { return new Map([...hits].map(([k, v]) => [k, v.length])); },
  };
}
