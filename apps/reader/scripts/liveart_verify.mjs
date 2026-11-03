// verifyWidget only. No Chrome. The probe gate reads reasons and detail.
import { verifyWidget } from "../src/lib/liveart/verify.js";

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  raw += chunk;
});
process.stdin.on("end", () => {
  const body = JSON.parse(raw || "{}");
  let report;
  try {
    report = verifyWidget(body.widget, { claim: body.claim || "" });
  } catch (err) {
    report = { accept: false, reasons: ["throw"], detail: [String(err && err.message || err)] };
  }
  process.stdout.write(JSON.stringify({
    accept: Boolean(report.accept),
    reasons: report.reasons || [],
    detail: report.detail || [],
  }));
});
