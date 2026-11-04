import { arxivAbs } from "@/lib/rights.js";

/** One line under the authors. Text only: no box. */
export default function Rights({ rights }: { rights: any }) {
  if (!rights) return null;
  const open = rights.cls === "open" && !rights.gated;
  const id = rights.arxiv ? `arXiv:${rights.arxiv}${rights.version || ""}` : "";
  const abs = arxivAbs(rights);
  const label = rights.label || "License unknown";
  const note = rights.fixture
    ? "Local fixture: full text for offline testing. Live still treats this license as closed."
    : open
      ? "Annotated by Research Microscope (modified)"
      : rights.gated ? "Abstract and our explanations only" : "";
  return (
    <p className="rights">
      {rights.url ? <a href={rights.url} target="_blank" rel="noreferrer">{label}</a> : <span>{label}</span>}
      {id ? <> · <a href={abs} target="_blank" rel="noreferrer">{id}</a></> : null}
      {note ? <>{" · "}{note}</> : null}
      {open && rights.sa ? " · Our annotations: CC BY-SA 4.0" : null}
    </p>
  );
}
