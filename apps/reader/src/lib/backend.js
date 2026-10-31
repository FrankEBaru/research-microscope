// Client for the live burst and reader. Plain JS so `node --test` can import it.
// NEXT_PUBLIC_* is inlined by the static export. Empty URLs keep the curated mock.

const BURST = process.env.NEXT_PUBLIC_BURST_URL || "";
const READER = process.env.NEXT_PUBLIC_READER_URL || "";
const TOKEN = process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN || "";

export function liveEnabled() {
  return Boolean(BURST) && Boolean(READER);
}

if (liveEnabled() && !TOKEN && process.env.NEXT_PUBLIC_RRM_OFFLINE !== "1") {
  throw new Error("NEXT_PUBLIC_RRM_DEMO_TOKEN is empty");
}

export function paperKey(paper) {
  return typeof paper.corpusid === "number" ? String(paper.corpusid) : paper.arxivId;
}

export function figureUrl(id, name) {
  if (String(name).startsWith("/")) return name;
  if (!liveEnabled()) return `/papers/${id}/${name}`;
  return `${READER}/file?id=${id}&name=${encodeURIComponent(name)}&k=${TOKEN}`;
}

export function refText(x, xref) {
  const label = x.label || "";
  if (x.number != null) return String(label).startsWith("eq") ? `(${x.number})` : String(x.number);
  return (xref && xref[label]) || label;
}

export function eqTex(b) {
  return b.number != null ? `${b.tex}\\tag{${b.number}}` : b.tex;
}

const SI_UNITS = { minute: "min", second: "s", hour: "h", meter: "m", metre: "m", gram: "g", kilogram: "kg" };

/** Render-time TeX. Do not rewrite the stored source. Keep in step with rrm/reader/katex.py. */
export function katexSource(tex) {
  let s = String(tex ?? "");
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
  return s;
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
  }
}

function kindOf(status) {
  return status === 401 ? "auth" : status === 403 ? "origin" : status === 429 ? "rate" : status >= 500 ? "server" : "http";
}

/** Texto para la persona. No lleva el token ni la URL. */
export function explain(err) {
  const msg = String(err?.message || "");
  if (msg.includes("consulta no grabada")) return "consulta no grabada";
  const k = err?.kind;
  if (k === "auth") return "El servidor rechazó el token de la demo (401). Revisa NEXT_PUBLIC_RRM_DEMO_TOKEN.";
  if (k === "origin") return "El servidor no acepta este origen (403). Hay que agregarlo a la lista de orígenes permitidos.";
  if (k === "rate") return "El servidor está recibiendo demasiadas peticiones (429). Espera unos segundos y vuelve a intentar.";
  if (k === "server") return `El servidor falló (${err.status}). Vuelve a intentar en un momento.`;
  if (k === "timeout") return "El servidor no respondió a tiempo. Puede estar arrancando; vuelve a intentar.";
  if (k === "network") return "No se pudo conectar con el servidor.";
  if (k === "http") return `El servidor respondió ${err.status}.`;
  return String(err?.message || err || "Error desconocido");
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
const TIMEOUT = { warm: 150000, burst: 150000, status: 20000, paper: 40000, panorama: PANORAMA_TIMEOUT_MS, crops: 20000, subtopics: 20000, prepare: 20000 };
const RETRIES = { warm: 0, burst: 0, status: 2, paper: 1, panorama: 0, crops: 1, subtopics: 0, prepare: 0 };
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

async function request(route, url, init = {}) {
  const retries = RETRIES[route];
  const auth = authed(url, init.method);
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
      if (attempt >= retries || !RETRYABLE.has(err.kind)) throw err;
      await sleep((override() ? 5 : 400) * 2 ** attempt);
    } finally {
      clearTimeout(timer);
    }
  }
}

export function warm(which = "burst") {
  const base = which === "reader" ? READER : BURST;
  return request("warm", `${base}/warm`);
}

export function burst(q) {
  return request("burst", `${BURST}/burst?q=${encodeURIComponent(q)}&n=10`);
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

export function paper(id) {
  return request("paper", `${READER}/paper?id=${encodeURIComponent(id)}`);
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
