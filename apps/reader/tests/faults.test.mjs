// RRM-64: catálogo de fallas, saneado, registro, interruptor de diagnóstico y la puerta única al backend.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN = "tok-de-prueba-123";
const F = await import("../src/lib/faults.js");
const { BackendError } = await import("../src/lib/backend.js");

test("classify: cada kind de BackendError tiene su código", () => {
  const cases = { auth: "F-AUTH", origin: "F-ORIGIN", rate: "F-RATE", server: "F-SERVER", timeout: "F-TIMEOUT", network: "F-NETWORK", http: "F-HTTP" };
  for (const [kind, code] of Object.entries(cases)) {
    assert.equal(F.classify(new BackendError(kind, kind === "server" ? 500 : 0), "/burst"), code, kind);
  }
});

test("classify: JSON ilegible, consulta no grabada, /ask y rutas de fondo", () => {
  assert.equal(F.classify(new BackendError("http", 200, "la respuesta no es JSON"), "/burst"), "F-JSON");
  assert.equal(F.classify(new SyntaxError("Unexpected token <"), "/papers/_content.json"), "F-JSON");
  assert.equal(F.classify(new BackendError("http", 404, "consulta no grabada"), "/burst"), "F-NOREC");
  assert.equal(F.classify(new BackendError("server", 502), "/ask"), "F-ASK");
  assert.equal(F.classify(new BackendError("server", 502), "ask"), "F-ASK");
  assert.equal(F.classify(new BackendError("timeout", 0), "/ask"), "F-ASK-SLOW");
  assert.equal(F.classify(new BackendError("server", 500), "/ask"), "F-SERVER");
  const silent = { "/notes": "F-NOTES", "/labels": "F-LABELS", "/map": "F-MAP", "/group-names": "F-NAMES", "/phrases": "F-PHRASES", "/warm": "F-WARM" };
  for (const [route, code] of Object.entries(silent)) {
    assert.equal(F.classify(new BackendError("server", 500), route), code, route);
    assert.equal(F.FAULTS[code].silent, true, code);
  }
  assert.equal(F.classify(new BackendError("rate", 429), "http://b.test/labels?q=x"), "F-LABELS");
  const tagged = new BackendError("server", 500);
  tagged.code = "F-SERVER";
  assert.equal(F.classify(tagged, "/notes"), "F-SERVER", "un código ya puesto no se reclasifica");
});

test("catálogo: cada código tiene demo o es silencioso", () => {
  for (const [code, row] of Object.entries(F.FAULTS)) {
    assert.equal(typeof row.silent, "boolean", code);
    if (!row.silent) assert.ok(row.demo.length > 0, code);
  }
});

test("sanitize: sin token, sin URL, sin k= ni Bearer", () => {
  const raw = "falló http://r.test/paper?id=1&k=tok-de-prueba-123 con Bearer abc.def y k=otro y tok-de-prueba-123 suelto";
  const out = F.sanitize(raw);
  assert.ok(!out.includes("tok-de-prueba-123"), out);
  assert.ok(!out.includes("r.test"), out);
  assert.ok(!out.includes("abc.def"), out);
  assert.ok(!out.includes("k=otro"), out);
  assert.match(out, /Bearer •••/);
  assert.match(out, /k=•••/);
  assert.equal(F.sanitize("checkpoint=3 sin clave"), "checkpoint=3 sin clave");
});

test("reportFault: ring buffer de 100, saneado y suscripción", () => {
  F.clearFaults();
  const seen = [];
  const off = F.subscribe((row) => seen.push(row.code));
  for (let i = 0; i < 130; i++) F.reportFault({ code: "F-SERVER", route: "/burst", kind: "server", status: 500, ms: i, detail: `n=${i}` });
  const log = F.faultLog();
  assert.equal(log.length, 100);
  assert.equal(log[0].detail, "n=30");
  assert.equal(log[99].detail, "n=129");
  assert.equal(seen.length, 130);
  off();
  const row = F.reportFault({ code: "F-NO-EXISTE", route: "https://x.test/burst?k=tok-de-prueba-123", detail: "https://x.test/a?k=tok-de-prueba-123" });
  assert.equal(seen.length, 130, "off() quita la suscripción");
  assert.equal(row.code, "F-RENDER");
  assert.ok(!JSON.stringify(row).includes("tok-de-prueba-123"));
  assert.ok(!JSON.stringify(row).includes("x.test"));
  F.clearFaults();
  assert.equal(F.faultLog().length, 0);
});

test("friendly: texto demo por código o por error", () => {
  assert.equal(F.friendly("F-SERVER"), "The server failed. Try again.");
  assert.equal(F.friendly(new BackendError("rate", 429), "/burst"), "The engine is busy. Try again in a few seconds.");
  assert.equal(F.friendly(new BackendError("http", 404, "consulta no grabada")), "This question is not in the local data.");
  assert.equal(F.friendly("F-NOTES"), "");
});

test("debugOn: ?debug=1, ?dev=1, ?debug=0 y la variable de entorno", () => {
  const store = new Map();
  globalThis.sessionStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
  try {
    delete process.env.NEXT_PUBLIC_RRM_DEBUG;
    delete globalThis.location;
    assert.equal(F.debugOn(), false, "sin location (export estático) es falso");
    globalThis.location = { search: "" };
    assert.equal(F.debugOn(), false);
    globalThis.location = { search: "?debug=1" };
    assert.equal(F.debugOn(), true);
    globalThis.location = { search: "" };
    assert.equal(F.debugOn(), true, "se recuerda en la pestaña");
    globalThis.location = { search: "?debug=0" };
    assert.equal(F.debugOn(), false);
    globalThis.location = { search: "" };
    assert.equal(F.debugOn(), false, "?debug=0 lo borra");
    globalThis.location = { search: "?dev=1" };
    assert.equal(F.debugOn(), true);
    assert.equal(store.get("rrm.debug"), "1");
    store.clear();
    globalThis.location = { search: "" };
    process.env.NEXT_PUBLIC_RRM_DEBUG = "1";
    assert.equal(F.debugOn(), true);
  } finally {
    delete process.env.NEXT_PUBLIC_RRM_DEBUG;
    delete globalThis.location;
    delete globalThis.sessionStorage;
  }
});

test("la puerta: el último intento fallido reporta y pone err.code", async () => {
  F.clearFaults();
  const realFetch = globalThis.fetch;
  globalThis.__RRM_TIMEOUT_MS = 50;
  globalThis.fetch = async () => new Response(JSON.stringify({ error: "boom" }), { status: 500 });
  try {
    const { status } = await import("../src/lib/backend.js");
    const err = await status([1]).then(() => null, (e) => e);
    assert.ok(err, "status debe fallar");
    assert.equal(err.code, "F-SERVER");
    const log = F.faultLog();
    assert.equal(log.length, 1, "un solo reporte tras los reintentos");
    assert.equal(log[0].code, "F-SERVER");
    assert.equal(log[0].route, "/status");
    assert.equal(log[0].status, 500);
    assert.equal(typeof log[0].ms, "number");
  } finally {
    globalThis.fetch = realFetch;
    delete globalThis.__RRM_TIMEOUT_MS;
    F.clearFaults();
  }
});

test("ningún fetch( directo en src/components", () => {
  const root = fileURLToPath(new URL("../src/components/", import.meta.url));
  const walk = (dir) => readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
  const hits = walk(root)
    .filter((path) => /\.(tsx?|jsx?|mjs)$/.test(path))
    .filter((path) => /(^|[^A-Za-z0-9_.])fetch\(/.test(readFileSync(path, "utf8")));
  assert.deepEqual(hits, []);
});
