// Reader-facing reason when the paper cannot be drawn.

/** @type {[RegExp, string][]} */
const RULES = [
  [/esta corrida no us[oó] ocr/i, "this run did not use OCR"],
  [/ocr skipped:\s*cap|ocr not run/i, "this run did not use OCR"],
  [/no arXiv e-print and no open-access PDF/i, "no arXiv e-print and no open PDF"],
  [/ocr failed/i, "OCR failed"],
  [/ocr returned no blocks/i, "OCR returned no text"],
  [/empty parse/i, "the text arrived empty"],
  [/no tex in e-print/i, "the e-print has no LaTeX"],
  [/pdfpages/i, "the e-print only inserts a PDF"],
  [/e-print failed|pdf failed|pdf route failed|resolve failed/i, "the PDF could not be downloaded"],
];

export function faltaText(reason) {
  const raw = String(reason || "").trim();
  if (!raw) return "the paper could not be drawn";
  for (const [re, line] of RULES) {
    if (re.test(raw)) return line;
  }
  if (/[A-Za-z]/.test(raw) && !/[áéíóúñ¿¡]/i.test(raw)) return "the paper could not be drawn";
  return raw;
}
