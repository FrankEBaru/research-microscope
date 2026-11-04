// Cita corta para el globo: (Primer autor et al.) y el título, en una sola línea.
// Nunca la lista de autores ni la ficha completa.

export function briefRef(raw) {
  const s = String(raw || "").replace(/\\&/g, "&").replace(/\s+/g, " ").trim();
  if (!s) return { who: "", title: "" };
  const cut = authorCut(s);
  const head = (cut ? s.slice(0, cut) : s.split(/\.\s+/)[0]).replace(/[.,\s]+$/, "").trim();
  const tail = cut ? s.slice(cut) : s.slice(head.length);
  const name = head ? etAl(head) : "";
  let title = titleOf(tail);
  if (!title || looksLikeAuthors(title)) title = titleOf(s.slice(head.length));
  if (looksLikeAuthors(title)) title = "";
  if (title.length > 140) title = `${title.slice(0, 140).replace(/\s+\S*$/, "").trim()}…`;
  return { who: name ? `(${name})` : "", title };
}

/** Dónde terminan los autores y empieza el título. 0 si no se ve el corte. */
function authorCut(s) {
  const year = /\((?:19|20)\d{2}[a-z]?\)\s*\.?\s*/.exec(s);
  if (year && year.index < 400) return year.index + year[0].length;
  // RRM-103: ACL style, "Andrew M Dai and Quoc V Le. 2015. Semi-supervised sequence learning. In …" (BERT's refs)
  // gave "(learning et al.)". The bare year between two periods ends the authors.
  const acl = /\.\s+(?:19|20)\d{2}[a-z]?\.\s+/.exec(s);
  if (acl && acl.index < 400) return acl.index + acl[0].length;
  const sentence = /[a-z]\)?\.\s+(?=[A-Z“"'])/.exec(s);
  if (sentence) return sentence.index + sentence[0].length;
  return 0;
}

function titleOf(tail) {
  let t = String(tail || "").replace(/^[\s.:;-]+/, "");
  t = t.replace(/^(?:In|Proceedings of|Proc\.)\s+/i, "");
  if (!t) return "";
  return t.split(/\.\s+(?=[A-Z])/)[0].replace(/\.$/, "").trim();
}

function looksLikeAuthors(s) {
  const text = String(s || "");
  const commas = (text.match(/,/g) || []).length;
  return commas >= 2 && /\b(?:and|&)\b/i.test(text);
}

function etAl(head) {
  const s = head.replace(/[.,\s]+$/, "").replace(/\((?:19|20)\d{2}[a-z]?\)/, "").replace(/[.\s]+(?:19|20)\d{2}[a-z]?$/, "").trim();
  if (!s) return "";
  // RRM-103: "Andrew M Dai and Quoc V Le" has no comma: the first author ends at "and".
  const commaParts = s.split(/,|\s+(?:and|&)\s+/).map((part) => part.trim()).filter(Boolean);
  const many = commaParts.length > 2 || /\b(?:and|&)\b/i.test(s) || /\bet al\.?/i.test(s);
  const first = (commaParts[0] || s).replace(/\bet al\.?$/i, "").trim();
  const words = first.split(/\s+/).filter((word) => !/^[A-Z]\.?$/.test(word));
  const surname = /^[A-Z][A-Za-z'’.-]+$/.test(first) ? first : (words.length ? words[words.length - 1] : first);
  return many ? `${surname} et al.` : surname;
}
