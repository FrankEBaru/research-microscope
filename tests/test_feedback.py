"""Parseo, verificador de dos capas y modo sin Meta. Sin red real."""

import json

from rrm.reader.cites import bind_cites
from rrm.reader.feedback import layer1, layer2, review
from rrm.reader.metacall import parse_json
from rrm.reader.phrases import store_progress
from rrm.reader.verify import answer


CITES = [
    {"paper": 7, "text": "Attention is all you need for this model."},
    {"paper": 8, "text": "We scale the learning rate with data."},
]


def _payload(text, usage=None):
    return {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": usage or {"input_tokens": 10, "output_tokens": 4, "input_tokens_details": {"cached_tokens": 2}},
    }


def test_parse_json_accepts_fences_and_rejects_prose():
    assert parse_json('```json\n{"coincide": []}\n```')["coincide"] == []
    assert parse_json("no es json") is None


def test_layer1_drops_foreign_papers_and_loose_quotes():
    raw = {
        "coincide": [
            {"text": "Sí habla de atención.", "cite": "Attention is all you need", "paper_id": "7"},
            {"text": "Inventado.", "cite": "this sentence is not in the paper", "paper_id": "7"},
            {"text": "Otro corpus.", "cite": "Attention is all you need", "paper_id": "99"},
        ],
        "contradice": [{"text": "Choca.", "cite": "Attention is all you need", "paper_id": "7"}],
        "sin_respaldo": [{"text": "Menciona un dataset que no está."}],
        "te_falto": [{"text": "Falta el learning rate.", "cite": "learning rate with data", "paper_id": "8"}],
    }
    kept = layer1(raw, CITES)
    assert len(kept["coincide"]) == 1
    assert kept["coincide"][0]["paper_id"] == "7"
    assert kept["sin_respaldo"][0]["text"].startswith("Menciona")
    assert kept["te_falto"][0]["paper_id"] == "8"
    assert "99" not in json.dumps(kept)


def test_layer2_mock_drops_a_no_and_rejects_a_short_list():
    parts = layer1({
        "coincide": [{"text": "Atención.", "cite": "Attention is all you need", "paper_id": "7"}],
        "contradice": [],
        "sin_respaldo": [{"text": "Nada de esto."}],
        "te_falto": [],
    }, CITES)
    kept = layer2(parts, [True, False])
    assert len(kept["coincide"]) == 1 and kept["coincide"][0]["verified"] is True
    assert kept["sin_respaldo"] == []
    assert layer2(parts, [True]) is None


def test_without_meta_the_box_keeps_extracts(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("RRM_META", raising=False)

    def explode(*_a, **_k):
        raise AssertionError("red")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    body = answer(CITES, "attention model")
    assert body["empty"] is False
    assert body["parts"]["coincide"] == []
    assert "no hay clave" in body["note"]
    monkeypatch.setenv("RRM_META", "0")
    parts, note, _cost = review("attention", CITES, complete=explode)
    assert parts["coincide"] == []
    assert "apagado" in note


def test_review_keeps_layer1_when_the_second_check_does_not_parse():
    calls = {"n": 0}

    def complete(body):
        calls["n"] += 1
        assert body["reasoning"]["effort"] == "minimal"
        if calls["n"] == 1:
            raw = {
                "coincide": [{"text": "Habla de atención.", "cite": "Attention is all you need", "paper_id": "7"}],
                "contradice": [],
                "sin_respaldo": [],
                "te_falto": [],
            }
            return _payload(json.dumps(raw))
        return _payload("no")

    parts, note, cost = review("el modelo usa atención", CITES, complete=complete)
    assert calls["n"] == 2
    assert len(parts["coincide"]) == 1
    assert parts["coincide"][0]["text"] == "Habla de atención."
    assert "No pude leer" not in note
    assert note == ""
    assert cost["input_tokens"] == 20
    assert cost["cost_usd"] > 0


def test_each_claim_is_classified_and_a_loose_gap_is_dropped():
    cites = [dict(row) for row in CITES]
    cites[0]["section"] = "3.2 Attention"
    raw = {
        "afirmaciones": [
            {"text": "Habla de atención.", "clase": "coincide", "cite": "Attention is all you need", "paper_id": "7"},
            {"text": "Niega la atención.", "clase": "contradice", "cite": "Attention is all you need", "paper_id": "7"},
            {"text": "Menciona un dataset que no está.", "clase": "sin_respaldo"},
        ],
        "te_falto": [
            {"text": "Falta el learning rate.", "cite": "learning rate with data", "paper_id": "8"},
            {"text": "Inventa un optimizador cuántico.", "cite": "learning rate with data", "paper_id": "8"},
        ],
    }
    kept = layer1(raw, cites)
    assert kept["coincide"][0]["text"] == "Habla de atención."
    assert kept["coincide"][0]["section"] == "3.2 Attention"
    assert kept["contradice"][0]["text"] == "Niega la atención."
    assert kept["sin_respaldo"][0]["text"].startswith("Menciona")
    assert [row["text"] for row in kept["te_falto"]] == ["Falta el learning rate."]


def test_store_counts_phrases_with_text(tmp_path):
    (tmp_path / "7").mkdir()
    (tmp_path / "7" / "phrases.json").write_text(
        '{"rows":[{"text":"Attention is all you need."}]}', encoding="utf-8",
    )
    (tmp_path / "8").mkdir()
    (tmp_path / "8" / "phrases.json").write_text("{}", encoding="utf-8")
    assert store_progress(tmp_path, [7, 8, 9]) == {"ready": 1, "total": 3}


def test_bibtex_key_resolves_by_title_and_year():
    graph = {"s2:42": "2014. Learning Phrase Representations with RNN"}
    bib = {"Cho2014a": "Cho, K. 2014. Learning Phrase Representations with RNN Encoder-Decoder."}
    assert bind_cites(bib, graph)["Cho2014a"] == "s2:42"
    assert "Other" not in bind_cites({"Other": "Unrelated title 1999."}, graph)


def test_query_vector_skips_a_second_encode():
    from rrm.search.labels import cosines_for

    def encode(_texts):
        raise AssertionError("encode")

    scores = cosines_for([1], encode, lambda cid: [1.0, 0.0], "pregunta", query_vec=[1.0, 0.0])
    assert scores[1] > 0.99


def test_cache_merge_keeps_burst_and_papers(tmp_path):
    import threading

    from rrm.search.qcache import load_entry, save_entry

    def burst():
        save_entry(tmp_path, "race", burst={"n": 1, "papers": [{"corpusid": 1}]})

    def papers():
        save_entry(tmp_path, "race", papers={"1": {"id": 1, "status": "done"}})

    threads = [threading.Thread(target=burst), threading.Thread(target=papers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    got = load_entry(tmp_path, "race")
    assert got["burst"]["n"] == 1
    assert got["papers"]["1"]["status"] == "done"
