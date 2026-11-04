"""rrm-widget/0.4 on the Python side (RRM-90): normalize, sanitize, prompts, schema, shots and gate.

No network, no Meta. The 0.4 path is behind RRM_LIVEART_V04; without it nothing changes.
"""
import json
from pathlib import Path

import pytest

from rrm.liveart import archetypes, gate, prompts
from rrm.liveart.contract import VERSION_04, normalize_04, v04_on

EXAMPLES = json.loads((Path(__file__).resolve().parents[1] / "rrm" / "liveart" / "v04_examples.json").read_text())
ARXIV = {"adam-valley": "1412.6980", "rope-shift": "2104.09864", "kl-policy": "2305.18290", "int8-outlier": "2208.07339"}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("RRM_LIVEART_V04", "1")


def test_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv("RRM_LIVEART_V04", raising=False)
    assert not v04_on()
    assert "rrm-widget/0.4" not in prompts.codegen_system()
    assert "version" not in prompts.schemas()["codegen"]["properties"]


def test_prompt_and_schema_with_flag(on):
    text = prompts.codegen_system()
    assert "CONTRATO rrm-widget/0.4" in text and "Nunca ctx.fillText" in text
    schema = prompts.schemas()["codegen"]
    assert schema["properties"]["version"]["enum"] == [VERSION_04]
    assert set(schema["required"]) == set(schema["properties"])


def test_normalize_flat_codegen():
    flat = {
        "version": VERSION_04, "hook": "", "takeaway": "lol takes {plol}.",
        "areas": [{"id": "main", "rect": [0, 0, 1, 1], "x_min": 0, "x_max": 0, "x_label": "", "y_min": 0, "y_max": 1, "y_label": "p"}],
        "marks": [{"id": "b", "control": "beta", "area": "", "axis": "", "label": "lol > 50%"}],
        "controls": [
            {"id": "beta", "label": "beta", "kind": "slider", "options": [], "min": 0.1, "max": 3, "value": 0.6, "step": 0.1},
            {"id": "mode", "label": "method", "kind": "select", "options": ["a", "b", "c"], "min": 0, "max": 9, "value": 1.4, "step": 2},
        ],
    }
    out = normalize_04(flat)
    assert "hook" not in out
    assert out["areas"] == [{"id": "main", "y": {"min": 0, "max": 1, "label": "p"}}]
    assert out["marks"] == [{"id": "b", "control": "beta", "label": "lol > 50%"}]
    assert "kind" not in out["controls"][0] and "options" not in out["controls"][0]
    assert out["controls"][1] == {"id": "mode", "label": "method", "kind": "select", "options": ["a", "b", "c"], "min": 0, "max": 2, "value": 1, "step": 1}
    assert normalize_04({"draw": "x"}) == {"draw": "x"}


def test_sanitize_drops_free_text_only_in_04():
    draw = 'function draw(ctx, state, t, ui) { ctx.fillText("x", 1, 2); ctx.fillRect(0, 0, 4, 4); }'
    assert "fillText" not in gate.sanitize_widget({"version": VERSION_04, "draw": draw})["draw"]
    old = draw.replace(", ui", "")
    assert "fillText" in gate.sanitize_widget({"draw": old})["draw"]


def test_shots_are_04_with_flag(on):
    got = [w["id"] for w in archetypes.shots_for("bars", "kl_rlhf", "kl-policy")]
    assert "kl-policy" not in got and len(got) == 2
    assert all(w["version"] == VERSION_04 for w in archetypes.shots_for("curve", "adam"))


@pytest.mark.parametrize("widget", EXAMPLES, ids=[w["id"] for w in EXAMPLES])
def test_gate_has_no_04_false_positives(on, widget):
    reasons = gate.quality_gate(widget, {"text": widget["title"], "arxiv": ARXIV[widget["id"]]})
    # Content rules of the #57 prompt (question form, citation) stay; layout reasons must not fire on 0.4.
    for bad in ("readability", "dead_label", "shapes", "steps", "free_text", "readout", "takeaway", "version", "banned", "throw"):
        assert bad not in reasons, (widget["id"], reasons)
