// Reads the license the backend already decided. Does not classify.

export function isGated(paper, state) {
  if (state && state.gated) return true;
  return Boolean(paper && paper.rights && paper.rights.gated);
}

/** Pieces of the one-line attribution. Empty when the paper has no rights. */
export function rightsLine(rights) {
  if (!rights) return [];
  const bits = [];
  if (rights.label) bits.push(String(rights.label));
  if (rights.arxiv) bits.push(`arXiv:${rights.arxiv}${rights.version || ""}`);
  const open = rights.cls === "open" && !rights.gated;
  if (rights.fixture) bits.push("Local fixture: full text for offline testing. Live still treats this license as closed.");
  else bits.push(open ? "Annotated by Research Reading Microscope (modified)" : "Abstract and our explanations only");
  if (open && rights.sa) bits.push("Our annotations: CC BY-SA 4.0");
  return bits;
}

export function arxivAbs(rights) {
  if (!rights || !rights.arxiv) return "";
  return `https://arxiv.org/abs/${rights.arxiv}${rights.version || ""}`;
}

export function arxivPdf(rights) {
  if (!rights || !rights.arxiv) return "";
  return `https://arxiv.org/pdf/${rights.arxiv}${rights.version || ""}`;
}
