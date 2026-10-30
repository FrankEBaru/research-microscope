"""What /paper bundles carry for the new UI. Uses the real parsers on small sources. No network."""

from rrm.reader.latex import parse_tex
from rrm.reader.ocr import blocks_from_content_list
from rrm.reader.pipeline import abstract_paper

TEX = r"""
\documentclass{article}
\begin{document}
\begin{abstract}
We study scaling. Loss falls as a power law in compute.
\end{abstract}
\section{Results}
Loss falls with size. It also falls with data.
\begin{figure}
\includegraphics{plot.png}
\caption{Loss.}
\label{fig:loss}
\end{figure}
\begin{table}
\caption{Scores.}
\label{tab:s}
\begin{tabular}{lcc}
\toprule
 & \multicolumn{2}{c}{Accuracy} \\
Model & A & B \\
\midrule
Base & 1 & 2 \\
\multicolumn{3}{l}{All rows} \\
\bottomrule
\end{tabular}
\end{table}
\end{document}
"""


def test_latex_bundle_has_sents_abs_and_fig_label():
    paper = parse_tex(TEX, arxiv_id="1706.03762")
    assert paper["arxivId"] == "1706.03762"
    blocks = paper["blocks"]
    assert blocks[0].get("abs") is True
    ps = [b for b in blocks if b["kind"] == "p"]
    assert ps and all(len(b["sents"]) >= 1 for b in ps)
    assert len(ps[0]["sents"]) == 2
    fig = next(b for b in blocks if b["kind"] == "fig")
    assert fig["label"] == "fig:loss"
    assert fig["images"] == ["plot.png"]


def test_latex_table_keeps_colspan():
    paper = parse_tex(TEX)
    tab = next(b for b in paper["blocks"] if b["kind"] == "table")
    assert tab["hspan"] == [[1, 2]]
    assert tab["bspan"] == [[1, 1, 1], [1, 1, 1], [3]]
    for rows, spans in ((tab["head"], tab["hspan"]), (tab["body"], tab["bspan"])):
        assert [len(r) for r in rows] == [len(s) for s in spans]


def test_table_without_merged_cells_has_no_span_fields():
    tex = TEX.replace(r"\multicolumn{2}{c}{Accuracy}", "Accuracy &").replace(r"\multicolumn{3}{l}{All rows}", "x & y & z")
    tab = next(b for b in parse_tex(tex)["blocks"] if b["kind"] == "table")
    assert "hspan" not in tab and "bspan" not in tab


def test_ocr_table_keeps_colspan():
    html = '<table><tr><th></th><th colspan="2">Acc</th></tr><tr><td>m</td><td>a</td><td>b</td></tr></table>'
    blocks = blocks_from_content_list([{"type": "table", "table_body": html, "table_caption": ["T"]}])
    tab = next(b for b in blocks if b["kind"] == "table")
    assert tab["hspan"] == [[1, 2]]
    assert tab["bspan"] == [[1, 1, 1]]


def test_abstract_only_paper_has_abs_block_with_sents():
    paper = abstract_paper({"arxiv": "1706.03762", "corpusid": 7, "abstract": "One. Two.", "title": "T"})
    b = paper["blocks"][0]
    assert b["abs"] is True and b["sents"] and paper["arxivId"] == "1706.03762"
