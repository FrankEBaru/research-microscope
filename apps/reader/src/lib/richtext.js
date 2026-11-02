/** Trozo de LaTeX sin $: \mathrm, \max, _{ o ^{. El resto es prosa. */

export function splitRich(text) {
  const src = String(text || "");
  const out = [];
  const re = /\\[A-Za-z]+|_\{|\^\{/g;
  let i = 0;
  let m;
  while ((m = re.exec(src))) {
    if (m.index < i) continue;
    let j = m.index;
    let depth = 0;
    while (j < src.length) {
      const c = src[j];
      if (c === "\\") {
        const cmd = /^\\([A-Za-z]+|.)/.exec(src.slice(j));
        j += cmd ? cmd[0].length : 1;
        continue;
      }
      if (c === "{" || c === "(") { depth++; j++; continue; }
      if (c === "}" || c === ")") { depth = Math.max(0, depth - 1); j++; continue; }
      if (depth || /[0-9=+\-*/,._^]/.test(c)) { j++; continue; }
      if (/[A-Za-z]/.test(c)) {
        const word = /^[A-Za-z]+/.exec(src.slice(j));
        const w = word ? word[0] : c;
        if (w.length >= 4 && src[j + w.length] !== "_" && src[j + w.length] !== "^") break;
        j += w.length;
        continue;
      }
      if (c === " " && /^(\\[A-Za-z]|[A-Za-z0-9(=+\-])/.test(src.slice(j + 1)) && !/^[A-Za-z]{4,}(?![_^])/.test(src.slice(j + 1))) { j++; continue; }
      break;
    }
    const chunk = src.slice(m.index, j).trim();
    if (m.index > i) out.push(["t", src.slice(i, m.index)]);
    if (chunk) out.push(["d", chunk]);
    i = j;
    re.lastIndex = j;
  }
  if (i < src.length) out.push(["t", src.slice(i)]);
  return out;
}
