// Red del cliente: tiempos de espera, reintentos acotados y mensajes por tipo de error. fetch simulado; sin red.
process.env.NEXT_PUBLIC_BURST_URL = "https://burst.example";
process.env.NEXT_PUBLIC_READER_URL = "https://reader.example";
process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN = "tok-secreto";

import test, { afterEach } from "node:test";
import assert from "node:assert/strict";

const m = await import("../src/lib/backend.js");
const realFetch = globalThis.fetch;
let calls;
const reply = (status, body = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const script = (...steps) => { calls = []; globalThis.fetch = async (url, init) => { calls.push({ url, init }); const s = steps[Math.min(calls.length - 1, steps.length - 1)]; return typeof s === "function" ? s(init) : s; }; };
const hang = (init) => new Promise((_, rej) => init.signal.addEventListener("abort", () => rej(new DOMException("abort", "AbortError"))));
afterEach(() => { globalThis.fetch = realFetch; delete globalThis.__RRM_TIMEOUT_MS; });

test("401 no se reintenta y el mensaje no trae token ni URL", async () => {
  script(reply(401));
  const err = await m.status([1]).catch((e) => e);
  assert.equal(err.kind, "auth"); assert.equal(calls.length, 1);
  const msg = m.explain(err); assert.match(msg, /token de la demo/); assert.ok(!msg.includes("tok-secreto") && !msg.includes("reader.example"));
});

test("503 en /status se reintenta y luego responde", async () => {
  script(reply(503), reply(200, { papers: [{ id: 1, status: "done" }] }));
  assert.deepEqual((await m.status([1])).papers[0].status, "done"); assert.equal(calls.length, 2);
});

test("429 persistente: tres intentos y mensaje de espera", async () => {
  script(reply(429));
  const err = await m.status([1]).catch((e) => e);
  assert.equal(calls.length, 3); assert.equal(err.kind, "rate"); assert.match(m.explain(err), /demasiadas peticiones/);
});

test("un paper que no responde corta por tiempo y no cuelga", async () => {
  globalThis.__RRM_TIMEOUT_MS = 30; script(hang);
  const t0 = Date.now(); const err = await m.paper("9").catch((e) => e);
  assert.equal(err.kind, "timeout"); assert.equal(calls.length, 2); assert.ok(Date.now() - t0 < 2000); assert.match(m.explain(err), /no respondió a tiempo/);
});

test("burst no se reintenta (arranque en frío) y 5xx se explica", async () => {
  script(reply(500)); const err = await m.burst("q").catch((e) => e);
  assert.equal(calls.length, 1); assert.equal(err.kind, "server"); assert.match(m.explain(err), /falló \(500\)/);
  globalThis.__RRM_TIMEOUT_MS = 30; script(hang); const slow = await m.burst("q").catch((e) => e);
  assert.equal(slow.kind, "timeout"); assert.equal(calls.length, 1);
});

test("sin conexión: kind network", async () => {
  script(() => { throw new TypeError("fetch failed"); });
  const err = await m.paper("1").catch((e) => e); assert.equal(err.kind, "network"); assert.match(m.explain(err), /No se pudo conectar/);
});

test("panorama: POST con JSON y token, sin reintento", async () => {
  script(reply(200, [{ id: "t0", statement: "s", selections: [] }]));
  assert.equal((await m.panorama("q", ["1", "2"]))[0].id, "t0");
  const { url, init } = calls[0];
  assert.equal(url, "https://reader.example/panorama"); assert.equal(init.method, "POST");
  assert.equal(init.headers["X-RRM-Demo"], "tok-secreto"); assert.equal(init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(init.body), { question: "q", ids: ["1", "2"] });
  script(reply(501)); const err = await m.panorama("q", ["1"]).catch((e) => e); assert.equal(calls.length, 1); assert.equal(err.kind, "server");
});

test("una respuesta que no es JSON es error http, no un cuelgue", async () => {
  script({ ok: true, status: 200, json: async () => { throw new SyntaxError("x"); } });
  const err = await m.burst("q").catch((e) => e); assert.equal(err.kind, "http");
});
