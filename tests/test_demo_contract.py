"""Contract checks for the demo guard, figure sandbox, and fixture shape. No network."""

import json
from pathlib import Path

from rrm.demo_guard import ALLOWED_ORIGINS, check, cors_kwargs
from rrm.reader.files import resolve_figure
from rrm.reader.latex import parse_tex

FIX = Path(__file__).parents[1] / "tests" / "fixtures" / "demo"
TEX = "\n".join([
    r"\documentclass{article}",
    r"\begin{document}",
    r"\section{One}",
    r"Words before the display live in a paragraph.",
    r"\[",
    r"y = x + 1",
    r"\]",
    r"More words sit between the two displays.",
    r"$$",
    r"z = y + 2",
    r"$$",
    r"\begin{equation}\label{eq:main}",
    r"a = b + c",
    r"\end{equation}",
    r"\end{document}",
])


def test_file_name_rejects_traversal(tmp_path):
    root = tmp_path / "papers"
    folder = root / "1"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text("{}", encoding="utf-8")
    (folder / "source.pdf").write_bytes(b"%PDF")
    (folder / "paper.json").write_text("{}", encoding="utf-8")
    assert resolve_figure(root, "1", "../meta.json") is None
    assert resolve_figure(root, "1", "foo/bar.png") is None
    assert resolve_figure(root, "1", "source.pdf") is None
    assert resolve_figure(root, "1", "..") is None
    assert resolve_figure(root, "../1", "plot.png") is None
    assert resolve_figure(root, "1", "") is None
    assert "resolve_figure(" in (Path(__file__).parents[1] / "rrm" / "reader" / "serve.py").read_text(encoding="utf-8")


def test_file_name_accepts_png(tmp_path):
    root = tmp_path / "papers"
    dest = root / "42" / "figures"
    dest.mkdir(parents=True)
    png = dest / "plot.png"
    png.write_bytes(b"\x89PNG\r\n")
    found = resolve_figure(root, "42", "plot.png")
    assert found == png.resolve()
    assert found.parent.name == "figures"


def test_guard_fails_closed_without_token(monkeypatch):
    monkeypatch.delenv("RRM_DEMO_TOKEN", raising=False)
    assert check("secret", None) == 401
    monkeypatch.setenv("RRM_DEMO_TOKEN", "")
    assert check("secret", None) == 401


def test_guard_rejects_bad_token_and_unknown_origin(monkeypatch):
    monkeypatch.setenv("RRM_DEMO_TOKEN", "secret")
    assert check(None, None) == 401
    assert check("nope", None) == 401
    assert check("nope", None, origin="http://localhost:3000") == 401
    assert check("secret", None, origin="https://evil.example") == 403
    assert "*" not in cors_kwargs()["allow_origins"]
    assert cors_kwargs()["allow_origins"] == list(ALLOWED_ORIGINS)


def test_guard_accepts_header_and_query_token(monkeypatch):
    monkeypatch.setenv("RRM_DEMO_TOKEN", "secret")
    assert check("secret", None) is None
    assert check("secret", None, origin="http://localhost:3000") is None
    assert check("secret", None, origin="") is None
    assert check(None, "secret") is None
    assert check("secret", "other") is None


def test_fixture_ids_stable_sections_to_figures():
    sections = json.loads((FIX / "paper_sections.json").read_text(encoding="utf-8"))
    figures = json.loads((FIX / "paper_figures.json").read_text(encoding="utf-8"))
    assert sections["stage"] == "sections"
    assert figures["stage"] == "figures"
    assert [b["id"] for b in sections["blocks"]] == [b["id"] for b in figures["blocks"]] == ["b0", "b1", "b2", "b3"]
    assert sections["blocks"][3]["images"] == ["figures/plot.pdf"]
    assert figures["blocks"][3]["images"] == ["plot.png"]
    eq = sections["blocks"][2]
    assert eq["number"] == 1 and "\\tag" not in eq["tex"]


def test_display_math_is_its_own_block():
    assert len(TEX.splitlines()) == 15
    paper = parse_tex(TEX)
    for block in paper["blocks"]:
        if block["kind"] == "p":
            dumped = json.dumps(block)
            assert "\\[" not in dumped and "$$" not in dumped
    eqs = [b for b in paper["blocks"] if b["kind"] == "eq"]
    assert len(eqs) >= 3
    assert any(b.get("number") == 1 for b in eqs)
    assert all("\\tag" not in (b.get("tex") or "") for b in eqs)


def test_burst_fixture_has_corpusid_not_arxiv():
    burst = json.loads((FIX / "burst.json").read_text(encoding="utf-8"))
    assert burst["mode"] == "short" and burst["subtopics"] == []
    assert len(burst["papers"]) == 3 and len(burst["edges"]) == 2
    for row in burst["papers"]:
        assert isinstance(row["corpusid"], int)
        assert "arxivId" not in row
