// Verifier plus the real iframe. No Meta. One widget at a time so a hung draw cannot block the next.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

import { srcdoc, srcdoc04 } from "../src/lib/liveart/sandbox.js";
import { isV04, v04On } from "../src/lib/liveart/spec.js";

// 0.4 (RRM-90): RRM_LIVEART_V04 turns on the 0.4 verifier and the 0.4 iframe for 0.4 widgets.
const V04 = v04On(process.env);
import { HOST } from "../src/lib/liveart/spec.js";
import { verifyWidget } from "../src/lib/liveart/verify.js";

const FRAME_MS = HOST.frame_ms;

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

function stateOf(widget) {
  const state = { w: HOST.canvas_w, h: HOST.canvas_h };
  for (const control of widget.controls || []) state[control.id] = control.value;
  return state;
}

function verifyRow(row) {
  let report;
  try {
    report = verifyWidget(row.widget, { claim: row.claim || "", v04: V04 });
  } catch (err) {
    report = { accept: false, reasons: ["throw"], usesT: false };
  }
  return {
    group: row.group,
    id: row.id,
    topic: row.widget && row.widget.topic,
    verify: report.accept ? "pass" : "fail",
    reasons: report.reasons,
    detail: report.detail || [],
    usesT: report.usesT,
    sandbox: report.accept ? "pending" : "not_mounted",
    pixels: 0,
  };
}

function connect(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const pending = new Map();
    let id = 0;
    ws.addEventListener("open", () => resolve({
      ws,
      send(method, params) {
        return new Promise((res, rej) => {
          const msgId = ++id;
          const timer = setTimeout(() => {
            pending.delete(msgId);
            rej(new Error("cdp_timeout " + method));
          }, FRAME_MS + 2500);
          pending.set(msgId, { res, rej, timer });
          ws.send(JSON.stringify({ id: msgId, method, params: params || {} }));
        });
      },
    }));
    ws.addEventListener("message", (ev) => {
      const data = JSON.parse(ev.data);
      if (!data.id || !pending.has(data.id)) return;
      const item = pending.get(data.id);
      clearTimeout(item.timer);
      pending.delete(data.id);
      if (data.error) item.rej(new Error(JSON.stringify(data.error)));
      else item.res(data.result);
    });
    ws.addEventListener("error", () => reject(new Error("ws")));
  });
}

async function chromeUp(port, dir) {
  const proc = spawn("google-chrome", [
    "--headless=new", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
    `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, "about:blank",
  ], { stdio: "ignore" });
  for (let i = 0; i < 50; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return { proc, version: await res.json() };
    } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  proc.kill();
  throw new Error("chrome_down");
}

const HARNESS = `<!DOCTYPE html><meta charset="utf-8"><title>audit</title>
<iframe id="f" sandbox="allow-scripts"></iframe>
<script>
window.__go = function (html, state) {
  return new Promise(function (resolve) {
    var old = document.getElementById("f");
    if (old) old.remove();
    var frame = document.createElement("iframe");
    frame.id = "f";
    frame.setAttribute("sandbox", "allow-scripts");
    document.body.appendChild(frame);
    var done = false;
    function finish(row) { if (done) return; done = true; resolve(row); }
    var arm = setTimeout(function () { finish({ ok: false, reason: "timeout", pixels: 0 }); }, ${FRAME_MS});
    window.onmessage = function (ev) {
      if (ev.source !== frame.contentWindow) return;
      var data = ev.data || {};
      if (data.type !== "rrm-live") return;
      if (data.reason === "ready") {
        clearTimeout(arm);
        arm = setTimeout(function () { finish({ ok: false, reason: "timeout", pixels: 0 }); }, ${FRAME_MS});
        frame.contentWindow.postMessage({ type: "rrm-params", state: state, t: 0 }, "*");
        return;
      }
      clearTimeout(arm);
      finish({ ok: !!data.ok, reason: data.reason || "throw", pixels: data.pixels || 0 });
    };
    frame.srcdoc = html;
  });
};
</script>`;

async function openPage(browser, port) {
  const created = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  const target = await created.json();
  const page = await connect(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  const tree = await page.send("Page.getFrameTree");
  await page.send("Page.setDocumentContent", { frameId: tree.frameTree.frame.id, html: HARNESS });
  return { page, targetId: target.id, browser };
}

async function sandboxRows(rows, widgets) {
  const port = 9341;
  const dir = "/tmp/rrm-audit-chrome";
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const { proc, version } = await chromeUp(port, dir);
  const browser = await connect(version.webSocketDebuggerUrl);
  let session = await openPage(browser, port);
  const byId = new Map(widgets.map((row) => [row.group + ":" + row.id, row]));
  try {
    for (const row of rows) {
      if (row.sandbox !== "pending") continue;
      const src = byId.get(row.group + ":" + row.id);
      const html = V04 && isV04(src.widget) ? srcdoc04(src.widget) : srcdoc(src.widget.draw);
      const state = stateOf(src.widget);
      const expr = `window.__go(${JSON.stringify(html)}, ${JSON.stringify(state)})`;
      try {
        const result = await session.page.send("Runtime.evaluate", {
          expression: expr,
          awaitPromise: true,
          returnByValue: true,
        });
        const value = result.result && result.result.value;
        if (!value) {
          row.sandbox = "fail";
          row.reasons = row.reasons.concat("sandbox");
        } else {
          row.sandbox = value.ok ? "pass" : "fail";
          row.pixels = value.pixels || 0;
          if (!value.ok) row.reasons = row.reasons.concat("sandbox:" + value.reason);
        }
      } catch {
        row.sandbox = "fail";
        row.reasons = row.reasons.concat("sandbox:timeout");
        try { await browser.send("Target.closeTarget", { targetId: session.targetId }); } catch { /* next page */ }
        session = await openPage(browser, port);
      }
    }
  } finally {
    try { browser.ws.close(); } catch { /* closed */ }
    proc.kill();
  }
}

const input = JSON.parse(readFileSync(arg("--in"), "utf8"));
const rows = input.map(verifyRow);
if (process.argv.includes("--sandbox")) await sandboxRows(rows, input);
const out = arg("--out");
if (out) writeFileSync(out, JSON.stringify(rows, null, 2));
const pass = rows.filter((row) => row.verify === "pass" && row.sandbox !== "fail").length;
console.log(JSON.stringify({
  total: rows.length,
  verify_pass: rows.filter((row) => row.verify === "pass").length,
  sandbox_pass: rows.filter((row) => row.sandbox === "pass").length,
  shown: pass,
}));
