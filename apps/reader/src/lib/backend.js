// Client for the live burst and reader. Plain JS so `node --test` can import it.
// NEXT_PUBLIC_* is inlined by the static export. Empty URLs keep the curated mock.

import { classify, reportFault } from "./faults.js";

export { friendly } from "./faults.js";

const BURST = process.env.NEXT_PUBLIC_BURST_URL || "";
const READER = process.env.NEXT_PUBLIC_READER_URL || "";
const TOKEN = process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN || "";

export function liveEnabled() {
  return Boolean(BURST) && Boolean(READER);
}

if (liveEnabled() && !TOKEN && process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") {
  throw new Error("NEXT_PUBLIC_RRM_DEMO_TOKEN is empty");
}

/** Una recarga que trae el stub no pisa el paper ya leído. */
export function keepOpened(prev, next) {
  if (!prev || !next || String(prev.corpusid) !== String(next.corpusid)) return next;
  const pb = Array.isArray(prev.blocks) ? prev.blocks.length : 0;
  const nb = Array.isArray(next.blocks) ? next.blocks.length : 0;
  if (pb > nb && prev.full && !next.full) return prev;
  return next;
}

export function paperKey(paper) {
  return typeof paper.corpusid === "number" ? String(paper.corpusid) : paper.arxivId;
}

export function figureUrl(id, name) {
  if (String(name).startsWith("/")) return name;
  if (!liveEnabled()) return `/papers/${id}/${name}`;
  return `${READER}/file?id=${id}&name=${encodeURIComponent(name)}&k=${TOKEN}`;
}

export function sourcePdfUrl(id) {
  return figureUrl(id, "source.pdf");
}

export function refText(x, xref) {
  const label = x.label || "";
  if (x.number != null) return String(label).startsWith("eq") ? `(${x.number})` : String(x.number);
  return (xref && xref[label]) || label;
}

export function eqTex(b) {
  return b.number != null ? `${b.tex}\\tag{${b.number}}` : b.tex;
}

const FILE_NAME = /^[A-Za-z0-9._-]{1,180}$/;

/** Names to try for a figure. `lstm.\\imgExt` is a macro the e-print never expanded. */
export function figureCandidates(name) {
  const raw = String(name || "");
  if (raw.startsWith("/")) return [raw];
  const out = [];
  const push = (n) => { if (FILE_NAME.test(n) && !out.includes(n)) out.push(n); };
  push(raw);
  const cleaned = raw.replace(/\\+imgExt\b/g, "").replace(/\\/g, "").replace(/\.$/, "");
  if (cleaned && cleaned !== raw) {
    if (/\.(png|jpe?g|gif|webp|pdf)$/i.test(cleaned)) push(cleaned);
    else for (const ext of [".png", ".jpg", ".jpeg", ".webp", ".gif"]) push(cleaned + ext);
  }
  return out;
}

const SI_UNITS = { minute: "min", second: "s", hour: "h", meter: "m", metre: "m", gram: "g", kilogram: "kg" };

function readBrace(s, i) {
  if (s[i] !== "{") return null;
  let d = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === "\\") { j += 1; continue; }
    if (s[j] === "{") d += 1;
    else if (s[j] === "}") {
      d -= 1;
      if (d === 0) return [s.slice(i + 1, j), j + 1];
    }
  }
  return null;
}

function stripOuterBrace(s) {
  const t = s.trim();
  if (!t.startsWith("{")) return t;
  const g = readBrace(t, 0);
  if (g && g[1] === t.length) return g[0].trim();
  return t;
}

/** `\mbox{\boldmath{$...$}}` is a bold symbol. Nested mboxes stay in math mode. */
function unwrapBoldMbox(s) {
  let out = "";
  for (let i = 0; i < s.length;) {
    if (s.startsWith("\\mbox", i) && !/[A-Za-z]/.test(s[i + 5] || "")) {
      let j = i + 5;
      while (s[j] === " ") j += 1;
      const g = s[j] === "{" ? readBrace(s, j) : null;
      if (g && g[0].trim().startsWith("\\boldmath")) {
        let inner = g[0].trim().replace(/^\\boldmath\s*/, "");
        inner = stripOuterBrace(inner);
        inner = inner.replace(/^\$(.*)\$$/s, "$1");
        inner = unwrapBoldMbox(inner);
        out += `\\mathbf{${inner}}`;
        i = g[1];
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

function unwrapNamed(s, name) {
  const mark = "\\" + name;
  let out = "";
  for (let i = 0; i < s.length;) {
    if (s.startsWith(mark, i) && !/[A-Za-z]/.test(s[i + mark.length] || "")) {
      let j = i + mark.length;
      while (s[j] === " ") j += 1;
      const g = s[j] === "{" ? readBrace(s, j) : null;
      if (g) {
        out += g[0];
        i = g[1];
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

/** `\resizebox{w}{h}{...}` is a size wrapper. Keep the third argument. */
function unwrapResizebox(s) {
  const mark = "\\resizebox";
  let out = "";
  for (let i = 0; i < s.length;) {
    if (s.startsWith(mark, i) && !/[A-Za-z]/.test(s[i + mark.length] || "")) {
      let j = i + mark.length;
      while (s[j] === " ") j += 1;
      const w = s[j] === "{" ? readBrace(s, j) : null;
      if (w) {
        j = w[1];
        while (s[j] === " ") j += 1;
        const h = s[j] === "{" ? readBrace(s, j) : null;
        if (h) {
          j = h[1];
          while (s[j] === " ") j += 1;
          const body = s[j] === "{" ? readBrace(s, j) : null;
          if (body) {
            let inner = body[0].trim();
            if (inner.startsWith("$") && inner.endsWith("$")) inner = inner.slice(1, -1).trim();
            out += inner;
            i = body[1];
            continue;
          }
        }
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

/** Render-time TeX. Do not rewrite the stored source. Keep in step with rrm/reader/katex.py. */
export function katexSource(tex) {
  let s = unwrapBoldMbox(String(tex ?? ""));
  s = unwrapResizebox(s);
  let prev;
  do { prev = s; s = unwrapNamed(s, "ensuremath"); } while (s !== prev);
  s = s.replace(/\\mbox(?![A-Za-z])/g, "\\text");
  // NeRF / Instant-NGP: \left -> \mathopen{}\mathclose\bgroup\originalleft
  s = s.replace(/(?:\\mathopen\{\}\s*\\mathclose(?![A-Za-z])\s*\\bgroup\s*)+/g, "");
  s = s.replace(/(?:\\aftergroup\s*\\egroup\s*)+/g, "");
  s = s.replace(/\\originalleft(?![A-Za-z])/g, "\\left");
  s = s.replace(/\\originalright(?![A-Za-z])/g, "\\right");
  s = s.replace(/\\mathopen(?![A-Za-z])\s*/g, "");
  s = s.replace(/\\mathclose(?![A-Za-z])\s*/g, "");
  s = s.replace(/\\nicefrac(?![A-Za-z])/g, "\\frac");
  s = s.replace(/\\num(?![A-Za-z])\s*\{([^{}]*)\}/g, "$1");
  s = s.replace(/\\SI(?![A-Za-z])\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (_, num, unit) => {
    const name = String(unit).replace(/^\\/, "");
    return `${num}\\,\\mathrm{${SI_UNITS[name] || name}}`;
  });
  s = s.replace(/\\partialm(?![A-Za-z])/g, "\\partial m");
  s = s.replace(/\\mathds(?![A-Za-z])/g, "\\mathbb");
  s = s.replace(/\\mathbbm(?![A-Za-z])\s*([0-9A-Za-z])/g, "\\mathbb{$1}");
  s = s.replace(/\\mathbbm(?![A-Za-z])/g, "\\mathbb");
  s = s.replace(/\\textrm(?![A-Za-z])/g, "\\text");
  s = s.replace(/\\boldmath\s*\{\$([^{}$]+)\$\}/g, "\\mathbf{$1}");
  s = s.replace(/\\boldmath(?![A-Za-z])\s*/g, "");
  s = s.replace(/\\[vh]space\s*\{[^{}]*\}/g, "");
  s = s.replace(/\\vskip\s*-?[0-9.]+\s*(?:pt|em|ex|mm|cm)?/g, "");
  s = s.replace(/\\Tilde(?![A-Za-z])/g, "\\tilde");
  s = s.replace(/\\Hat(?![A-Za-z])/g, "\\hat");
  s = s.replace(/\\Bar(?![A-Za-z])/g, "\\bar");
  s = s.replace(/\{([^{}\\]+)\\choose\s*\{([^{}]*)\}\}/g, "\\binom{$1}{$2}");
  s = s.replace(/\{([^{}\\]+)\\choose\s*([^{}\\]+)\}/g, "\\binom{$1}{$2}");
  s = s.replace(/\$([^$]+)\$/g, "\\text{$1}");
  return s;
}

const OUTER_ALIGN = /^\s*\\begin\{(aligned|align\*?|eqnarray\*?|gather\*?|flalign\*?|multline\*?|split|gathered|cases|array|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|Bmatrix|smallmatrix|subarray|dmath|equation\*?)\b/;

/** Display math KaTeX can parse. `&` outside an alignment environment is wrapped. */
export function displayTex(tex) {
  let s = katexSource(tex);
  // alignat's column count ({2}) used to stay in front of the formula ("2PE").
  s = s.replace(/^\{\d+\}\s*\n/, "");
  const tag = s.match(/\\tag\{[^{}]*\}\s*$/);
  let suffix = "";
  if (tag && tag.index > 0) {
    suffix = tag[0];
    s = s.slice(0, tag.index);
  }
  s = s.replace(/^\s*\\begin\{split\}/, "\\begin{aligned}").replace(/\\end\{split\}\s*$/, "\\end{aligned}");
  if (OUTER_ALIGN.test(s)) return s + suffix;
  if (s.includes("&") || /\\\\/.test(s)) return `\\begin{aligned}${s}\\end{aligned}${suffix}`;
  return s + suffix;
}

/** done / abstract_only / failed. `missing` is still in flight. */
export const SETTLED = new Set(["done", "abstract_only", "failed"]);

export function settled(status) {
  return SETTLED.has(status);
}

/** Error del backend con el motivo ya clasificado: kind = auth | origin | rate | server | timeout | network | http. */
export class BackendError extends Error {
  constructor(kind, status, detail = "") {
    super(detail || `${kind}${status ? ` ${status}` : ""}`);
    this.name = "BackendError";
    this.kind = kind;
    this.status = status;
    this.code = "";
  }
}

function kindOf(status) {
  return status === 401 ? "auth" : status === 403 ? "origin" : status === 429 ? "rate" : status >= 500 ? "server" : "http";
}

/** Texto para la persona. No lleva el token ni la URL. */
export function explain(err) {
  const msg = String(err?.message || "");
  if (msg.includes("consulta no grabada")) return "This question is not in the local data.";
  const k = err?.kind;
  if (k === "auth") {
    const why = String(err?.message || "");
    if (why === "missing") return "The server has no demo token (401). Start the app again with bash scripts/run.sh.";
    if (why === "empty" || why === "mismatch") return "This page and the server do not share a demo token (401). Stop the app and start it again with bash scripts/run.sh.";
    return "The server rejected the demo token (401). Stop the app and start it again with bash scripts/run.sh.";
  }
  if (k === "origin") return "The server does not accept this origin (403). Add it to the allowed origins.";
  if (k === "rate") return "The server is getting too many requests (429). Wait a few seconds and try again.";
  if (k === "server") {
    const detail = String(err?.message || "").trim();
    const base = `The server failed (${err.status}). Try again in a moment.`;
    if (!detail || detail === `server ${err.status}` || /https?:|bearer|token|key/i.test(detail)) return base;
    return `${base} ${detail}`;
  }
  if (k === "timeout") return "The server did not answer in time. It may be starting up; try again.";
  if (k === "network") return "Could not connect to the server.";
  if (k === "http") return `The server responded ${err.status}.`;
  return String(err?.message || err || "Unknown error");
}

// Un número en NEXT_PUBLIC_RRM_PANORAMA_TIMEOUT_MS (ms) cambia la espera del navegador.
function panoramaTimeout() {
  const raw = process.env.NEXT_PUBLIC_RRM_PANORAMA_TIMEOUT_MS;
  const n = Number(raw);
  if (raw && Number.isFinite(n) && n >= 1000 && n <= 120000) return n;
  return 45000;
}

export const PANORAMA_TIMEOUT_MS = panoramaTimeout();

// Tiempos de espera por ruta (ms). /burst puede tardar 100–131 s si el contenedor estaba dormido.
const TIMEOUT = { warm: 150000, burst: 150000, status: 20000, paper: 40000, panorama: PANORAMA_TIMEOUT_MS, crops: 20000, subtopics: 20000, prepare: 20000, labels: 8000, ask: 50000, names: 7500, notes: 90000, recorded: 8000 };
const RETRIES = { warm: 0, burst: 0, status: 2, paper: 1, panorama: 0, crops: 1, subtopics: 0, prepare: 0, labels: 0, ask: 0, names: 0, notes: 0, recorded: 0 };
const RETRYABLE = new Set(["timeout", "network", "rate", "server"]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const override = () => (typeof globalThis.__RRM_TIMEOUT_MS === "number" ? globalThis.__RRM_TIMEOUT_MS : null);

/** GET/HEAD carry the token in `k` and no custom header, so the browser skips the CORS preflight.
 * A preflight waits for the Modal container, and a cold /burst did not answer OPTIONS within 30s.
 * POST still sends X-RRM-Demo (application/json cannot be a simple request). */
function authed(url, method) {
  const m = String(method || "GET").toUpperCase();
  if (m === "GET" || m === "HEAD") {
    const join = url.includes("?") ? "&" : "?";
    return { url: `${url}${join}k=${encodeURIComponent(TOKEN)}`, headers: {} };
  }
  return { url, headers: { "X-RRM-Demo": TOKEN } };
}

const pathOf = (url) => String(url).replace(/^[a-z]+:\/\/[^/]+/i, "").split("?")[0];

/** Último intento fallido: código en `err.code` y una fila en el registro de fallas. */
function giveUp(err, url, t0) {
  const path = pathOf(url);
  err.code = classify(err, path);
  reportFault({ code: err.code, route: path, kind: err.kind, status: err.status, ms: Date.now() - t0, detail: err.message, where: "backend" });
  return err;
}

async function request(route, url, init = {}) {
  const retries = RETRIES[route];
  const auth = authed(url, init.method);
  const t0 = Date.now();
  for (let attempt = 0; ; attempt++) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), override() ?? TIMEOUT[route]);
    try {
      const res = await fetch(auth.url, { ...init, signal: ctl.signal, headers: { ...auth.headers, ...(init.headers || {}) } });
      if (!res.ok) {
        let detail = "";
        try {
          const body = await res.json();
          if (body && typeof body.error === "string") detail = body.error;
        } catch { /* cuerpo vacío o no JSON */ }
        throw new BackendError(kindOf(res.status), res.status, detail);
      }
      try { return await res.json(); } catch { throw new BackendError("http", res.status, "la respuesta no es JSON"); }
    } catch (e) {
      const err = e instanceof BackendError ? e : new BackendError(ctl.signal.aborted ? "timeout" : "network", 0);
      if (attempt >= retries || !RETRYABLE.has(err.kind)) throw giveUp(err, url, t0);
      await sleep((override() ? 5 : 400) * 2 ** attempt);
    } finally {
      clearTimeout(timer);
    }
  }
}

/** Datos curados del export estático (`public/papers/`). Misma URL que antes; la falla queda registrada. */
async function curated(url) {
  const t0 = Date.now();
  try {
    return await (await fetch(url)).json();
  } catch (e) {
    const kind = e?.name === "SyntaxError" ? "json" : "network";
    const code = classify(e?.name === "SyntaxError" ? e : { kind: "network" }, url);
    try { e.code = code; } catch { /* error congelado */ }
    reportFault({ code, route: url, kind, ms: Date.now() - t0, detail: e?.message, where: "curated" });
    throw e;
  }
}

export function curatedContent() {
  return curated("/papers/_content.json");
}

export function curatedPaper(id) {
  return curated(`/papers/${id}.json`);
}

export function warm(which = "burst") {
  const base = which === "reader" ? READER : BURST;
  return request("warm", `${base}/warm`);
}

/** Preguntas grabadas que el servidor offline acepta. Cualquier otra responde «consulta no grabada». */
export function parseRecorded(body) {
  const rows = body && Array.isArray(body.queries) ? body.queries : [];
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const q = String(row || "").trim();
    if (!q || seen.has(q)) continue;
    seen.add(q);
    out.push(q);
  }
  return out;
}

export function recordedQueries() {
  if (process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1" || !BURST) return Promise.resolve([]);
  return request("recorded", `${BURST}/`).then(parseRecorded, () => []);
}

export function burst(q) {
  return request("burst", `${BURST}/burst?q=${encodeURIComponent(q)}&n=10`);
}

export function mapLayout(q) {
  return request("burst", `${BURST}/map?q=${encodeURIComponent(q)}`);
}

export function status(ids, q) {
  const extra = q ? `&q=${encodeURIComponent(q)}` : "";
  return request("status", `${READER}/status?ids=${ids.join(",")}${extra}`);
}

/** front=true moves those ids ahead of the background top-10. The UI does not wait on the parse. */
export function prepare(ids, front = false) {
  return request("prepare", `${READER}/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, front: Boolean(front) }),
  });
}

export function paper(id, opts = {}) {
  const cites = opts.cites ? "&cites=1" : "";
  return request("paper", `${READER}/paper?id=${encodeURIComponent(id)}${cites}`);
}

export function groupNames(groups) {
  return request("names", `${BURST}/group-names`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groups }),
  });
}

/** Selecciones SIMULADAS del servidor: [{id, statement, selections: [{paper, quote}]}]. La compuerta sigue en la UI. */
export function panorama(question, ids) {
  return request("panorama", `${READER}/panorama`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, ids }),
  });
}

export function crops(id, pages = "0,1,2") {
  return request("crops", `${READER}/crops?id=${encodeURIComponent(id)}&pages=${encodeURIComponent(pages)}`);
}

export function subtopics(q) {
  return request("subtopics", `${BURST}/subtopics?q=${encodeURIComponent(q)}`);
}

export function labels(q) {
  return request("labels", `${BURST}/labels?q=${encodeURIComponent(q)}`);
}

export function preparePhrases(id) {
  return request("ask", `${READER}/phrases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

export function fetchNotes(id) {
  if (!READER) {
    return Promise.resolve({ notes: [], artifacts: [], usage: { model: "", license: "", cost_usd: 0 } });
  }
  return request("notes", `${READER}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

/** RRM-100: `section` (id del encabezado) revisa contra esa sección del paper abierto. */
export function ask(ids, text, stage, focus, section) {
  if (!READER) {
    return Promise.resolve({
      extracts: [], papers: 0, line: "", empty: false, matched: 0, parts: {},
      note: "Sin retroalimentación: no hay clave.", store: { ready: 0, total: 0 },
    });
  }
  return request("ask", `${READER}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, text, stage: stage || "", focus: focus || "", ...(section ? { section } : {}) }),
  });
}
