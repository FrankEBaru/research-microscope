"""0.4 is off unless RRM_LIVEART_V04 is set. No Meta."""

from rrm.liveart.contract import v04_on
from rrm.liveart.gate import _few_stops
from rrm.liveart.prompts import codegen_system, repair_messages, schemas


def test_v04_is_off_and_a_select_is_not_a_short_slider(monkeypatch):
    monkeypatch.delenv("RRM_LIVEART_V04", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_RRM_LIVEART_V04", raising=False)
    assert v04_on() is False
    assert "rrm-widget/0.4" not in codegen_system()
    assert "version" not in schemas()["codegen"]["properties"]
    system, _user = repair_messages({"text": "Adam."}, "Adam.", [], {}, [])
    assert "ui.area" not in system
    assert _few_stops([{"id": "mode", "label": "method", "kind": "select", "min": 0, "max": 2, "step": 1, "value": 0}]) is False
    assert _few_stops([{"id": "lr", "label": "lr", "min": 0, "max": 1, "step": 1, "value": 0}]) is True


def test_v04_prompt_and_schema_follow_the_flag(monkeypatch):
    monkeypatch.setenv("RRM_LIVEART_V04", "1")
    text = codegen_system()
    assert "rrm-widget/0.4" in text
    assert "ui.area" in text
    assert "ui.readout" in text
    props = schemas()["codegen"]["properties"]
    assert props["version"]["type"] == "string"
    assert "kind" in props["controls"]["items"]["properties"]
    assert "id" in schemas()["codegen"]["required"]
    system, _user = repair_messages({"text": "Adam."}, "Adam.", [], {}, [])
    assert "ui.mark" in system
