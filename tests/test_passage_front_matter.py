"""El parser de pasajes no guarda la portada. El flag es el de la búsqueda."""

import pytest

from rrm.passages.rows import extract_rows


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


def test_extract_rows_keeps_preamble_when_flag_off(monkeypatch):
    monkeypatch.setenv("RRM_PASSAGES_FILTER_JUNK", "0")
    rows = extract_rows(_paper(), arxiv_id="1")
    assert any(r"\icmlaffiliation" in row["text"] for row in rows)
    eqs = [row for row in rows if row["kind"] == "eq"]
    assert r"\icmlaffiliation" in eqs[0]["text"]
