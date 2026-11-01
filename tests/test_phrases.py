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


def test_commit_survives_a_reload_that_drops_uncommitted_files(tmp_path):
    import json
    import numpy as np
    from rrm.reader.similar import commit_phrases, read_vectors, text_rows
    from rrm.reader.phrases import read_phrases

    folder = tmp_path / "7"
    remote = tmp_path / "remote"
    folder.mkdir()
    remote.mkdir()
    (folder / "paper.json").write_text(json.dumps(_paper()), encoding="utf-8")

    def reload():
        for path in list(folder.iterdir()):
            if path.name == "paper.json":
                continue
            if not (remote / path.name).is_file():
                path.unlink()
        for path in remote.iterdir():
            if path.is_file():
                (folder / path.name).write_bytes(path.read_bytes())

    def commit():
        for name in ("phrases.json", "phrases.npy"):
            src = folder / name
            if src.is_file():
                (remote / name).write_bytes(src.read_bytes())

    def encode(texts):
        return np.ones((len(list(texts)), 4), dtype=np.float32)

    # Sin commit, el reload se lleva el archivo. Es el fallo que vio /ask.
    from rrm.reader.phrases import write_phrases
    write_phrases(folder, _paper())
    reload()
    assert not (folder / "phrases.json").is_file()

    out = commit_phrases(folder, reload, commit, encode=encode)
    assert out["had_phrases"] is False and out["had_vectors"] is False
    assert out["ready"] is True and out["rows"] >= 1
    (folder / "phrases.npy").unlink()
    reload()
    rows = text_rows(read_phrases(folder))
    assert read_vectors(folder, len(rows)) is not None


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


def test_stored_vectors_encode_only_the_query():
    from rrm.reader.similar import local_encode, rank_similar

    rows = [
        {"paper": 7, "text": "Attention is all you need for this model."},
        {"paper": 8, "text": "We scale the learning rate with data."},
    ]
    stored = local_encode([row["text"] for row in rows])
    seen = []

    def encode(texts):
        seen.extend(texts)
        return local_encode(texts)

    hits, _total = rank_similar(rows, "attention model", encode, vectors=stored)
    assert seen == ["attention model"]
    assert hits[0]["paper"] == 7


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


def test_open_paper_is_the_only_phrase_pool(monkeypatch):
    from rrm.reader.similar import phrase_ids

    monkeypatch.delenv("RRM_PHRASE_NEIGHBORS", raising=False)
    assert phrase_ids([13756489, 215737171, 220831004], 13756489) == [13756489]
    assert phrase_ids([7, 8], None) == [7, 8]
    monkeypatch.setenv("RRM_PHRASE_NEIGHBORS", "1")
    assert phrase_ids([7, 8, 9], 7) == [7, 8, 9]


def test_abstract_sentence_is_stored_unless_the_flag_is_off(monkeypatch):
    monkeypatch.delenv("RRM_PHRASE_ABSTRACT", raising=False)
    paper = _paper()
    paper["blocks"].insert(0, {
        "kind": "p", "abs": True,
        "sents": [[{"t": "text", "v": "We propose a new simple network architecture, the Transformer."}]],
    })
    texts = [row["text"] for row in collect_phrases(paper)]
    assert "We propose a new simple network architecture, the Transformer." in texts
    monkeypatch.setenv("RRM_PHRASE_ABSTRACT", "0")
    skipped = [row["text"] for row in collect_phrases(paper)]
    assert "We propose a new simple network architecture, the Transformer." not in skipped


def test_literal_abstract_beats_a_closer_neighbor():
    import numpy as np
    from rrm.reader.similar import rank_similar

    abstract = "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms."
    rows = [
        {"paper": 7, "text": abstract},
        {"paper": 8, "text": "Longformer attends with a sliding window over the sequence."},
    ]
    stored = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)

    def encode(texts):
        assert texts == [abstract]
        return np.array([[1.0, 0.0]], dtype=np.float32)

    hits, _total = rank_similar(rows, abstract, encode, vectors=stored)
    assert hits[0]["paper"] == 7
    assert abstract in hits[0]["text"]


def test_folder_id_fills_a_missing_paper_id(tmp_path):
    import json
    import numpy as np
    from rrm.reader.similar import load_aligned

    folder = tmp_path / "7"
    folder.mkdir()
    (folder / "phrases.json").write_text(json.dumps({
        "rows": [{"text": "We propose a new simple network architecture, the Transformer."}],
    }), encoding="utf-8")
    np.save(folder / "phrases.npy", np.ones((1, 4), dtype=np.float32))
    rows, _vecs, missing = load_aligned(tmp_path, [7])
    assert missing is False
    assert rows[0]["paper"] == 7


def test_commit_appends_the_abstract_without_reencoding_the_rest(tmp_path):
    import json
    import numpy as np
    from rrm.reader.phrases import read_phrases
    from rrm.reader.similar import commit_phrases, read_vectors, text_rows

    folder = tmp_path / "7"
    folder.mkdir()
    abstract = "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms."
    paper = {
        "corpusid": 7,
        "blocks": [
            {"kind": "p", "abs": True, "sents": [[{"t": "text", "v": abstract}]]},
            {"kind": "p", "sents": [[{"t": "text", "v": "We scale with "}, {"t": "math", "v": r"\alpha"}, {"t": "text", "v": "."}]]},
        ],
    }
    (folder / "paper.json").write_text(json.dumps(paper), encoding="utf-8")
    (folder / "phrases.json").write_text(json.dumps({
        "paper": 7,
        "rows": [{"paper": 7, "text": r"We scale with $\alpha$.", "latex": [r"\alpha"], "section": ""}],
    }), encoding="utf-8")
    np.save(folder / "phrases.npy", np.ones((1, 4), dtype=np.float32))
    seen = []

    def encode(texts):
        seen.extend(texts)
        return np.full((len(list(texts)), 4), 0.5, dtype=np.float32)

    out = commit_phrases(folder, lambda: None, lambda: None, encode=encode)
    assert out["ready"] is True
    assert seen == [abstract]
    rows = text_rows(read_phrases(folder))
    assert rows[-1]["text"] == abstract
    assert read_vectors(folder, len(rows)).shape[0] == 2


def test_review_failure_is_not_an_empty_200(monkeypatch):
    from rrm.reader.verify import ask_error_text, ask_http

    monkeypatch.setenv("MODEL_API_KEY", "sekret-no-log")
    assert "sekret" not in ask_error_text("muse http 500: sekret-no-log Bearer abc https://api.meta.ai/v1")
    code, payload = ask_http(
        {"note": "Sin retroalimentación: no hubo red.", "parts": {"coincide": [], "contradice": [], "sin_respaldo": [], "te_falto": []}},
        "revisar",
    )
    assert code == 502 and payload["error"].startswith("Sin retroalimentación")
    ok, body = ask_http({"note": "", "parts": {"sin_respaldo": [{"text": "x"}]}}, "revisar")
    assert ok == 200 and body["parts"]["sin_respaldo"]
