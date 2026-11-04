// RRM-97: the real phases of opening a paper, read from /status and /paper (stage, stages, source, timings).
// Pure functions: Engine records when each phase starts; OpenPhases draws the rows.

/** Rows in the order the backend runs them. `ocr` (PDF route) only shows when the backend took it; its output is the sections. */
export const OPEN_ROWS = ["find", "download", "ocr", "sections"];

/**
 * Phase of a paper still opening, or the end state.
 * row: a /status row ({status, stage, stages, source, ocr_invoked_at, text}); meta: /paper meta (optional).
 * Returns find | download | sections | ocr | text | abstract | failed.
 */
export function openPhase(row, meta) {
  const r = row || {};
  const m = meta || {};
  const status = String(r.status || m.status || "");
  const stage = String(r.stage || m.stage || "");
  const source = String(r.source || m.source || "");
  if (status === "abstract_only") return "abstract";
  if (status === "failed") return "failed";
  if (status === "done" || r.text === true || source === "latex" || stage === "sections" || stage === "figures" || stage === "done") return "text";
  if (source === "ocr") return "text";
  if (stage === "ocr" || r.ocr_invoked_at || m.ocr_invoked_at) return "ocr";
  if (stage === "stub" || stage === "download") {
    // The e-print is in and the parse is running: reading sections.
    const got = (Array.isArray(m.downloads) ? m.downloads : []).some((d) => d && d.ok && d.source === "arxiv_eprint");
    return got ? "sections" : "download";
  }
  return "find";
}

/** Where the text can come from, as far as we know: arxiv | pdf | none | unknown. */
export function openRoute(meta, paper) {
  const m = meta || {};
  const p = paper || {};
  if (m.arxiv || p.arxivId) return "arxiv";
  if (m.oa_pdf || p.oaPdf || m.pdf) return "pdf";
  if (m.stage === "stub" || m.stage === "download" || m.status === "parsing" || p.title) return "none";
  return "unknown";
}

const LABELS = {
  find: "Finding the paper",
  download: { arxiv: "Downloading from arXiv", pdf: "Downloading the open PDF", none: "Looking for an open version", unknown: "Downloading" },
  sections: "Reading sections",
  ocr: "Reading the PDF (OCR)",
};

export function phaseLabel(id, route = "unknown") {
  const v = LABELS[id];
  return typeof v === "string" ? v : (v?.[route] || v?.unknown || id);
}

/** Append a phase change to the log. Same phase twice is one entry. */
export function notePhase(log, phase, at) {
  const prev = Array.isArray(log) ? log : [];
  if (prev.length && prev[prev.length - 1].phase === phase) return prev;
  return [...prev, { phase, at }];
}

/**
 * Rows to draw: {id, label, state: done|run|wait, sec}.
 * `log` holds {phase, at} in ms; `now` is the clock. `ocr` only appears if it ran.
 */
export function phaseRows(log, now, route = "unknown") {
  const seen = (Array.isArray(log) ? log : []).filter((e) => OPEN_ROWS.includes(e.phase));
  const last = seen[seen.length - 1];
  const cur = last ? last.phase : "find";
  const idx = OPEN_ROWS.indexOf(cur);
  const ids = OPEN_ROWS.filter((id) => id !== "ocr" || seen.some((e) => e.phase === "ocr"));
  return ids.map((id) => {
    const i = OPEN_ROWS.indexOf(id);
    const k = seen.findIndex((e) => e.phase === id);
    const start = k >= 0 ? seen[k].at : null;
    const end = k >= 0 && k + 1 < seen.length ? seen[k + 1].at : null;
    // A row skipped by the backend (it went straight from find to sections) counts as done with no time.
    const state = id === cur ? "run" : i < idx ? "done" : "wait";
    const sec = start == null ? null : Math.max(0, ((end ?? now) - start) / 1000);
    return { id, label: phaseLabel(id, route), state, sec: state === "wait" ? null : sec };
  });
}

/** mm:ss, or s for under a minute. */
export function clockText(sec) {
  if (sec == null || !Number.isFinite(sec)) return "—";
  const s = Math.max(0, Math.floor(sec));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
