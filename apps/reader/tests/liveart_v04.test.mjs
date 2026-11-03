import test from "node:test";
import assert from "node:assert/strict";

import { ROUND } from "../src/lib/liveart/round.js";
import { VERSION_04, v04On } from "../src/lib/liveart/spec.js";
import { verifyWidget } from "../src/lib/liveart/verify.js";

const draw = `function draw(ctx, state, t, ui) {
  var box = ui.area("main");
  ui.axes("main");
  var p = 1 / (1 + state.beta + state.mode);
  ctx.fillStyle = ui.c.c1;
  ctx.fillRect(box.x, box.Y(p), 48, box.y1 - box.Y(p));
  ui.readout("plol", p);
  ui.mark("half", 0.5);
  ui.say("hold");
}`;

function widget() {
  return {
    version: VERSION_04,
    id: "kl-policy",
    topic: "kl_rlhf",
    title: "The KL leash keeps the policy near the reference",
    hook: "Does a bigger beta chase the reward harder?",
    explain: "A larger beta pulls the policy back toward the reference, so the odd token gets less probability.",
    questions: [
      { q: "Does a bigger beta lower the odd token?", why: "the KL term punishes leaving the reference" },
      { q: "What happens to the bar at the right?", why: "it shrinks as beta grows" },
    ],
    controls: [
      { id: "beta", label: "KL weight", min: 0.05, max: 3, value: 0.6, step: 0.05 },
      { id: "mode", label: "method", kind: "select", options: ["absmax", "drop", "int8"], min: 0, max: 2, value: 0, step: 1 },
    ],
    areas: [{ id: "main", rect: [0, 0, 1, 1], x: { min: 0, max: 3 }, y: { min: 0, max: 1 } }],
    readouts: [{ id: "plol", label: "lol", digits: 2 }],
    marks: [{ id: "half", area: "main", axis: "y" }],
    legend: [{ color: "c1", text: "policy" }],
    takeaway: { hold: "At beta = {beta} the odd token is {plol}." },
    anchor: {
      latex: "\\pi(y)\\propto \\pi_{ref}(y)\\exp(r/\\beta)",
      vars: [{ tex: "\\beta", control: "beta" }],
      quote: "the optimal solution takes the form",
      arxiv: "2305.18290",
    },
    predict: {
      options: ["Harder", "Less hard", "No change"],
      answer: 1,
      reveal: { beta: 2 },
      check: { readout: "plol", expect: "down" },
    },
    draw,
  };
}

test("0.4 stays behind the flag and the 0.3 gallery still mounts", () => {
  const previous = process.env.RRM_LIVEART_V04;
  try {
    delete process.env.RRM_LIVEART_V04;
    assert.equal(v04On(), false);
    const blocked = verifyWidget(widget());
    assert.equal(blocked.accept, false);
    assert.ok(blocked.reasons.includes("v04_off"), blocked.reasons.join(","));

    process.env.RRM_LIVEART_V04 = "1";
    assert.equal(v04On(), true);
    const report = verifyWidget(widget());
    assert.equal(report.accept, true, report.reasons.join(",") + " " + (report.detail || []).join(","));
    assert.ok(!report.notes.includes("free_text"));

    const painted = widget();
    painted.draw = draw.replace("ui.say(\"hold\");", "ctx.fillText(\"beta\", 20, 20); ui.say(\"hold\");");
    const noted = verifyWidget(painted);
    assert.equal(noted.accept, true, noted.reasons.join(","));
    assert.ok(noted.notes.includes("free_text"));

    const flat = widget();
    flat.predict = { ...flat.predict, check: { readout: "plol", expect: "up" } };
    const missed = verifyWidget(flat);
    assert.ok(missed.reasons.includes("predict"), missed.reasons.join(","));

    for (const entry of ROUND) {
      const got = verifyWidget(entry.widget);
      assert.equal(got.accept, true, entry.widget.id + " " + got.reasons.join(","));
    }
  } finally {
    if (previous == null) delete process.env.RRM_LIVEART_V04;
    else process.env.RRM_LIVEART_V04 = previous;
  }
});
