// BibTeX de un paper a partir de su ficha de arXiv (título, autores, fecha, id). Sin inventar campos.
const ascii = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]/g, "");
const STOP = new Set(["a", "an", "the", "of", "on", "for", "and", "in", "to", "is", "are", "with", "from", "at", "by"]);
const esc = (s) => s.replace(/([&%$#_])/g, "\\$1");

export function bibtexKey(p) {
  const last = ascii((p.authors[0] || "anon").split(" ").pop()).toLowerCase() || "anon";
  const year = (p.date || "").slice(0, 4);
  const word = ascii((p.title.split(/[\s:–-]+/).find((w) => !STOP.has(w.toLowerCase()) && ascii(w)) || "paper")).toLowerCase();
  return `${last}${year}${word}`;
}

export function bibtex(p) {
  const year = (p.date || "").slice(0, 4);
  const lines = [
    `@misc{${bibtexKey(p)},`,
    `  title = {${esc(p.title)}},`,
    `  author = {${p.authors.map(esc).join(" and ")}},`,
    year ? `  year = {${year}},` : null,
    `  eprint = {${p.arxivId}},`,
    `  archivePrefix = {arXiv},`,
    `  url = {https://arxiv.org/abs/${p.arxivId}}`,
    "}",
  ].filter(Boolean);
  return lines.join("\n");
}
