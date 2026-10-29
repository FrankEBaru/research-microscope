// Tablas → gráficas vivas. Determinista y fiel: solo re-presenta los números que el autor publicó, sin cambiarlos.
// `analyze(tabla)` devuelve columnas numéricas con su cabecera (expandida por colspan) y las filas con su etiqueta.

/** Texto plano de una celda (inlines de la UI). Las matemáticas van como $latex$. */
export function cellText(inls) {
  return (inls || []).map((x) => x.t === "text" ? x.v : x.t === "math" ? `$${x.v}$` : x.t === "cite" || x.t === "note" ? "" : Array.isArray(x.c) ? cellText(x.c) : x.v || "").join("").replace(/\s+/g, " ").trim();
}

/** Número de una celda: «23.75», «85%», «1,024», «$2.3\cdot10^{19}$». Devuelve null si no es un número limpio. */
export function parseNumber(text) {
  let t = String(text || "").trim().replace(/^\$|\$$/g, "").replace(/\\(?:textbf|mathbf|text)\{([^}]*)\}/g, "$1").replace(/[{}]/g, "").trim();
  if (!t) return null;
  const sci = /^([-+]?\d*\.?\d+)\s*(?:\\cdot|\\times|·|×)\s*10\^\s*([-+]?\d+)$/.exec(t);
  if (sci) return Number(`${sci[1]}e${Number(sci[2])}`);  // como cadena: sin error de coma flotante
  t = t.replace(/(\d),(\d{3})(?!\d)/g, "$1$2");
  if (/^[-+−]?\d*\.?\d+%?$/.test(t)) return Number(t.replace("−", "-").replace("%", ""));
  return null;
}

const expand = (cells, spans) => {  // cada celda se repite por su colspan; las repeticiones llevan cont=true
  const out = [];
  cells.forEach((c, i) => { for (let k = 0; k < ((spans && spans[i]) || 1); k++) out.push({ c: k === 0 ? c : [], cont: k > 0 }); });
  return out;
};
const junk = (s) => /^\d+-\d+$/.test(s); // residuo de \cmidrule{2-3}

/**
 * @param {{head: any[][], body: any[][], hspan?: number[][], bspan?: number[][]}} t
 * @returns {{headers: string[], rows: {label: string, raw: string[], num: (number|null)[]}[], numericCols: number[]}}
 */
export function analyze(t) {
  const all = [...(t.head || []).map((r, i) => expand(r, t.hspan?.[i])), ...(t.body || []).map((r, i) => expand(r, t.bspan?.[i]))];
  const ncols = Math.max(0, ...all.map((r) => r.length));
  const text = all.map((r) => Array.from({ length: ncols }, (_, i) => cellText(r[i]?.c)));
  // filas de cabecera: las primeras que no contienen ningún número (los residuos «2-3» no cuentan)
  let h = 0;
  while (h < text.length - 1 && h < 3 && !text[h].some((c) => parseNumber(c) !== null && !junk(c))) h++;
  h = Math.max(h, 1);
  // celdas combinadas (colspan) en la cabecera: heredan la etiqueta de la celda que las abarca
  for (let r = 0; r < h; r++) for (let i = 1; i < ncols; i++) if (all[r][i]?.cont) text[r][i] = text[r][i - 1];
  const headers = Array.from({ length: ncols }, (_, i) => {
    const parts = [];
    for (let r = 0; r < h; r++) { const c = junk(text[r][i]) ? "" : text[r][i]; if (c && c !== parts[parts.length - 1]) parts.push(c); }
    return parts.join(" · ");
  });
  // para dibujar la tabla con colspan: filas originales (sin expandir) con la columna donde empieza cada celda
  const orig = [...(t.head || []).map((r, i) => ({ cells: r, spans: t.hspan?.[i] })), ...(t.body || []).map((r, i) => ({ cells: r, spans: t.bspan?.[i] }))];
  const place = (o, isHead) => { let col = 0; return o.cells.map((c, i) => { const span = (o.spans && o.spans[i]) || 1; const cell = { c: isHead && junk(cellText(c)) ? [] : c, span, col }; col += span; return cell; }); };
  const headRows = orig.slice(0, h).map((o) => place(o, true));
  const bodyRows = orig.slice(h).map((o) => place(o, false));
  const rows = text.slice(h).map((r) => ({ label: (r[0] || "").replace(/\[cite\]/g, "").trim(), raw: r, num: r.map((c, i) => (i === 0 ? null : parseNumber(c))) }));
  const numericCols = [];
  for (let i = 1; i < ncols; i++) {
    const filled = rows.filter((r) => r.raw[i]);
    if (filled.length >= 3 && filled.filter((r) => r.num[i] !== null).length / filled.length >= 0.6) numericCols.push(i);
  }
  return { headers, rows, numericCols, headRows, bodyRows };
}

/** Barras de una columna: valores no nulos, con orden y escala elegidos. Las barras de log usan log10 relativo al mínimo positivo. */
export function bars(model, col, { sort = "original", log = false } = {}) {
  let items = model.rows.map((r, i) => ({ row: i, label: r.label || `fila ${i + 1}`, value: r.num[col], raw: r.raw[col] })).filter((x) => x.value !== null);
  if (sort === "asc") items.sort((a, b) => a.value - b.value); else if (sort === "desc") items.sort((a, b) => b.value - a.value);
  const vals = items.map((x) => x.value), max = Math.max(...vals), min = Math.min(...vals.filter((v) => v > 0), Infinity);
  return items.map((x) => {
    let f;
    if (log && x.value > 0 && isFinite(min) && max > min) f = (Math.log10(x.value) - Math.log10(min)) / (Math.log10(max) - Math.log10(min)) * 0.92 + 0.08;
    else f = max > 0 ? Math.max(0, x.value) / max : 0;
    return { ...x, frac: Math.min(1, f) };
  });
}
