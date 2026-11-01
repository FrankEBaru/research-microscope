import test from "node:test";
import assert from "node:assert/strict";
import { parseProse, polishText, presentInlines, visibleInlines, pdfPagesOnly } from "../src/lib/prose.js";

const text = (nodes) => nodes.map((n) => n.t === "text" ? n.v : n.t === "em" ? `*${text(n.c)}*` : n.t === "strong" ? `**${text(n.c)}**` : n.t === "math" ? `$${n.v}$` : n.t === "cite" ? `[@${n.keys.join(",")}]` : n.t === "ref" ? `#${n.label}` : "").join("");

test("titles lose spacing commands and protect line breaks", () => {
  assert.equal(polishText("\\!\\!Mip-NeRF: A Multiscale Representation\\!"), "Mip-NeRF: A Multiscale Representation");
  assert.equal(polishText("Local Light Field Fusion: \\protect\\\\Practical View Synthesis"), "Local Light Field Fusion: Practical View Synthesis");
});

test("table residue and font switches become words", () => {
  assert.equal(polishText("\\rule{0pt}{2.0ex}Self-Attention"), "Self-Attention");
  assert.equal(polishText("{\\bf Method}"), "Method");
  assert.equal(text(parseProse("a {\\it global} approach")), "a *global* approach");
  assert.equal(polishText("\\multirow{2}{*}{Model}"), "Model");
  assert.equal(polishText("\\multicolumn{2}{|c}{BLEU}"), "BLEU");
  assert.equal(polishText("\\cmidrule{2-3} EN-DE"), "EN-DE");
  assert.equal(polishText("5.0{} BLEU"), "5.0 BLEU");
});

test("accents, quotes, percent and boldmath", () => {
  assert.equal(polishText("H\\\"older"), "Hölder");
  assert.equal(polishText("the concept of ``attention\" has"), "the concept of “attention” has");
  assert.equal(polishText("by $17\\%$"), "by 17%");
  assert.equal(polishText("The $L$ Hyperparameter"), "The L Hyperparameter");
  const nodes = parseProse("representation \\mbox{\\boldmath{$s$}} for");
  assert.equal(text(nodes), "representation $\\mathbf{s}$ for");
});

test("exploded cite definitions become cite nodes", () => {
  const raw = "The model by \\def\\citename#1{{\\frenchspacing#1} (}\\@ifnextchar [{\\@tempswatrue\\@citexb}{\\@tempswafalse\\@citexb[]}{luong15} reads";
  const nodes = parseProse(raw);
  assert.equal(text(nodes), "The model by [@luong15] reads");
});

test("preamble-only lines disappear and includegraphics is not prose", () => {
  assert.equal(polishText("\\definecolor{yellow}{rgb}{1,1, 0.6}"), "");
  assert.equal(polishText("\\newcommand{\\barron}[1]{{\\color{blue} barron: #1}}"), "");
  assert.equal(visibleInlines([{ t: "text", v: "\\definecolor{yellow}{rgb}{1,1,0.6}" }]), false);
  const blocks = [{ kind: "p", inlines: [{ t: "text", v: "\\includegraphics[width=0.98\\paperwidth,page=1]{main.pdf}" }] }];
  assert.equal(pdfPagesOnly(blocks), true);
  assert.equal(pdfPagesOnly([{ kind: "p", inlines: [{ t: "text", v: "Hello" }] }]), false);
});

test("a sentence keeps the space that separates it from the next", () => {
  const a = presentInlines([{ t: "text", v: "tasks. " }]);
  const b = presentInlines([{ t: "text", v: "One factor" }]);
  assert.equal((a[0].v || "") + (b[0].v || ""), "tasks. One factor");
});

test("spaces beside math are kept", () => {
  const nodes = presentInlines([
    { t: "text", v: "the length " },
    { t: "math", v: "n" },
    { t: "text", v: " is smaller" },
  ]);
  assert.equal(nodes.map((n) => n.t === "math" ? `$${n.v}$` : n.v).join(""), "the length $n$ is smaller");
});

test("a macro whose argument was split by math is not prose", () => {
  const defs = presentInlines([
    { t: "text", v: "\\newcommand{\\bestnum}[1]{" },
    { t: "math", v: "\\mathbf{#1}" },
    { t: "text", v: "}" },
    { t: "text", v: " \\newcommand{\\secnum}[1]{" },
    { t: "math", v: "\\mathit{#1}" },
    { t: "text", v: "}" },
  ]);
  assert.equal(visibleInlines([
    { t: "text", v: "\\newcommand{\\bestnum}[1]{" },
    { t: "math", v: "\\mathbf{#1}" },
    { t: "text", v: "}" },
  ]), false);
  assert.equal(text(defs).trim(), "");
  const kept = presentInlines([
    { t: "text", v: "See " },
    { t: "text", v: "\\newcommand{\\foo}[1]{" },
    { t: "math", v: "#1" },
    { t: "text", v: "} next." },
  ]);
  assert.equal(text(kept), "See next.");
});

test("split font commands and stray braces leave the words", () => {
  assert.equal(text(parseProse("\\bf{System}")), "**System**");
  assert.equal(polishText("\\hdashline Base + dropout"), "Base + dropout");
  assert.equal(text(parseProse("models.}")), "models.");
  assert.equal(text(parseProse("proposed: \\edit{it is cheaper")), "proposed: it is cheaper");
  assert.equal(text(parseProse("said \\correct{Roger Dow}, CEO")), "said Roger Dow, CEO");
  assert.equal(text(parseProse("keep \\foo{\\bar} raw")), "keep \\foo{\\bar} raw");
  const ref = presentInlines([{ t: "math", v: "\\eqref{eq:diff_scaling}" }]);
  assert.equal(ref[0].t, "ref");
  assert.equal(ref[0].label, "eq:diff_scaling");
  assert.equal(text(parseProse("a {\\it global} approach")), "a *global* approach");
});

test("presentInlines merges split tokens and is idempotent", () => {
  const once = presentInlines([{ t: "text", v: "{\\bf" }, { t: "text", v: " " }, { t: "text", v: "Parser}" }]);
  assert.equal(text(once), "**Parser**");
  const twice = presentInlines(once);
  assert.equal(text(twice), text(once));
});
