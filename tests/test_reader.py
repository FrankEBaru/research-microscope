"""Seconds-long checks for the reader parser. No network, Modal, or model download."""

import io
import tarfile
from pathlib import Path

from rrm.reader.fetch import Limiter, canon_arxiv, unpack_eprint
from rrm.reader.katex import katex_available
from rrm.reader.latex import (
    attach_katex,
    collect_macros,
    expand_math,
    is_pdfpages_wrapper,
    materialize_figures,
    parse_tex,
    parse_tree,
    plain,
)
from rrm.reader.ocr import blocks_from_content_list
from rrm.reader.pipeline import abstract_paper, mark_queued
from rrm.reader.sam import parse_sam_text, segment_pdf

MACRO = r"""
\documentclass{article}
\newcommand{\vect}[1]{\mathbf{#1}}
\DeclareMathOperator{\argmax}{arg\,max}
\begin{document}
\begin{equation}
y = \vect{x} + \argmax
\label{eq:y}
\end{equation}
See \eqref{eq:y}.
\end{document}
"""

INPUT_MAIN = r"""
\documentclass{article}
\begin{document}
\input{sec}
\end{document}
"""

FIGURE = r"""
\documentclass{article}
\begin{document}
\section{Intro}
\label{sec:intro}
\section*{Notes}
\begin{figure*}
\includegraphics{plot.pdf}
\caption{The plot of $x$.}
\label{fig:p}
\end{figure*}
\begin{weirdstuff}
keep me
\end{weirdstuff}
\end{document}
"""

WRAPPER = r"""
\documentclass{article}
\usepackage{pdfpages}
\begin{document}
\includepdf[pages=-]{adam.pdf}
\end{document}
"""

REAL = r"""
\documentclass{article}
\usepackage{pdfpages}
\begin{document}
\includepdf[pages=-]{card.pdf}
This paper still has a real discussion of training language models on mixed data
with an actual equation in the body so it must stay on the TeX path for parsing.
\begin{equation}
L = -\sum_i y_i
\end{equation}
\end{document}
"""


def test_macro_expansion_and_label_link():
    macros = collect_macros(MACRO)
    assert expand_math(r"\vect{x}+\argmax", macros) == r"\mathbf{x}+\operatorname{arg\,max}"
    paper = parse_tex(MACRO, arxiv_id="0")
    eqs = [b for b in paper["blocks"] if b["kind"] == "eq"]
    assert len(eqs) == 1
    assert r"\mathbf{x}" in eqs[0]["tex"]
    assert r"\operatorname{arg\,max}" in eqs[0]["tex"]
    assert eqs[0]["label"] == "eq:y"
    assert eqs[0]["number"] == 1
    refs = [x for b in paper["blocks"] if b["kind"] == "p" for x in b["inlines"] if x["t"] == "ref"]
    assert refs and refs[0]["target"] == eqs[0]["id"]
    assert refs[0]["number"] == 1
    if katex_available():
        attach_katex(paper["blocks"])
        assert eqs[0]["katex_ok"] is True


def test_input_inlining(tmp_path: Path):
    (tmp_path / "main.tex").write_text(INPUT_MAIN)
    (tmp_path / "sec.tex").write_text("Hello world from the section file.\n")
    parsed = parse_tree(tmp_path, arxiv_id="1")
    assert parsed["route"] == "latex"
    text = " ".join(plain(b["inlines"]) for b in parsed["paper"]["blocks"] if b["kind"] == "p")
    assert "Hello world from the section file" in text


def test_figure_star_section_star_and_raw(tmp_path: Path):
    (tmp_path / "main.tex").write_text(FIGURE)
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=120, height=80)
    page.insert_text((10, 40), "plot")
    doc.save(tmp_path / "plot.pdf")
    doc.close()
    parsed = parse_tree(tmp_path)
    paper = parsed["paper"]
    kinds = {b["kind"] for b in paper["blocks"]}
    assert kinds <= {"p", "h", "eq", "list", "fig", "table"}
    heads = [b for b in paper["blocks"] if b["kind"] == "h"]
    assert heads[0]["number"] == "1" and heads[0]["unnumbered"] is False
    assert heads[0]["label"] == "sec:intro"
    assert heads[1]["unnumbered"] is True and heads[1]["number"] is None
    fig = next(b for b in paper["blocks"] if b["kind"] == "fig")
    assert fig["label"] == "fig:p"
    assert "plot" in plain(fig["caption"]).lower() or "$x$" in plain(fig["caption"])
    raw = [b for b in paper["blocks"] if b.get("raw")]
    assert raw and "keep me" in plain(raw[0]["inlines"])
    n = materialize_figures(paper["blocks"], tmp_path, tmp_path / "figures")
    assert n == 1
    assert list((tmp_path / "figures").glob("*.png"))


def test_theorem_and_list_keep_display_math():
    tex = r"""
\documentclass{article}
\newtheorem{lem}{Lemma}
\begin{document}
\begin{lem}\label{lem:one}
A transformer computes
\begin{align}
a &= b \label{eq:ab}
\end{align}
\end{lem}
\begin{enumerate}
\item Kept iff
\[z = z\]
\end{enumerate}
\end{document}
"""
    paper = parse_tex(tex)
    eqs = [b for b in paper["blocks"] if b["kind"] == "eq"]
    assert [b["tex"].replace(" ", "") for b in eqs] == ["a&=b", "z=z"] or "a" in eqs[0]["tex"]
    assert any("a" in b["tex"] and "b" in b["tex"] for b in eqs)
    assert any(b["tex"].replace(" ", "") == "z=z" for b in eqs)
    assert any(b.get("label") == "eq:ab" for b in eqs)
    assert any(b["kind"] == "list" for b in paper["blocks"])


def test_pdfpages_wrapper_versus_real_tex():
    assert is_pdfpages_wrapper(WRAPPER)
    assert not is_pdfpages_wrapper(REAL)


def test_def_bracket_is_not_display_math():
    tex = r"""
\documentclass{article}
\def\[{\left[}
\begin{document}
The token \[ is a macro here, and \[x\] should not vanish.
\end{document}
"""
    paper = parse_tex(tex)
    text = " ".join(plain(b.get("inlines") or []) for b in paper["blocks"])
    assert "should not vanish" in text
    assert not any(b["kind"] == "eq" for b in paper["blocks"])


def test_unpack_eprint_tar_and_pdf(tmp_path: Path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = b"\\documentclass{article}\\begin{document}Hi\\end{document}\n"
        info = tarfile.TarInfo("main.tex")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    kind = unpack_eprint(buf.getvalue(), tmp_path / "tex")
    assert kind == "tex"
    assert (tmp_path / "tex" / "main.tex").is_file()
    kind = unpack_eprint(b"%PDF-1.4 fake", tmp_path / "pdf")
    assert kind == "pdf"
    assert (tmp_path / "pdf" / "source.pdf").read_bytes().startswith(b"%PDF")


def test_limiter_uses_the_injected_clock():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    lim = Limiter(3.2, sleep=sleep, now=lambda: now[0])
    lim.wait()
    lim.wait()
    assert slept == [3.2]
    assert canon_arxiv("arXiv:1706.03762v5") == "1706.03762"


def test_ocr_content_list_matches_schema():
    blocks = blocks_from_content_list([
        {"type": "text", "text": "Introduction", "text_level": 1},
        {"type": "equation", "text": "$$E = mc^2$$"},
        {"type": "image", "img_path": "images/a.png", "image_caption": ["Figure 1: a plot"]},
        {"type": "table", "table_caption": ["Table 1"], "table_body": "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"},
        {"type": "header", "text": "running head"},
    ])
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["h", "eq", "fig", "table"]
    eq = next(b for b in blocks if b["kind"] == "eq")
    assert eq["tex"] == "E = mc^2" and eq["source"] == "ocr"
    assert all(b["id"].startswith("b") for b in blocks)
    table = next(b for b in blocks if b["kind"] == "table")
    assert plain(table["head"][0][0]) == "a"
    assert plain(table["body"][0][1]) == "2"


def test_sam_parser_and_missing_key(tmp_path: Path, monkeypatch):
    text = (
        "<0f>0<|box;x1=10;y1=20;x2=40;y2=50;w=100;h=80;c=0.9|>"
        "<|mask;x=0;y=0;c=0.9;data=4,5,!abcd|>,"
        "1<|box;x1=1;y1=1;x2=2;y2=2;w=100;h=80|>"
    )
    hits = parse_sam_text(text)
    assert hits[0]["x1"] == 10 and hits[0]["y2"] == 50 and hits[0]["c"] == 0.9
    assert hits[0]["mask"].startswith("4,5,!")
    assert hits[1]["x2"] == 2
    assert parse_sam_text("") == []
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    pdf = tmp_path / "empty.pdf"
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=100, height=100)
    doc.save(pdf)
    doc.close()
    out = segment_pdf(pdf, tmp_path / "crops", max_pages=1)
    assert out["crops"] == [] and out["error"] == "no MODEL_API_KEY"
    assert (tmp_path / "crops" / "index.json").is_file()


def test_queue_and_abstract_shape(tmp_path: Path):
    assert mark_queued(tmp_path / "5", 5) == "queued"
    assert mark_queued(tmp_path / "5", 5) == "queued"
    paper = abstract_paper({"corpusid": 5, "title": "T", "abstract": "Hello there.", "tldr": "short"})
    assert paper["full"] is False and paper["source"] == "abstract"
    assert paper["blocks"][0]["kind"] == "p"
