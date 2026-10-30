// Cómputo del instrumento "por qué se divide por √d_k" (Attention Is All You Need, §3.2.1, nota 1).
// Supuesto del paper: componentes de q y k independientes, media 0, varianza 1.
// El paper no fija la distribución: aquí se usa normal estándar (escalada por σ² si se cambia el supuesto).
// Módulo puro (sin DOM) para poder probarlo con `node --test`.

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function makeNormal(rand) {
  let spare = null;
  return function () {
    if (spare !== null) {
      const s = spare;
      spare = null;
      return s;
    }
    let u = 0;
    while (u === 0) u = rand();
    const v = rand();
    const r = Math.sqrt(-2 * Math.log(u));
    spare = r * Math.sin(2 * Math.PI * v);
    return r * Math.cos(2 * Math.PI * v);
  };
}

/** Simula n productos punto q·k con componentes ~ N(0, sigma2) independientes. */
export function simulate({ dk, sigma2 = 1, n = 4000, seed = 1 }) {
  const normal = makeNormal(mulberry32(seed));
  const sd = Math.sqrt(sigma2);
  const dots = new Float64Array(n);
  for (let s = 0; s < n; s++) {
    let acc = 0;
    for (let i = 0; i < dk; i++) acc += sd * normal() * (sd * normal());
    dots[s] = acc;
  }
  return dots;
}

export function meanVar(xs) {
  const n = xs.length;
  let m = 0;
  for (let i = 0; i < n; i++) m += xs[i];
  m /= n;
  let v = 0;
  for (let i = 0; i < n; i++) v += (xs[i] - m) * (xs[i] - m);
  return { mean: m, variance: v / (n - 1) };
}

export function scaled(xs, dk) {
  const f = 1 / Math.sqrt(dk);
  return Float64Array.from(xs, (x) => x * f);
}

export function histogram(xs, bins, lo, hi) {
  const h = new Array(bins).fill(0);
  const w = (hi - lo) / bins;
  for (let i = 0; i < xs.length; i++) {
    const b = Math.floor((xs[i] - lo) / w);
    if (b >= 0 && b < bins) h[b]++;
  }
  return h;
}

export function softmax(xs) {
  let m = -Infinity;
  for (const x of xs) if (x > m) m = x;
  const e = Array.from(xs, (x) => Math.exp(x - m));
  const z = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / z);
}

/** Peso máximo medio de softmax sobre `trials` conjuntos de `k` logits tomados de `dots`. */
export function meanMaxWeight(dots, k = 8, trials = 200, seed = 7) {
  const rand = mulberry32(seed);
  let acc = 0;
  for (let t = 0; t < trials; t++) {
    const logits = [];
    for (let j = 0; j < k; j++) logits.push(dots[Math.floor(rand() * dots.length)]);
    acc += Math.max(...softmax(logits));
  }
  return acc / trials;
}

/** Teoría: Var(q·k) = d_k · σ⁴ (componentes independientes, media 0, varianza σ² cada uno). */
export function theoreticalVar(dk, sigma2 = 1) {
  return dk * sigma2 * sigma2;
}
