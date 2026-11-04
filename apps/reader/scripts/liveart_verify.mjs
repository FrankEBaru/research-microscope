// verifyWidget only. No Chrome. The probe gate reads reasons and detail.
import { verifyWidget } from "../src/lib/liveart/verify.js";
import { v04On } from "../src/lib/liveart/spec.js";

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  raw += chunk;
});
process.stdin.on("end", () => {
  const body = JSON.parse(raw || "{}");
  let report;
  try {
    report = verifyWidget(body.widget, { claim: body.claim || "", v04: Boolean(body.v04) || v04On(process.env) });
  } catch (err) {
    report = { accept: false, reasons: ["throw"], detail: [String(err && err.message || err)] };
  }
  process.stdout.write(JSON.stringify({
    accept: Boolean(report.accept),
    reasons: report.reasons || [],
    detail: report.detail || [],
  }));
});
