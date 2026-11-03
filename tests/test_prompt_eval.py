"""La suite offline pasa y no llama a Meta."""

import os

from evals.prompts.runner import estimate, format_table, live_on, main, run


def test_offline_suite_passes_and_prints_a_table(capsys):
    assert os.environ.get("RRM_EVAL_LIVE", "") != "1"
    assert live_on() is False
    rows = run()
    failed = [row["id"] for row in rows if not row["ok"]]
    assert failed == []
    text = format_table(rows, estimate())
    assert "PASS" in text and "FAIL" not in text
    assert "live: not run" in text
    cost = estimate()
    assert cost["calls"] > 40
    assert 0 < cost["cost_usd"] < 0.05
    assert main() == 0
    printed = capsys.readouterr().out
    assert "prompt eval (offline)" in printed
    assert "one live run estimate" in printed


def test_bundle_is_one_folder_and_has_no_secrets(tmp_path):
    from evals.prompts.runner import estimate, run, write_bundle

    folder = write_bundle(run(), estimate(), root=tmp_path)
    cases = (folder / "cases.json").read_text(encoding="utf-8")
    report = (folder / "REPORT.md").read_text(encoding="utf-8")
    offline = (folder / "results" / "offline.json").read_text(encoding="utf-8")
    for name in ("absurd", "sensible", "injection", "near-correct-but-wrong"):
        assert name in cases
    assert "PASS" in report and "Commit:" in report
    blob = cases + report + offline
    assert "MODEL_API_KEY" not in blob
    assert "Bearer " not in blob
    assert "sk-" not in blob


def test_live_flag_is_off_so_urlopen_is_not_used(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("red")

    monkeypatch.delenv("RRM_EVAL_LIVE", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    rows = run()
    assert all(row["ok"] for row in rows)
