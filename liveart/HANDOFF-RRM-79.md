# HANDOFF RRM-79 (engine)

Branch: `cursor/rrm-79-live-engine-c8e7`
Contract: **`rrm-widget/0.3`** (`rrm/liveart/contract.py`). JSON shape is still 0.2. Budgets and the canvas/Math lists moved. A string exposes `.length` only. `fillText` of "verified" / "from the paper" is `slop_seal`.
Sandbox: `apps/reader/src/lib/liveart/` (`spec.js`, `parse.js`, `run.js`, `verify.js`, `sandbox.js`, `mount.js`, `showcase.js`, `guest.js`). Gallery: `/liveart`, flag off by default. Not wired into GapNotes (Franklin: later).
Timeout: [V] Chrome 156 headless, iframe `sandbox="allow-scripts"`, draw body `while(true)`. Parent `setTimeout` 800 ms still set the status to `parent-alive`. No Worker. CSP stays without `worker-src`.
Tests: `apps/reader/tests/liveart_sandbox.test.mjs` (21).
`continue` and the value `undefined` parse. A braced `continue` inside `for` still runs the update; inside `while` it retests. `setLineDash` does not. The step cap stays 200000. An English claim can link to the Spanish mark of the same topic.
`quant` is the LLM.int8 absmax row (control `mag`). SmoothQuant stays separate. A bare 8-bit claim stays skip. There is no emulated draw for it yet.
Repair: `rrm/liveart/repair.py`. `RRM_LIVE_REPAIR` is off. One short codegen retry, then the engine checks again. The gallery shows the written explanation when a figure stays down (`stays-down`).
Audit: `python3 scripts/liveart_audit.py --sandbox`. Stack: `python3 scripts/liveart_stack.py --n 16 --sandbox` (16 show on the emulated bank).
READY FOR PROBE 2 is recorded in compass. This repo does not call Meta.

# HANDOFF RRM-79 (engine) — previous stop

Branch: `cursor/rrm-79-live-engine-c8e7`
Stop point: 2026-11-03. Compass was 404 in this environment. Relaunch has compass. Do not start a second contract.

## What’s done

- Read RRM-78 on `cursor/rrm-78-prompts-526e` (PR #57). Their contract is the one to keep: **`rrm-widget/0.1`** in `rrm/liveart/`.
- Copied that package onto this branch unchanged: `CONTRACT.md`, `contract.py`, `fewshots.py`, `offline.py`, `prompts.py`, `__init__.py`. Same bytes as their branch at fetch time. Merge with PR #57 will conflict if both sides edit those files. Prefer their text unless a limit actually changes; if it changes, bump the version in `contract.py` and `CONTRACT.md` together.
- Generated `apps/reader/src/lib/liveart/gold.js` from `gold_widget()` for the four few-shots (`positional-encoding`, `softmax-temperature`, `attention-scale`, `stddev`). It is a browser copy of `fewshots.py` + the explain/questions in `offline.py`. It can drift. Regenerate from Python; do not hand-edit.
- An earlier private design under `apps/reader/src/lib/live/` (custom `ctx.rect` / `ctx.line` API, contract “v1”) was **deleted before any commit**. Do not revive it. The gold draws are real canvas 2d and will not parse against that subset.

Nothing else is on the branch. No iframe, no AST, no runtime verifier, no flag wiring, no tests, no UI.

## Contract to implement (do not fork)

Source of truth: `rrm/liveart/contract.py` and `rrm/liveart/CONTRACT.md`.

JSON keys, no extras: `id`, `topic`, `title`, `explain`, `questions`, `controls`, `draw`.

`draw` is exactly `function draw(ctx, state, t)`. Nested `function` declarations are allowed (the attention few-shot defines `probs`). Host sets `state.w` and `state.h`. Controls are copied onto `state` by id (`state.base`, `state.temp`, `state.d`, `state.sigma`). `t` is seconds. Same `state` and `t` must draw the same picture. No `Math.random`, no `Date`.

Canvas 2d allowlist: `clearRect`, `fillRect`, `strokeRect`, `beginPath`, `closePath`, `moveTo`, `lineTo`, `arc`, `ellipse`, `rect`, `fill`, `stroke`, `fillText`, `save`, `restore`, `translate`, `rotate`, `scale`, and props `fillStyle`, `strokeStyle`, `lineWidth`, `font`, `globalAlpha`.

Math allowlist: `sin`, `cos`, `tan`, `exp`, `log`, `sqrt`, `abs`, `min`, `max`, `pow`, `floor`, `ceil`, `round`, `PI`, `E`.

Banned source patterns already live in `contract.py` (`banned_in`). Mirror them; do not invent a quieter list. Python also rejects extra keys, bad control ranges, questions that do not end in `?`, and injection echoed into title/explain/draw (`offline.verify_widget`). That check is **not** a pixel check.

Flag, off by default: `RRM_LIVE_ARTIFACTS` or `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS` in `1` / `true` / `yes` / `on`. The reader only sees `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS` (Next inlines that name). With the flag off, `path_for` stays `static` and `GapNotes` must keep drawing today’s artifact. Do not delete `ArtifactView`.

Topics the selector already knows are listed in `CONTRACT.md`. Only four have gold draws. `emulated_widget` returns null for the other topics. RRM-80 fills those.

## What’s next (priority order)

1. **Iframe sandbox.** This is the team blocker. `sandbox="allow-scripts"` and **no** `allow-same-origin`. Document CSP: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'`. Sliders stay in the parent. Parent posts `{type:"rrm-params", state, t}`; iframe posts `{type:"rrm-live", ok}`. Check `event.source`, not origin (`null` inside an opaque sandbox). On throw, timeout (~800ms), or no pixels, unmount the iframe and show the static artifact.
2. **AST / allowlist** that accepts the four gold draws and rejects everything else. The gold syntax is not a toy: comma `var`, uninitialized `var i, x`, `for (x = 0; x < w; x++)`, `if`/`else` without braces, `a[i] =`, `s +=`, nested `function`, `array.length`, ternary, `===`. No arrows, no `new`, no string-key `obj["constructor"]`, no `import`. A regex ban is not enough (`constructor` can be built from strings).
3. **Runtime verifier** before mount: runs without throwing, paints non-background pixels, and at least one control at `min` vs `max` changes the picture. Cap loops (the positional draw loops `x < state.w`). Do not `eval` the draw in the parent page. Node can interpret the AST or run a locked-down function only after the AST passes. Time cap is part of the contract’s “Qué no entra en 0.1” list and is still undone.
4. Wire `GapNotes` behind the flag. Fallback is the existing `ArtifactView`. Match a paper block to a gold topic only with the same idea as `offline.py` (`10000`+sin → positional, sqrt+d_k/softmax → attention, sigma → stddev, temperature+softmax → softmax). Do not show a gold widget for a topic that has no draw.
5. Gallery route is optional. `/live` behind the flag is enough to see the four widgets. No Meta calls until this sandbox accepts the gold draws and rejects fetch/eval. Do not ask for a key until then. Say `READY FOR META` only with a plan.

Host decisions that are **not** in the JSON (do not bump `0.1` for these unless RRM-78 agrees): canvas **360×200** logical pixels injected as `state.w` / `state.h`; animate `t` only when the function body uses `t` (positional does; the other three only name it in the signature).

## Decisions

- One contract: `rrm-widget/0.1`. RRM-79 owns iframe, AST, and runtime. RRM-78 owns the prompt text. Changing a limit means bumping the version in `contract.py` so `prompts.py` picks it up.
- Renderer consumes their few-shots as-is. The engine adapts to `function draw(ctx, state, t)`, not the other way around.
- Pass a null-prototype canvas facade into the iframe (methods + the five style props only). `state` is null-prototype. Shadow `Math` with the allowlist inside the draw closure so `Math["constructor"]` is not the real `Function`.
- Static artifact stays the failure path. Flag off means the DOM does not change.
- `gold.js` is a snapshot for the bundle. Python remains the source.

## Open problems

- No sandbox code exists yet. Other agents cannot render a widget from this branch.
- AST has to be written against the gold strings in `fewshots.py`. A parser that only allows `const` and `ctx.rect()` will reject every few-shot.
- `gold.js` will drift from `fewshots.py` / `offline.gold_widget`. Add a test that regenerates and diffs.
- Copying `rrm/liveart/` duplicates PR #57. On rebase, take theirs if the files were only copied, then re-apply engine files (`apps/reader/src/lib/liveart/`, this handoff).
- Pixel proof: parent cannot read an opaque iframe’s canvas. Count pixels in the verifier **before** mount. The iframe only reports ok/error.
- `for (;;)` or `i += 0` will hang `new Function`. The step cap has to live in the interpreter or a killed worker, not in hope.
- Compass was not writable here. Next session should put status in compass `equipo-artefactos/` if it is actually reachable, and keep this file until that landed.
- Not ready for Meta. No model calls.
