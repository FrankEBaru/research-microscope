export const metadata = { title: "Licenses & use — Reading Microscope" };

export default function LicensesPage() {
  return (
    <main className="licenses">
      <h1>Licenses & use</h1>
      <p>What you see depends on the paper’s license. We do not guess. An unknown license is treated as closed.</p>
      <ul>
        <li>CC BY, CC BY-SA, CC0, and public domain: the full paper, with attribution on this page, under the title, and in the footer.</li>
        <li>The arXiv license, CC BY-NC, CC BY-ND, and anything else: the title, authors, year, and abstract, a link to arXiv, and short explanations with short quotes. No body, figures, tables, TeX, or embedded PDF.</li>
      </ul>
      <p>Our annotations on CC BY-SA papers are CC BY-SA 4.0.</p>
      <p>The papers and their licenses belong to their authors. This demo is not endorsed by the authors or by arXiv.</p>
      <p>Paper metadata comes from <a href="https://www.semanticscholar.org/">Semantic Scholar</a> (ODC-BY) and from arXiv (CC0).</p>
      <p>This is an open-source demo.</p>
    </main>
  );
}
