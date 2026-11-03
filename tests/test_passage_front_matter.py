"""El parser de pasajes no guarda la portada. El flag es el de la búsqueda."""

import pytest

from rrm.passages.rows import extract_rows
from rrm.reader.passage_junk import is_junk_passage


def _text(value):
    return [{"t": "text", "v": value}]


def _paper():
    junk = r"\icmlaffiliation{yyy}{Meta}"
    after = "The scale keeps the product of queries and keys from growing too fast."
    body = (
        "Direct preference optimization trains a policy from pairwise preferences "
        "without fitting an explicit reward model."
    )
    return {
        "corpusid": 7,
        "blocks": [
            {"kind": "h", "level": 1, "inlines": _text("Method")},
            {"kind": "p", "inlines": _text(body), "sents": [_text(body)]},
            {"kind": "p", "inlines": _text(junk), "sents": [_text(junk)]},
            {"kind": "eq", "tex": r"\sqrt{d_k}"},
            {"kind": "p", "inlines": _text(after), "sents": [_text(after)]},
        ],
    }


def test_extract_rows_skips_preamble(monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES_FILTER_JUNK", raising=False)
    rows = extract_rows(_paper(), arxiv_id="1")
    blob = " ".join(row["text"] for row in rows)
    assert r"\icmlaffiliation" not in blob
    assert "yyy" not in blob
    assert any("preference optimization" in row["text"] for row in rows)
    eqs = [row for row in rows if row["kind"] == "eq"]
    assert len(eqs) == 1 and eqs[0]["latex"] == r"\sqrt{d_k}"
    assert "product of queries" in eqs[0]["text"]
    assert "icmlaffiliation" not in eqs[0]["text"]


def test_extract_rows_keeps_footnote_prose_and_drops_layout(monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES_FILTER_JUNK", raising=False)
    note = (
        r"\footnotetext{SimCLR pulls two augmented views of the same image together "
        r"and pushes views of different images apart.}"
    )
    prompt = (
        r"\newcommand{\react}{Claim: the agent interleaves reasoning and actions "
        r"before it searches. Thought: look up the tool.}"
    )
    paper = _paper()
    paper["blocks"] = [
        {"kind": "h", "level": 1, "inlines": _text("Method")},
        {"kind": "p", "inlines": _text(note), "sents": [_text(note)]},
        {"kind": "p", "inlines": _text(prompt), "sents": [_text(prompt)]},
        {"kind": "p", "inlines": _text(r"\onecolumn"), "sents": [_text(r"\onecolumn")]},
        {"kind": "p", "inlines": _text(r"\vskip 0.3in ]"), "sents": [_text(r"\vskip 0.3in ]")]},
        {"kind": "p", "inlines": _text(r"\printAffiliationsAndNotice{}"), "sents": [_text(r"\printAffiliationsAndNotice{}")]},
        {"kind": "p", "inlines": _text(r"\titlerunning{Direct Preference Optimization}"), "sents": [_text(r"\titlerunning{Direct Preference Optimization}")]},
        {"kind": "eq", "tex": r"\sqrt{d_k}"},
        {"kind": "p", "inlines": _text("The scale keeps the product of queries and keys from growing too fast."),
         "sents": [_text("The scale keeps the product of queries and keys from growing too fast.")]},
    ]
    rows = extract_rows(paper, arxiv_id="2002.05709")
    blob = " ".join(row["text"] for row in rows)
    assert "augmented views" in blob
    assert "interleaves reasoning" in blob
    assert r"\onecolumn" not in blob
    assert "printAffiliations" not in blob
    assert "titlerunning" not in blob
    assert any(row["kind"] == "eq" and row["latex"] == r"\sqrt{d_k}" for row in rows)


def test_round3_keeps_notes_definitions_and_teasers():
    kept = [
        r"\footnotetext{Appendix B details the visualization method.}",
        r"\footnotetext{Определение выпуклого множества требует проверки отрезка между точками.}",
        r"\begin{def}A convex set contains the segment between any two of its points.\end{def}",
        r"\twocolumn[{\captionof{figure}{A foundation model for segmentation across many visual domains.}}]",
    ]
    junk = [
        r"\title{Direct Preference Optimization}\thanks{Work done while the authors were visiting a long list of labs.}",
        r"\begin{titlepage}A long title page naming the university and the author.\end{titlepage}",
        r"\titlenote{Equal contribution from the first two authors of this paper.}",
        r"\authorcontributions{A.B. designed the study and wrote the paper with the other authors.}",
        r"\def\convex{A convex set contains every segment between its points and nothing else.}",
        r"\newtheorem{theorem}{Theorem}",
        r"\twocolumn[\icmltitle{Direct Preference Optimization: Your Language Model is Secretly a Reward Model}]",
    ]
    for text in kept:
        assert not is_junk_passage(text), text
    for text in junk:
        assert is_junk_passage(text), text


def test_extract_rows_keeps_preamble_when_flag_off(monkeypatch):
    monkeypatch.setenv("RRM_PASSAGES_FILTER_JUNK", "0")
    rows = extract_rows(_paper(), arxiv_id="1")
    assert any(r"\icmlaffiliation" in row["text"] for row in rows)
    eqs = [row for row in rows if row["kind"] == "eq"]
    assert r"\icmlaffiliation" in eqs[0]["text"]
