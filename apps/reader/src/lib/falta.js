// Lo que ve el lector cuando el paper no se puede dibujar. En español.

/** @type {[RegExp, string][]} */
const RULES = [
  [/esta corrida no us[oó] ocr/i, "esta corrida no usó OCR"],
  [/ocr skipped:\s*cap|ocr not run/i, "esta corrida no usó OCR"],
  [/no arXiv e-print and no open-access PDF/i, "no hay e-print de arXiv ni un PDF abierto"],
  [/ocr failed/i, "el OCR falló"],
  [/ocr returned no blocks/i, "el OCR no devolvió texto"],
  [/empty parse/i, "el texto llegó vacío"],
  [/no tex in e-print/i, "el e-print no trae LaTeX"],
  [/pdfpages/i, "el e-print solo inserta un PDF"],
  [/e-print failed|pdf failed|pdf route failed|resolve failed/i, "no se pudo bajar el PDF"],
];

export function faltaText(reason) {
  const raw = String(reason || "").trim();
  if (!raw) return "no se pudo dibujar el paper";
  for (const [re, line] of RULES) {
    if (re.test(raw)) return line;
  }
  if (/[A-Za-z]/.test(raw) && !/[áéíóúñ¿¡]/i.test(raw)) return "no se pudo dibujar el paper";
  return raw;
}
