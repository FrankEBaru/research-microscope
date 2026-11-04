/** Filas de una figura, en el orden del autor. El ancho viene de \\includegraphics[width=0.48\\linewidth]. */

export function figRows(panels) {
  const list = panels || [];
  const width = (panel) => {
    const w = Number(panel && panel.w);
    if (!(w > 0)) return 0;
    return w >= 0.92 ? 1 : w;
  };
  const known = list.some((panel) => width(panel) > 0);
  if (!known) {
    const per = list.length >= 4 ? 2 : Math.max(list.length, 1);
    const rows = [];
    for (let i = 0; i < list.length; i += per) rows.push(list.slice(i, i + per));
    return rows;
  }
  const rows = [];
  let row = [];
  let sum = 0;
  for (const panel of list) {
    const w = width(panel);
    if (w >= 1) {
      if (row.length) rows.push(row);
      rows.push([panel]);
      row = [];
      sum = 0;
      continue;
    }
    const share = w || 0.5;
    if (row.length && sum + share > 1.08) {
      rows.push(row);
      row = [];
      sum = 0;
    }
    row.push(panel);
    sum += share;
  }
  if (row.length) rows.push(row);
  return rows;
}
