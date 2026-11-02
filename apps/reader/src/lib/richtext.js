/** LaTeX sin $ (\mathrm, \max, _{, ^{) contra prosa. */
export function splitRich(text) {
  const src = String(text || ""), out = [], re = /\\[A-Za-z]+|_\{|\^\{/g;
  let i = 0, m;
  while ((m = re.exec(src))) {
    if (m.index < i) continue;
    let j = m.index, depth = 0;
    for (; j < src.length;) {
      const c = src[j], word = /^[A-Za-z]+/.exec(src.slice(j));
      if (c === "\\") { j += (/^\\([A-Za-z]+|.)/.exec(src.slice(j)) || [" "])[0].length; continue; }
      if (c === "{" || c === "(") { depth++; j++; continue; }
      if (c === "}" || c === ")") { depth = Math.max(0, depth - 1); j++; continue; }
      if (depth || /[0-9=+\-*/,._^]/.test(c)) { j++; continue; }
      if (word && (word[0].length < 4 || src[j + word[0].length] === "_" || src[j + word[0].length] === "^")) { j += word[0].length; continue; }
      if (c === " " && /^(\\[A-Za-z]|[A-Za-z0-9(=+\-])/.test(src.slice(j + 1)) && !/^[A-Za-z]{4,}(?![_^])/.test(src.slice(j + 1))) { j++; continue; }
      break;
    }
    if (m.index > i) out.push(["t", src.slice(i, m.index)]);
    const chunk = src.slice(m.index, j).trim();
    if (chunk) out.push(["d", chunk]);
    i = j; re.lastIndex = j;
  }
  if (i < src.length) out.push(["t", src.slice(i)]);
  return out;
}
