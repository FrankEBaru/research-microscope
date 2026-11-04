import test from "node:test";
import assert from "node:assert/strict";
import { liftCiteKeys, parseProse, polishText, presentInlines, splitIntertext, visibleInlines, pdfPagesOnly } from "../src/lib/prose.js";

const text = (nodes) => nodes.map((n) => n.t === "text" ? n.v : n.t === "em" ? `*${text(n.c)}*` : n.t === "strong" ? `**${text(n.c)}**` : n.t === "math" ? `$${n.v}$` : n.t === "cite" ? `[@${n.keys.join(",")}]` : n.t === "ref" ? `#${n.label}` : "").join("");

test("natbib, table notes and a repeated symbol do not stay raw", () => {
  const nat = parseProse("learning \\begingroup\\NAT@swatrue\\NAT@ctype\\z@\\NAT@partrue Brown2020LanguageMA.");
  assert.equal(nat.some((n) => n.t === "cite" && n.keys[0] === "Brown2020LanguageMA"), true);
  assert.equal(nat.some((n) => n.t === "text" && /NAT@/.test(n.v)), false);
  const braced = parseProse("see \\begingroup\\NAT@swafalse\\@ifnextchar[{[]}{Brown2020LanguageMA}");
  assert.equal(braced.some((n) => n.t === "cite" && n.keys[0] === "Brown2020LanguageMA"), true);
  assert.equal(text(parseProse("a learner \\tnote{edited, unclear} remains")), "a learner remains");
  assert.equal(text(parseProse("words \\tnote{edited, unclear what a learner is")), "words edited, unclear what a learner is");
  const mov = parseProse("\\textbf{\\texttt{mov}}(H; s)");
  assert.equal(mov.some((n) => n.t === "strong" || n.t === "code"), true);
  assert.equal(mov.some((n) => n.t === "text" && /textbf|texttt/.test(n.v)), false);
  const echo = presentInlines([{ t: "math", v: "\\theta" }, { t: "text", v: "θ to denote" }]);
  assert.equal(text(echo), "$\\theta$ to denote");
  const dd = presentInlines([{ t: "math", v: "d" }, { t: "text", v: "d-dimensional" }]);
  assert.equal(text(dd), "$d$-dimensional");
  const parts = splitIntertext("a &= b \\\\ \\intertext{where each head is} c &= d");
  assert.equal(parts[1].t, "text");
  assert.match(parts[1].v, /where each head/);
  assert.equal(parts.filter((p) => p.t === "math").length, 2);
});

test("titles and paren math stay as nodes the body renderer can draw", () => {
  const nodes = presentInlines([{ t: "text", v: "\\texttt{OLMo}: Paper de prueba $L_2$" }]);
  assert.equal(nodes.some((n) => n.t === "text" && n.v.includes("OLMo")), true);
  assert.equal(nodes.some((n) => n.t === "math" && n.v === "L_2"), true);
  assert.equal(nodes.some((n) => n.t === "text" && /\\texttt/.test(n.v)), false);
  const paren = parseProse("see \\(L_2\\) now");
  assert.equal(paren.some((n) => n.t === "math" && n.v === "L_2" && !n.display), true);
});

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

test("author asides, loose formulas, labels and echoed math are one class of bug", () => {
  const aside = parseProse("kept. \\ekin{I don't have strong opinion, but this was where they start looking Figure 1, so this was ok to me.} Next.");
  assert.equal(text(aside).includes("strong opinion"), false);
  assert.match(text(aside), /kept\./);
  assert.match(text(aside), /Next/);
  const paragraph = parseProse("\\paragraph{The results show that this method works on the benchmark and we report them.}");
  assert.match(text(paragraph), /results show/);
  const prop = presentInlines([{ t: "text", v: "See prop:main and cor:bound." }]);
  assert.deepEqual(prop.filter((n) => n.t === "ref").map((n) => n.label), ["prop:main", "cor:bound"]);
  const gelu = parseProse("a unit \\Big(\\frac{x}{\\sqrt{2}}\\Big)\\Big) here");
  assert.equal(gelu.some((n) => n.t === "math" && n.v.includes("\\frac") && !/\\Big\)\\Big\)/.test(n.v)), true);
  assert.equal(text(parseProse("and σσ denotes")), "and σ denotes");
  const sig = presentInlines([{ t: "math", v: "\\sigma" }, { t: "text", v: "σ denotes" }]);
  assert.equal(text(sig), "$\\sigma$ denotes");
  const mov = presentInlines([{ t: "math", v: "\\textbf{\\texttt{div}}(H; (i, j), i')" }]);
  assert.equal(JSON.stringify(mov).includes("textbf"), false);
  assert.equal(JSON.stringify(mov).includes("texttt"), false);
  assert.match(JSON.stringify(mov), /"v":"div"/);
  const echo = presentInlines([{ t: "math", v: "f(x_n)" }, { t: "text", v: "f(xn) to predictions" }]);
  assert.equal(text(echo), "$f(x_n)$ to predictions");
  const labels = presentInlines([{ t: "text", v: "Proofs are given in app:Thm1,,app:Thm2." }]);
  assert.deepEqual(labels.filter((n) => n.t === "ref").map((n) => n.label), ["app:Thm1", "app:Thm2"]);
  const fig = presentInlines([{ t: "text", v: "In fig:implicitw, the curve" }]);
  assert.equal(fig.some((n) => n.t === "ref" && n.label === "fig:implicitw"), true);
  assert.equal(text(parseProse("ends [cite].")), "ends .");
});

test("presentInlines merges split tokens and is idempotent", () => {
  const once = presentInlines([{ t: "text", v: "{\\bf" }, { t: "text", v: " " }, { t: "text", v: "Parser}" }]);
  assert.equal(text(once), "**Parser**");
  const twice = presentInlines(once);
  assert.equal(text(twice), text(once));
});

test("RRM-103: a display environment inside a raw paragraph renders as display math", () => {
  const toks = "We define the projection $f$ as \\begin{equation} f(r; \\piref, \\beta)(x, y) = r(x, y) - \\beta\\log\\sum_{y}\\piref(y\\mid x) \\label{eq:proj} \\end{equation} The operator $f$ normalizes."
    .split(/( )/).filter(Boolean).map((v) => ({ t: "text", v }));
  const out = presentInlines(toks);
  const disp = out.filter((n) => n.t === "math" && n.display);
  assert.equal(disp.length, 1);
  assert.match(disp[0].v, /^f\(r; \\piref, \\beta\)\(x, y\) = r\(x, y\)/);
  assert.doesNotMatch(disp[0].v, /label/);
  const words = out.filter((n) => n.t === "text").map((n) => n.v).join("");
  assert.doesNotMatch(words, /\\piref|\\beta|equation/);
  const al = presentInlines([{ t: "text", v: "so \\begin{align*} a &= b \\\\ c &= d \\end{align*} done" }]).find((n) => n.t === "math");
  assert.equal(al.display, true);
  assert.match(al.v, /^\\begin\{aligned\}a &= b \\\\ c &= d\\end\{aligned\}$/);
});

test("RRM-103: bare BibTeX keys of the paper become citations; ordinary words do not", () => {
  const refs = { su2022roformer: 1, "yu-etal:2018:_qanet": 2, bidaf: 3, shazeer2019mq: 4 };
  const out = liftCiteKeys([{ t: "text", v: "embeddings (RoPE, su2022roformer). As in yu-etal:2018:_qanet, the bidaf model and shazeer2019mq or shazeer2019mqx." }], refs);
  assert.deepEqual(out.filter((n) => n.t === "cite").map((n) => n.keys[0]), ["su2022roformer", "yu-etal:2018:_qanet", "shazeer2019mq"]);
  assert.equal(text(out.filter((n) => n.t === "text")).includes("bidaf"), true);
  assert.equal(text(out.filter((n) => n.t === "text")).includes("shazeer2019mqx"), true);
  assert.deepEqual(liftCiteKeys([{ t: "text", v: "no keys" }], {}), [{ t: "text", v: "no keys" }]);
});

test("RRM-103: \\textellipsis, \\textgreater and booktabs row spacing are not left raw", () => {
  const out = text(presentInlines([{ t: "text", v: "RLHF-V1, \\textellipsis, RLHF-V5 with \\textgreater= 0.005% here.\\\\[\\heavyrulewidth] Prompt:" }]));
  assert.doesNotMatch(out, /\\text|heavyrulewidth/);
  assert.match(out, /RLHF-V1, …, RLHF-V5 with >= 0.005% here\./);
});

test("RRM-103: a braced umlaut keeps its letter", () => {
  assert.equal(text(presentInlines([{ t: "text", v: "the Nystr{\\\"o}mformer and Nystr\\\"omformer baselines" }])), "the Nyströmformer and Nyströmformer baselines");
});

test("RRM-103: \\hdots (FlashAttention §3.1) is a known macro", async () => {
  const { TEX_MACROS } = await import("../src/lib/texcolor.js");
  assert.equal(TEX_MACROS["\\hdots"], "\\ldots");
});

test("RRM-103: algorithm captions, nested \\IF arguments and layout leftovers", () => {
  const cap = text(presentInlines([{ t: "text", v: "\\caption{\\small\\label{alg:x}Standard Attention Implementation} \\REQUIRE Matrices" }]));
  assert.match(cap, /^\s*Standard Attention Implementation Require: Matrices/);
  const step = presentInlines([{ t: "text", v: "\\IF{$M_{ij} \\neq 0$} Load the block." }]);
  assert.equal(step.some((n) => n.t === "math" && n.v === "M_{ij} \\neq 0"), true);
  assert.doesNotMatch(text(step), /\\IF/);
  const junk = text(presentInlines([{ t: "text", v: "details. \\@startsection{paragraph}{4}{\\z@} {1.5ex \\@plus 0.5ex} {-1em} Next [\\dots] TL;DR *{\\baselineskip} We" }]));
  assert.doesNotMatch(junk, /paragraph|1\.5ex|baselineskip|\\dots/);
  assert.match(junk, /\[…\] TL;DR/);
});
