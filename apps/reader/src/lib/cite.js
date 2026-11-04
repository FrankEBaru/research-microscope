// Cita corta para el globo: primer autor et al. y el título. Nunca la lista completa.

export function briefRef(raw) {
  const s = String(raw || "").replace(/\s+/g, " ").trim();
  if (!s) return { who: "", title: "" };
  const year = /\((19|20)\d{2}[a-z]?\)/.exec(s);
  const head = (year ? s.slice(0, year.index) : "").replace(/[.,\s]+$/, "").trim();
  const tail = year ? s.slice(year.index + year[0].length).replace(/^[\s.:;-]+/, "") : "";
  const who = head ? etAl(head) : "";
  let title = "";
  if (tail) title = tail.split(/\.\s+(?=[A-Z])/)[0].replace(/\.$/, "").trim();
  if (!title) {
    const bits = s.split(/\.\s+/);
    title = bits.length > 1 ? bits.slice(who ? 1 : 0).join(". ") : (who ? "" : s);
  }
  if (title.length > 180) title = `${title.slice(0, 180).replace(/\s+\S*$/, "").trim()}…`;
  return { who, title };
}

function etAl(head) {
  const s = head.replace(/[.,\s]+$/, "").trim();
  if (!s) return "";
  const commaParts = s.split(",").map((part) => part.trim()).filter(Boolean);
  const many = commaParts.length > 2 || /\b(?:and|&)\b/i.test(s) || /\bet al\.?/i.test(s);
  const first = (commaParts[0] || s).replace(/\bet al\.?$/i, "").trim();
  const words = first.split(/\s+/).filter((word) => !/^[A-Z]\.?$/.test(word));
  const surname = /^[A-Z][A-Za-z'’.-]+$/.test(first) ? first : (words.length ? words[words.length - 1] : first);
  return many ? `${surname} et al.` : surname;
}
