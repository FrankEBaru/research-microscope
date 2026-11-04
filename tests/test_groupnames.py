"""Nombres de grupo: el verificador tira lo inventado. Sin red."""

import json

from rrm.search.groupnames import accept, name_groups, name_ok


BLOB = "Attention Is All You Need\nNeural machine translation"


def test_name_ok_rejects_invented_words_and_bad_lengths():
    assert name_ok("Attention translation", BLOB)
    assert name_ok("quantum attention", BLOB) is False
    assert name_ok("Attention", BLOB) is False
    assert name_ok("one two three four five six", BLOB) is False


def test_accept_drops_a_failed_group_and_a_repeated_name():
    groups = [
        {"id": "0", "titles": ["Attention Is All You Need"]},
        {"id": "1", "titles": ["Attention and Need in graphs"]},
    ]
    data = {
        "names": [
            {"id": "0", "name": "Attention Need"},
            {"id": "1", "name": "Attention Need"},
            {"id": "9", "name": "Attention Need"},
            {"id": "1", "name": "quantum graphs"},
        ]
    }
    assert accept(groups, data) == [{"id": "0", "name": "Attention Need"}]


def test_name_groups_stays_empty_until_a_mock_answers(monkeypatch):
    monkeypatch.delenv("RRM_GROUP_NAMES", raising=False)
    groups = [{"id": "0", "titles": ["Attention Is All You Need"]}]
    names, cost = name_groups(groups)
    assert names == []
    assert cost["cost_usd"] == 0.0

    def complete(body):
        assert body["reasoning"]["effort"] == "minimal"
        assert body["max_output_tokens"] == 600
        raw = {
            "names": [
                {"id": "0", "name": "Attention Need"},
                {"id": "0", "name": "invented quantum topic"},
            ]
        }
        return {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(raw)}]}],
            "usage": {"input_tokens": 10, "output_tokens": 4, "input_tokens_details": {"cached_tokens": 0}},
        }

    names, cost = name_groups(groups, complete=complete)
    assert names == [{"id": "0", "name": "Attention Need"}]
    assert cost["input_tokens"] == 10
