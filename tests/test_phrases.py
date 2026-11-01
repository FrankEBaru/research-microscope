"""Almacén de frases, búsqueda y verificador. Sin red."""

import urllib.request

from rrm.reader.phrases import collect_phrases, query_tokens, rank_phrases, search_phrases, write_phrases
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


def test_symbol_letter_is_capped_and_not_a_substring():
    rows = [
        {"paper": 1, "text": "We keep the keys.", "latex": ["K"]},
        {"paper": 1, "text": "Another K here.", "latex": ["K"]},
        {"paper": 1, "text": "Third K.", "latex": ["K"]},
        {"paper": 1, "text": "Fourth K is past the cap.", "latex": ["K"]},
        {"paper": 2, "text": "The word keep has no symbol.", "latex": []},
    ]
    hits, total = rank_phrases(rows, "$K$")
    assert total == 4
    assert len(hits) == 3
    assert all(row["paper"] == 1 for row in hits)


def test_spanish_and_english_rank_the_matching_english_phrase():
    from rrm.reader.similar import rank_similar

    rows = [
        {"paper": 7, "text": "Attention is all you need for this model."},
        {"paper": 8, "text": "We scale the learning rate with data."},
        {"paper": 99, "text": "Photosynthesis converts sunlight into sugar."},
    ]
    spanish, _total = rank_similar(rows, "La atención basta para este modelo.")
    english, _total = rank_similar(rows, "We scale the learning rate with data.")
    assert spanish[0]["paper"] == 7
    assert english[0]["paper"] == 8


def test_similar_does_not_encode_papers_outside_the_store():
    from rrm.reader.similar import local_encode, rank_similar

    seen = []

    def encode(texts):
        seen.extend(texts)
        return local_encode(texts)

    rows = [
        {"paper": 7, "text": "Attention is all you need for this model."},
        {"paper": 8, "text": "We scale the learning rate with data."},
    ]
    rank_similar(rows, "La atención basta para este modelo.", encode)
    blob = " ".join(seen)
    assert "Attention is all you need" in blob
    assert "Photosynthesis" not in blob


def test_phrase_stage_skips_meta(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("meta")

    monkeypatch.setattr("rrm.reader.feedback.review", explode)
    rows = [{"paper": 7, "text": "Attention is all you need for this model."}]
    body = answer(rows, "La atención basta para este modelo.", stage="frases")
    assert body["extracts"][0]["paper"] == 7
    assert body["parts"]["coincide"] == []
    assert body["note"] == ""


def test_linea_final_is_empty_and_does_not_touch_the_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("red")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    cites = [{"paper": 7, "text": "attention is all you need"}]
    assert linea_final(cites) == ""
    body = answer(cites, "attention")
    assert body["line"] == ""
    assert body["papers"] == 1
    assert body["empty"] is False
    assert body["parts"]["coincide"] == []
    assert "Sin retroalimentación" in body["note"]
