// rrm-widget/0.4 (RRM-90): verify with and without the flag, 0.3 compatibility, negative cases,
// the iframe document, and the Python mirror of the examples. No network, no Chrome.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { NOSLIDER } from "../src/lib/liveart/noslider.js";
import { ROUND } from "../src/lib/liveart/round.js";
import { runDraw } from "../src/lib/liveart/run.js";
import { srcdoc04 } from "../src/lib/liveart/sandbox.js";
import { v04On } from "../src/lib/liveart/spec.js";
import { V04 } from "../src/lib/liveart/v04.js";
import { verifyWidget } from "../src/lib/liveart/verify.js";

test("the four 0.4 widgets pass with the flag and are refused without it", () => {
  assert.equal(V04.length, 4);
  for (const { widget } of V04) {
    const on = verifyWidget(widget, { v04: true });
    assert.equal(on.accept, true, widget.id + " " + on.reasons.join(","));
    assert.deepEqual(verifyWidget(widget, {}).reasons, ["version"]);
  }
});

test("every 0.3 widget behaves the same with the flag on", () => {
  for (const { widget } of [...ROUND, ...NOSLIDER]) {
    const off = verifyWidget(widget, {});
    const on = verifyWidget(widget, { v04: true });
    assert.equal(off.accept, true, widget.id + " " + off.reasons.join(","));
    assert.deepEqual(on.reasons, off.reasons, widget.id);
  }
});

test("0.4 refusals: free text, undeclared readout, unknown helper, bad takeaway, 0.4 draw on a 0.3 widget", () => {
  const kl = V04.find((e) => e.widget.id === "kl-policy").widget;
  const variant = (patch) => ({ ...JSON.parse(JSON.stringify(kl)), ...patch });
  const at = 'ui.readout("plol", p[3]);';
  const cases = [
    ["free_text", variant({ draw: kl.draw.replace(at, at + ' ctx.fillText("lol", 10, 10);') })],
    ["readout", variant({ draw: kl.draw.replace(at, at + ' ui.readout("zzz", 1);') })],
    ["banned", variant({ draw: kl.draw.replace('ui.axes("main");', 'ui.axes("main"); ui.secret(1);') })],
    ["takeaway", variant({ takeaway: { took: "lol takes {nope}." } })],
    ["hook", variant({ hook: "No question mark" })],
  ];
  for (const [reason, w] of cases) assert.ok(verifyWidget(w, { v04: true }).reasons.includes(reason), reason);
  const legacy = { ...ROUND[0].widget, draw: ROUND[0].widget.draw.replace("function draw(ctx, state, t)", "function draw(ctx, state, t, ui)") };
  assert.deepEqual(verifyWidget(legacy, { v04: true }).reasons, ["version"]);
});

test("the frame carries readouts, takeaway variant and regime marks; labels stay in budget", () => {
  for (const { widget } of V04) {
    const state = { w: 640, h: 360 };
    for (const c of widget.controls) state[c.id] = c.value;
    const r = runDraw(widget.draw, state, 0, 200000, { v04: true, widget });
    const declared = new Set(widget.readouts.map((x) => x.id));
    assert.ok(Object.keys(r.frame.readouts).every((id) => declared.has(id)), widget.id);
    if (widget.takeaway && typeof widget.takeaway === "object") assert.ok(r.frame.say in widget.takeaway, widget.id);
    assert.ok(r.frame.report.labels <= 3 && !r.frame.report.free_text, widget.id);
  }
});

test("the 0.4 iframe document embeds the helpers once and closes its scripts", () => {
  const html = srcdoc04(V04[2].widget);
  assert.equal((html.match(/function makeUI\(/g) || []).length, 1);
  assert.equal((html.match(/<\/script>/g) || []).length, 2);
  assert.ok(html.includes("rrm-init") && html.includes("default-src 'none'"));
});

test("flag parsing and the Python mirror of the examples", () => {
  assert.equal(v04On({}), false);
  assert.equal(v04On({ RRM_LIVEART_V04: "1" }), true);
  const mirror = JSON.parse(readFileSync(new URL("../../../rrm/liveart/v04_examples.json", import.meta.url), "utf8"));
  assert.deepEqual(mirror, V04.map((e) => e.widget));
});

test("an area rect is fractions of the canvas, not pixels (RRM-96: pixel rects drew nothing)", () => {
  const kl = V04.find((e) => e.widget.id === "kl-policy").widget;
  const withRect = (rect) => {
    const w = JSON.parse(JSON.stringify(kl));
    w.areas = (w.areas || [{ id: "main" }]).map((a, i) => (i === 0 ? { ...a, rect } : a));
    return verifyWidget(w, { v04: true });
  };
  assert.equal(withRect([0, 0, 1, 0.6]).accept, true);
  for (const bad of [[80, 40, 520, 260], [0.5, 0, 0.7, 1], [0, 0, 0, 1], [0, 0, 1]]) {
    assert.ok(withRect(bad).reasons.includes("areas"), JSON.stringify(bad));
  }
});
