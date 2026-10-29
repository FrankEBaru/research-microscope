delete process.env.NEXT_PUBLIC_BURST_URL;
delete process.env.NEXT_PUBLIC_READER_URL;
delete process.env.NEXT_PUBLIC_RRM_DEMO_TOKEN;

import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const paperSrc = readFileSync(new URL("../src/components/Paper.tsx", import.meta.url), "utf8");

async function load() {
  const url = new URL("../src/lib/backend.js", import.meta.url);
  return import(url.href);
}

function runLive(token) {
  const code = `
    const { figureUrl, liveEnabled } = await import("./src/lib/backend.js");
    if (!liveEnabled()) process.exit(2);
    const got = figureUrl("9", "plot.png");
    if (got !== "https://reader.example/file?id=9&name=plot.png&k=tok") {
      console.error(got);
      process.exit(3);
    }
  `;
  return spawnSync(process.execPath, ["--input-type=module", "-e", code], {
    cwd: root,
    env: {
      ...process.env,
      NEXT_PUBLIC_BURST_URL: "https://burst.example",
      NEXT_PUBLIC_READER_URL: "https://reader.example",
      NEXT_PUBLIC_RRM_DEMO_TOKEN: token,
    },
    encoding: "utf8",
  });
}

test("paperKey prefers corpusid", async () => {
  const { paperKey } = await load();
  assert.equal(paperKey({ corpusid: 12, arxivId: "1706.03762" }), "12");
  assert.equal(paperKey({ arxivId: "1706.03762" }), "1706.03762");
  assert.equal(paperKey({ corpusid: "12", arxivId: "1706.03762" }), "1706.03762");
});

test("figureUrl points at /file", async () => {
  const { figureUrl, liveEnabled } = await load();
  assert.equal(liveEnabled(), false);
  assert.equal(figureUrl("1706.03762", "/papers/1706.03762/a.png"), "/papers/1706.03762/a.png");
  assert.equal(figureUrl("1706.03762", "fig1.png"), "/papers/1706.03762/fig1.png");
  const live = runLive("tok");
  assert.equal(live.status, 0, live.stderr);
});

test("ref text uses number", async () => {
  const { refText } = await load();
  assert.equal(refText({ label: "eq:a", number: 1 }, {}), "(1)");
  assert.equal(refText({ label: "sec:a", number: 2 }, {}), "2");
  assert.equal(refText({ label: "eq:a" }, { "eq:a": "(3)" }), "(3)");
  assert.equal(refText({ label: "missing" }, {}), "missing");
  assert.match(paperSrc, /case "ref"/);
});

test("missing is not settled and mbox is text", async () => {
  const { settled, katexSource } = await load();
  assert.equal(settled("missing"), false);
  assert.equal(settled(undefined), false);
  assert.equal(settled("queued"), false);
  assert.equal(settled("parsing"), false);
  assert.equal(settled("done"), true);
  assert.equal(settled("abstract_only"), true);
  assert.equal(settled("failed"), true);
  assert.equal(katexSource("\\mbox{a} + \\mboxx"), "\\text{a} + \\mboxx");
});

test("eq tag comes from number", async () => {
  const { eqTex } = await load();
  assert.equal(eqTex({ tex: "y = x", number: 1 }), "y = x\\tag{1}");
  assert.equal(eqTex({ tex: "y = x\\tag{9}" }), "y = x\\tag{9}");
  assert.match(paperSrc, /eqTex\(/);
  const bare = runLive("");
  assert.notEqual(bare.status, 0);
});
