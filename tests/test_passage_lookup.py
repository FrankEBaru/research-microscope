"""Lookup de pasajes sin red y sin Modal. La base de prueba es un parquet local."""

import pytest

import rrm.reader.passage_lookup as lookup_mod
from rrm.reader.passage_lookup import adapt_row, lookup


def test_adapt_passage_row():
    row = adapt_row({
        "id": "9:1", "corpusid": 9, "arxiv_id": "1", "kind": "p", "section": "Intro",
        "text": "usa d_k", "latex": "d_k", "license": "", "url": "http://x", "cosine": 0.2,
    })
    assert row == {"id": "9:1", "paper": "9", "section": "Intro", "text": "usa d_k", "latex": "d_k"}


def test_present_absent_and_burst_tie(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES", raising=False)
    fixture = tmp_path / "passages_demo.json"
    fixture.write_text(
        '[{"id":"f1","paper":"10","section":"A","text":"habla de d_k","latex":""},'
        '{"id":"f2","paper":"11","section":"B","text":"también d_k","latex":""}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(lookup_mod, "_FIXTURE", fixture)
    rows = [{"id": "c1", "paper": "3", "section": "S", "text": "local d_k", "latex": []}]
    got = lookup("d_k", rows=rows, burst_ids=["11"])
    assert [row["id"] for row in got] == ["f2", "c1", "f1"]
    assert lookup("no_esta", rows=rows) == []


def test_flag_off_does_not_touch_the_volume(monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("volume")

    monkeypatch.setattr(lookup_mod, "_volume_hits", boom)
    assert lookup("d_k", rows=[{"id": "a", "paper": "1", "section": "", "text": "d_k", "latex": ""}])[0]["id"] == "a"


_CLOSED = (
    "The scaling factor is introduced for a specific reason. "
    + ("More background on the product of queries and keys. " * 20)
    + "UNIQUE_CLOSED_SENTENCE about d_k must stay in the prompt and out of the quote. "
    + "A tail sentence closes the paragraph."
)


def _tiny_db(tmp_path):
    faiss = pytest.importorskip("faiss")
    np = pytest.importorskip("numpy")
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    rows = [
        {
            "id": "far", "corpusid": 10, "arxiv_id": "1706.03762", "kind": "p", "section": "Att",
            "text": "An open paragraph mentions d_k once and can be shown in full.",
            "latex": "d_k", "license": "https://creativecommons.org/licenses/by/4.0/",
            "url": "https://arxiv.org/abs/1706.03762",
        },
        {
            "id": "near", "corpusid": 11, "arxiv_id": "1409.0473", "kind": "def", "section": "Def",
            "text": _CLOSED, "latex": "d_k",
            "license": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
            "url": "https://arxiv.org/abs/1409.0473",
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "rows.parquet")
    mat = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    faiss.normalize_L2(mat)
    index = faiss.IndexFlatIP(2)
    index.add(mat)
    faiss.write_index(index, str(tmp_path / "faiss.index"))
    return np


def _use_db(monkeypatch, tmp_path, np):
    monkeypatch.setenv("RRM_PASSAGES", "1")
    monkeypatch.setenv("RRM_PASSAGES_DIR", str(tmp_path))
    monkeypatch.setattr(lookup_mod, "_query_vector", lambda _text: np.array([0.0, 1.0], dtype=np.float32))


def test_flag_off_ignores_the_local_db(tmp_path, monkeypatch):
    np = _tiny_db(tmp_path)
    monkeypatch.delenv("RRM_PASSAGES", raising=False)
    monkeypatch.setenv("RRM_PASSAGES_DIR", str(tmp_path))
    monkeypatch.setattr(lookup_mod, "_query_vector", lambda _text: (_ for _ in ()).throw(AssertionError("embed")))
    rows = [{"id": "a", "paper": "1", "section": "", "text": "local d_k", "latex": ""}]
    got = lookup("d_k", rows=rows)
    assert [row["id"] for row in got] == ["a"]
    assert "near" not in {row["id"] for row in got}


def test_embedding_returns_the_full_passage(tmp_path, monkeypatch):
    np = _tiny_db(tmp_path)
    _use_db(monkeypatch, tmp_path, np)
    got = lookup("d_k", limit=1, query="d_k\nsoftmax scale")
    assert got[0]["id"] == "near"
    assert got[0]["paper"] == "11"
    assert got[0]["kind"] == "def"
    assert got[0]["closed"] is True
    assert got[0]["from_db"] is True
    assert "UNIQUE_CLOSED_SENTENCE" in got[0]["text"]
    assert got[0]["url"] == "https://arxiv.org/abs/1409.0473"


def test_explanation_and_artifact_read_the_passage_and_hide_it(tmp_path, monkeypatch):
    import json

    from rrm.reader.notes import answer_notes, compose

    np = _tiny_db(tmp_path)
    _use_db(monkeypatch, tmp_path, np)
    monkeypatch.setenv("MODEL_API_KEY", "local-test")
    monkeypatch.delenv("RRM_META", raising=False)
    seen = {}

    def complete(body):
        seen["body"] = body
        payload = {
            "notes": [{
                "block_id": "e", "sent_index": 0, "fuente": "near",
                "note": "Dividing by d_k keeps the softmax from saturating.",
            }],
            "artifacts": [{"block_id": "e", "show": True, "why_look": "The bars show the weights spreading out."}],
        }
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}

    paper = {
        "corpusid": 1,
        "license": "",
        "blocks": [{"id": "e", "kind": "eq", "tex": r"\mathrm{softmax}(\frac{QK}{\sqrt{d_k}})"}],
    }
    out = answer_notes(paper, rows=[], complete=complete)
    user = seen["body"]["input"][1]["content"]
    assert seen["body"]["store"] is False
    assert "UNIQUE_CLOSED_SENTENCE" in user
    assert "No se usan para entrenar" in user
    assert "kind=def" in user
    note = out["notes"][0]
    assert "UNIQUE_CLOSED_SENTENCE" not in note["note"]
    assert "UNIQUE_CLOSED_SENTENCE" not in note["cite"]
    assert "softmax" in note["cite"]
    assert "https://arxiv.org/abs/1409.0473" in note["cite"]
    assert out["artifacts"][0]["why_look"] == "The bars show the weights spreading out."
    assert out["artifacts"][0]["url"] == "https://arxiv.org/abs/1409.0473"
    plain = compose("1", {"equations": [], "license": ""}, [
        {"id": "row1", "paper": "9", "section": "Intro", "text": "la cita literal esta aqui d_k", "latex": ""},
    ])
    assert "entrenar" not in plain["input"][1]["content"]


def test_a_copied_closed_passage_is_not_shown(tmp_path, monkeypatch):
    import json

    from rrm.reader.notes import answer_notes

    np = _tiny_db(tmp_path)
    _use_db(monkeypatch, tmp_path, np)
    monkeypatch.setenv("MODEL_API_KEY", "local-test")
    monkeypatch.delenv("RRM_META", raising=False)

    def complete(_body):
        payload = {
            "notes": [{
                "block_id": "e", "sent_index": 0, "fuente": "near",
                "note": "UNIQUE_CLOSED_SENTENCE about d_k must stay in the prompt and out of the quote.",
            }],
            "artifacts": [{
                "block_id": "e", "show": True,
                "why_look": "Look: UNIQUE_CLOSED_SENTENCE about d_k must stay in the prompt and out of the quote.",
            }],
        }
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}

    paper = {
        "corpusid": 1,
        "license": "",
        "blocks": [{"id": "e", "kind": "eq", "tex": r"\mathrm{softmax}(\frac{QK}{\sqrt{d_k}})"}],
    }
    out = answer_notes(paper, rows=[], complete=complete)
    blob = json.dumps(out["notes"]) + json.dumps(out["artifacts"])
    assert "UNIQUE_CLOSED_SENTENCE" not in blob
    assert out["notes"] == [] or "1409.0473" in out["notes"][0]["cite"]
