"""Almacén de frases, búsqueda y verificador. Sin red."""

import urllib.request

from rrm.reader.phrases import collect_phrases, query_tokens, search_phrases, write_phrases
from rrm.reader.verify import answer, linea_final, verify_line


def _paper():
    return {
        "corpusid": 7,
        "blocks": [
            {"kind": "h", "inlines": [{"t": "text", "v": "Attention"}]},
            {"kind": "p", "sents": [[
                {"t": "text", "v": "We scale with "},
                {"t": "math", "v": r"\alpha"},
                {"t": "text", "v": "."},
            ], [
                {"t": "text", "v": "No symbol in this sentence."},
            ]]},
            {"kind": "p", "sents": [[
                {"t": "text", "v": "The score uses the factor below."},
            ]]},
            {"kind": "eq", "tex": r"\sqrt{d_k}"},
            {"kind": "p", "sents": [[
                {"t": "text", "v": "Another paper says "},
                {"t": "math", "v": r"\beta"},
                {"t": "text", "v": " instead."},
            ]]},
        ],
    }


def test_collect_keeps_symbol_and_equation_sentence():
    rows = collect_phrases(_paper())
    texts = [row["text"] for row in rows]
    assert any(r"\alpha" in row["latex"] for row in rows)
    assert "No symbol in this sentence." not in texts
    assert any("factor below" in text and r"\sqrt{d_k}" in row["latex"] for text, row in zip(texts, rows))
    assert all(row["paper"] == 7 and row["section"] == "Attention" for row in rows)


def test_search_requires_every_word_and_latex_chunk(tmp_path):
    write_phrases(tmp_path, _paper())
    from rrm.reader.phrases import read_phrases
    rows = read_phrases(tmp_path)
    both = search_phrases(rows, r"scale $\alpha$")
    assert len(both) == 1 and r"\alpha" in both[0]["text"]
    other = search_phrases(rows, r"$\beta$")
    assert len(other) == 1 and other[0]["text"] != both[0]["text"]
    assert search_phrases(rows, "missing-word scale") == []
    words, chunks = query_tokens(r"scale $\alpha$")
    assert "scale" in words and chunks == [r"\alpha"]


def test_verifier_drops_a_sentence_missing_from_that_paper():
    cites = [
        {"paper": 1, "text": "attention is all you need"},
        {"paper": 2, "text": "we scale with data"},
    ]
    line = "1: «attention   is\nall you need». 2: «this was never written»."
    kept = verify_line(line, cites)
    assert "attention is all you need" in kept.replace(" ", "") or "attention" in kept
    assert "never written" not in kept
    assert verify_line("therefore invented.", cites) == ""
    assert "attention" in verify_line("attention need.", cites)


def test_linea_final_is_empty_and_does_not_touch_the_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("red")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    cites = [{"paper": 7, "text": "attention is all you need"}]
    assert linea_final(cites) == ""
    body = answer(cites, "attention")
    assert body["line"] == ""
    assert body["papers"] == 1
    assert body["empty"] is False
