// RRM-95. Live papers have no curated symbol list, so pick the recurring
// symbols of the paper and give each a stable color from the six --sym-* tokens.
// Stable: the slot comes from a hash of the symbol, so d_k keeps its color
// across papers unless two symbols of the same paper collide.

const SLOTS = 6;
const ATOM = /^(?:[A-Za-z]|\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|tau|phi|psi|omega|Sigma|Phi|Omega))(?:_(?:[A-Za-z0-9]|\{(?:[A-Za-z0-9]+|\\(?:text|mathrm)\{[A-Za-z]+\})\}))?$/;

function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

/** d_{k} → d_k, so both spellings are one symbol. */
export function symKey(tex) {
  return String(tex || "").replace(/\s+/g, "").replace(/_\{([A-Za-z0-9])\}/g, "_$1");
}

function variants(key) {
  const out = new Set([key]);
  const m = /^(.+)_([A-Za-z0-9])$/.exec(key);
  if (m) out.add(`${m[1]}_{${m[2]}}`);
  return [...out];
}

function inCommand(hay, at) {
  let j = at - 1;
  while (j >= 0 && /[A-Za-z]/.test(hay[j])) j--;
  return j >= 0 && hay[j] === "\\" && j < at - 0;
}

function count(hay, needle) {
  let n = 0;
  let at = hay.indexOf(needle);
  const single = needle.length === 1;
  while (at >= 0) {
    const prev = hay[at - 1] || "";
    const next = hay[at + needle.length] || "";
    const cmd = prev === "\\" || (/[A-Za-z]/.test(prev) && inCommand(hay, at));
    const glued = single && (next === "_" || (/[a-z]/.test(prev) && /[a-z]/.test(next)));
    if (!cmd && !glued && prev !== "^" && prev !== "_") n++;
    at = hay.indexOf(needle, at + needle.length);
  }
  return n;
}

const WORDS = /\\(?:mathrm|text|operatorname|textbf|mathbf|textit|mathit)\{[^{}]*\}/g;

function mathOf(blocks) {
  const inline = [];
  const all = [];
  const walk = (list) => (list || []).forEach((x) => {
    if (!x || typeof x !== "object") return;
    if (x.t === "math") { inline.push(x.v); all.push(x.v); }
    if (Array.isArray(x.c)) walk(x.c);
    if (Array.isArray(x.blocks)) x.blocks.forEach((b) => walk(b.inlines));
  });
  for (const b of blocks || []) {
    walk(b.inlines);
    if (b.kind === "eq" && b.tex) all.push(String(b.tex));
  }
  const raw = all.map((t) => String(t).replace(/\s+/g, "")).join(" ¶ ");
  return { inline, all: raw, bare: raw.replace(WORDS, "□") };
}

/** Up to six symbols that recur (≥3 times; a bare lowercase letter, often an index, needs ≥8). */
export function autoSyms(blocks, max = SLOTS) {
  const { inline, all, bare: plain } = mathOf(blocks);
  const cands = new Map();
  for (const tex of inline) {
    const key = symKey(tex);
    if (!ATOM.test(key) || cands.has(key)) continue;
    const single = key.length === 1;
    const n = variants(key).reduce((sum, v) => sum + count(single ? plain : all, v), 0);
    const lower = /^[a-z]$/.test(key);
    // Indices (i, n, k…) recur a lot but say little; they rank below named symbols.
    if (n >= (lower ? 8 : 3)) cands.set(key, lower ? n * 0.3 : n);
  }
  const picked = [...cands.entries()]
    .sort((a, b) => b[1] - a[1] || (b[0].length - a[0].length) || a[0].localeCompare(b[0]))
    .slice(0, max);
  const used = new Set();
  const out = [];
  for (const [key] of picked) {
    let slot = hash(key) % SLOTS;
    for (let i = 0; i < SLOTS && used.has(slot); i++) slot = (slot + 1) % SLOTS;
    used.add(slot);
    for (const latex of variants(key)) out.push({ id: `auto-${slot + 1}`, latex, name: key, color: "", cls: `symc-${slot + 1}` });
  }
  return out;
}
