// Catálogo de fallas, clasificación, registro saneado y el interruptor de diagnóstico.
// JS puro: `node --test` lo importa sin Next.

/** code → { demo, silent }. `silent`: el demo no muestra aviso. */
export const FAULTS = {
  "F-AUTH": { demo: "Could not reach the engine.", silent: false },
  "F-ORIGIN": { demo: "Could not reach the engine.", silent: false },
  "F-RATE": { demo: "The engine is busy. Try again in a few seconds.", silent: false },
  "F-SERVER": { demo: "The server failed. Try again.", silent: false },
  "F-TIMEOUT": { demo: "The engine took too long. It may be starting up; try again.", silent: false },
  "F-NETWORK": { demo: "No connection to the engine.", silent: false },
  "F-HTTP": { demo: "The server returned an error.", silent: false },
  "F-JSON": { demo: "The server reply could not be read.", silent: false },
  "F-NOREC": { demo: "This question is not in the local data.", silent: false },
  "F-RENDER": { demo: "This part could not be shown.", silent: false },
  "F-ASK": { demo: "Could not review your explanation just now. The excerpts are still below.", silent: false },
  "F-ASK-SLOW": { demo: "Still checking the citations. Send again if nothing appears.", silent: false },
  "F-NOTES": { demo: "", silent: true },
  "F-LABELS": { demo: "", silent: true },
  "F-MAP": { demo: "", silent: true },
  "F-NAMES": { demo: "", silent: true },
  "F-PHRASES": { demo: "", silent: true },
  "F-WARM": { demo: "", silent: true },
  "F-FIG": { demo: "", silent: true },
  "F-KATEX": { demo: "", silent: true },
  "F-STORAGE": { demo: "", silent: true },
};

const KIND_CODE = {
  auth: "F-AUTH",
  origin: "F-ORIGIN",
  rate: "F-RATE",
  server: "F-SERVER",
  timeout: "F-TIMEOUT",
  network: "F-NETWORK",
  http: "F-HTTP",
};

// Rutas de fondo: si fallan, la pantalla sigue sin ellas.
const ROUTE_CODE = {
  notes: "F-NOTES",
  labels: "F-LABELS",
  map: "F-MAP",
  "group-names": "F-NAMES",
  names: "F-NAMES",
  phrases: "F-PHRASES",
  warm: "F-WARM",
};

/** "/ask?x=1", "ask" o "http://h/ask" → "ask". */
export function routeName(route) {
  return String(route || "")
    .replace(/^[a-z]+:\/\/[^/]+/i, "")
    .split(/[?#]/)[0]
    .replace(/^\/+|\/+$/g, "");
}

/** Error (BackendError u otro) → código del catálogo. */
export function classify(err, route) {
  if (err && typeof err.code === "string" && FAULTS[err.code]) return err.code;
  const name = routeName(route ?? err?.route);
  const kind = err?.kind;
  const status = Number(err?.status) || 0;
  const msg = String(err?.message ?? (typeof err === "string" ? err : ""));
  if (ROUTE_CODE[name]) return ROUTE_CODE[name];
  if (name === "ask") {
    if (status === 502) return "F-ASK";
    if (kind === "timeout" || err?.name === "AbortError") return "F-ASK-SLOW";
  }
  if (msg.includes("consulta no grabada")) return "F-NOREC";
  if (err?.name === "SyntaxError" || /no es JSON/i.test(msg)) return "F-JSON";
  if (KIND_CODE[kind]) return KIND_CODE[kind];
  if (err?.name === "AbortError") return "F-TIMEOUT";
  if (err?.name === "TypeError" && /fetch|network|load failed/i.test(msg)) return "F-NETWORK";
  return "F-RENDER";
}

/** Texto `demo` de un código o de un error. Vacío si la falla es silenciosa. */
export function friendly(codeOrErr, route) {
  const code = typeof codeOrErr === "string" ? codeOrErr : classify(codeOrErr, route);
  return FAULTS[code]?.demo || "";
}

const demoToken = () => process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN || "";

/** Quita token, `k=…`, `Bearer …` y URLs. */
export function sanitize(text, token = demoToken()) {
  let s = String(text ?? "");
  if (token) s = s.split(token).join("•••");
  s = s.replace(/https?:\/\/[^\s"'<>]+/gi, "<url>");
  s = s.replace(/\bBearer\s+[^\s"',;]+/gi, "Bearer •••");
  s = s.replace(/(^|[^A-Za-z0-9_])k=[^&\s"',;]*/g, "$1k=•••");
  return s.length > 500 ? `${s.slice(0, 500)}…` : s;
}

const LIMIT = 100;
const ring = [];
const subs = new Set();

/** Registra una falla: ring buffer de 100 con el detalle saneado. */
export function reportFault({ code, route, kind, status, ms, detail, where } = {}) {
  const row = {
    at: Date.now(),
    code: FAULTS[code] ? code : "F-RENDER",
    route: sanitize(route || ""),
    kind: kind ? String(kind) : "",
    status: Number(status) || 0,
    ms: Number.isFinite(ms) ? Math.max(0, Math.round(ms)) : null,
    detail: sanitize(detail || ""),
    where: where ? String(where) : "",
  };
  ring.push(row);
  if (ring.length > LIMIT) ring.splice(0, ring.length - LIMIT);
  for (const fn of [...subs]) {
    try { fn(row); } catch { /* un suscriptor roto no detiene el registro */ }
  }
  return row;
}

/** `localStorage` o IndexedDB rechazó leer o escribir. */
export function storageFault(err, where) {
  return reportFault({ code: "F-STORAGE", where, detail: String(err?.message || err || "") });
}

export function faultLog() {
  return ring.slice();
}

export function clearFaults() {
  ring.length = 0;
}

export function subscribe(fn) {
  subs.add(fn);
  return () => { subs.delete(fn); };
}

function session() {
  try { return typeof sessionStorage === "undefined" ? null : sessionStorage; } catch { return null; }
}

/** `?debug=1` o `?dev=1` (se recuerda en la pestaña), `?debug=0` lo borra, o NEXT_PUBLIC_RRM_DEBUG=1.
 * Solo en efectos o handlers: en el export estático el servidor no tiene `location`. */
export function debugOn() {
  if (process.env.NEXT_PUBLIC_RRM_DEBUG === "1") return true;
  if (typeof location === "undefined") return false;
  let params;
  try { params = new URLSearchParams(location.search || ""); } catch { return false; }
  const ss = session();
  if (params.get("debug") === "0") {
    try { ss?.removeItem("rrm.debug"); } catch { /* sin memoria de pestaña */ }
    return false;
  }
  if (params.get("debug") === "1" || params.get("dev") === "1") {
    try { ss?.setItem("rrm.debug", "1"); } catch { /* sin memoria de pestaña */ }
    return true;
  }
  try { return ss?.getItem("rrm.debug") === "1"; } catch { return false; }
}
