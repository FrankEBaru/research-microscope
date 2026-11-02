"""Lookup de pasajes sin red y sin la base real."""

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
