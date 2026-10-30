"""POST /panorama (simulated). No network, no Modal, no model."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rrm import panorama as pn

ROOT = Path(__file__).parents[1]
READER = ROOT / "apps" / "reader"

S1 = "Scaling laws show that loss falls as a power law in compute, data size and parameters."
S2 = "The Transformer relies entirely on attention and dispenses with recurrence and convolution."
S3 = "Attention weights are computed from queries and keys, then applied to the values of the sequence."


def p(*sents, abs=False):
    return {"kind": "p", "abs": abs, "sents": [[{"t": "text", "v": s}] for s in sents],
            "inlines": [{"t": "text", "v": " ".join(sents)}]}


DOC_A = {"blocks": [p(S1, S2, abs=True), p(S3), {"kind": "h", "inlines": [{"t": "text", "v": "Intro"}]}]}
DOC_B = {"blocks": [p("Another paper says attention is not enough to explain scaling laws in practice.")]}


def test_shape_and_quotes_are_real_sentences():
    out = pn.sim_panorama("¿Cómo funciona la atención en los modelos?", {"1": DOC_A, "2": DOC_B})
    assert [c["id"] for c in out] == ["t0"]
    assert out[0]["statement"] == "Lo que dicen los papers sobre «atención»"
    sels = out[0]["selections"]
    assert {s["paper"] for s in sels} == {"1", "2"}
    text = {S1, S2, S3, "Another paper says attention is not enough to explain scaling laws in practice."}
    assert all(s["quote"] in text for s in sels)
    assert all(set(s) == {"paper", "quote"} for s in sels)


def test_one_sentence_per_theme_and_not_shared():
    out = pn.sim_panorama("attention scaling", {"1": DOC_A})
    quotes = [s["quote"] for c in out for s in c["selections"]]
    assert len(quotes) == len(set(quotes)) == 2


def test_deterministic_and_no_text_invented():
    a = pn.sim_panorama("scaling laws compute", {"1": DOC_A, "2": DOC_B})
    assert a == pn.sim_panorama("scaling laws compute", {"1": DOC_A, "2": DOC_B})


def test_unreadable_papers_add_nothing():
    out = pn.sim_panorama("attention", {"1": None, "2": DOC_B})
    assert [s["paper"] for s in out[0]["selections"]] == ["2"]


def test_duplicate_sentences_are_dropped():
    doc = {"blocks": [p(S2), p(S2)]}
    assert pn.sim_panorama("attention", {"1": doc})[0]["selections"] == []


def test_empty_question_has_no_themes():
    assert pn.sim_panorama("¿?", {"1": DOC_A}) == []


def test_math_is_dollar_wrapped_like_the_ui_gate():
    inls = [{"t": "text", "v": "Loss is "}, {"t": "math", "v": "L(N)"}, {"t": "cite", "v": "x"}, {"t": "text", "v": " in the model."}]
    assert pn.inline_text(inls) == "Loss is $L(N)$ in the model."


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("question", ["¿Cómo funciona la atención en los modelos?", "scaling laws compute", "self-attention vs recurrence", "leyes de escalado"])
def test_same_picks_as_musesim_js(question):
    code = """
      import { themesOf, simulatePaper, assemble } from './src/lib/musesim.js';
      const docs = JSON.parse(process.argv[1]);
      const themes = themesOf(process.argv[2]);
      const per = {};
      for (const [id, doc] of Object.entries(docs)) per[id] = simulatePaper({ themes, id, doc });
      console.log(JSON.stringify(assemble(themes, per)));
    """
    docs = {"1": DOC_A, "2": DOC_B}
    got = subprocess.run(["node", "--input-type=module", "-e", code, json.dumps(docs), question],
                         cwd=READER, capture_output=True, text=True, check=True).stdout
    assert json.loads(got) == pn.sim_panorama(question, docs)


def test_parse_request_validates():
    assert pn.parse_request({"question": " q ", "ids": [3, "3", "4"]}) == ("q", ["3", "4"])
    for bad in (None, [], {"question": "", "ids": [1]}, {"question": "q"}, {"question": "q", "ids": []},
                {"question": "q", "ids": ["x"]}, {"question": "q", "ids": [True]},
                {"question": "q" * 501, "ids": [1]}, {"question": "q", "ids": list(range(21))}):
        with pytest.raises(ValueError):
            pn.parse_request(bad)


def test_mode_default_and_meta(monkeypatch):
    monkeypatch.delenv("RRM_PANORAMA_MODE", raising=False)
    assert pn.mode() == "sim"
    assert pn.run("attention", {"1": DOC_A})
    monkeypatch.setenv("RRM_PANORAMA_MODE", "meta")
    with pytest.raises(NotImplementedError):
        pn.run("attention", {"1": DOC_A})
    monkeypatch.setenv("RRM_PANORAMA_MODE", "x")
    with pytest.raises(ValueError):
        pn.mode()


def test_docs_for_reads_only_settled_papers(tmp_path):
    status = {"1": "done", "2": "abstract_only", "3": "parsing", "4": "failed"}
    docs = pn.docs_for(tmp_path, ["1", "2", "3", "4", "5"],
                       lambda f: {"status": status[f.name]} if f.name in status else None,
                       lambda f: {"blocks": [], "from": f.name})
    assert docs == {"1": {"blocks": [], "from": "1"}, "2": {"blocks": [], "from": "2"}, "3": None, "4": None, "5": None}


def test_serve_wires_the_route_through_the_guard():
    src = (ROOT / "rrm" / "reader" / "serve.py").read_text(encoding="utf-8")
    body = src[src.index('@web.post("/panorama")'):src.index('@web.get("/crops")')]
    assert "gate(request, False)" in body and "docs_for(" in body
    assert "spawn" not in body and "prioritize" not in body
