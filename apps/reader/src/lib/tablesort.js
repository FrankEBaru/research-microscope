// RRM-97: order of a paper table's body rows when the reader sorts by a column.

/**
 * Body row indexes in the order to draw. Numeric when the column is numeric (empty cells last),
 * text otherwise (natural order). sort = {col, dir: "asc"|"desc"} or null for the paper's order.
 */
export function sortedRows(model, sort) {
  const idx = (model?.bodyRows || []).map((_, i) => i);
  if (!sort) return idx;
  const numeric = (model.numericCols || []).includes(sort.col);
  const sign = sort.dir === "asc" ? 1 : -1;
  const textOf = (i) => String(model.rows?.[i]?.raw?.[sort.col] ?? "").trim();
  return idx.sort((a, b) => {
    if (numeric) {
      const x = model.rows?.[a]?.num?.[sort.col];
      const y = model.rows?.[b]?.num?.[sort.col];
      if (x == null && y == null) return a - b;
      if (x == null) return 1;
      if (y == null) return -1;
      return x === y ? a - b : (x - y) * sign;
    }
    const x = textOf(a), y = textOf(b);
    if (!x && !y) return a - b;
    if (!x) return 1;
    if (!y) return -1;
    const r = x.localeCompare(y, "en", { numeric: true, sensitivity: "base" });
    return r ? r * sign : a - b;
  });
}
