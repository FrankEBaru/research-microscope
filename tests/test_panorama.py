"""POST /panorama. sim is local. meta tests pass a fake Muse and do not touch the network."""

import json
import logging
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


def _index(prompt, snippet):
    for line in prompt.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == snippet:
            return int(parts[0])
    raise AssertionError(snippet)


def _no_muse(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("Muse client was called")

    monkeypatch.setattr(pn, "_muse", boom)


def test_mode_default_is_sim_and_meta_falls_back_without_network(monkeypatch):
    monkeypatch.delenv("RRM_PANORAMA_MODE", raising=False)
    assert pn.mode() == "sim"
    sim = pn.run("attention", {"1": DOC_A})
    assert sim and "mode" not in sim[0]
    monkeypatch.setenv("RRM_PANORAMA_MODE", "meta")

    def slow(_prompt, _timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr(pn, "_muse", slow)
    out = pn.run("attention", {"1": DOC_A})
    assert out and all(c["fallback"] is True and c["mode"] == "sim" and c["fallback_reason"] == "timeout" for c in out)
    monkeypatch.setenv("RRM_PANORAMA_MODE", "x")
    with pytest.raises(ValueError):
        pn.mode()


def test_meta_happy_path_rebuilds_exact_quotes(monkeypatch):
    _no_muse(monkeypatch)

    def complete(prompt):
        i2, i3 = _index(prompt, S2), _index(prompt, S3)
        body = {"themes": [
            {"statement": "Attention replaces recurrence and convolution.", "picks": [i2]},
            {"statement": "Queries and keys decide the weights.", "picks": [str(i3)]},
        ]}
        return json.dumps(body), {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}

    out = pn.meta_panorama("attention scaling", {"1": DOC_A, "2": None}, complete=complete)
    assert [c["id"] for c in out] == ["t0", "t1"]
    assert out[0]["statement"] == "Attention replaces recurrence and convolution."
    assert out[0]["selections"] == [{"paper": "1", "quote": S2}]
    assert out[1]["selections"] == [{"paper": "1", "quote": S3}]
    assert all(c["mode"] == "meta" and c["fallback"] is False for c in out)
    assert all(set(s) == {"paper", "quote"} for c in out for s in c["selections"])


def test_meta_invalid_json_falls_back_to_sim(monkeypatch, caplog):
    _no_muse(monkeypatch)
    caplog.set_level(logging.INFO, logger="rrm.panorama")
    calls = []

    def complete(prompt):
        calls.append(prompt)
        return "this is not json"

    question, docs = "attention scaling", {"1": DOC_A, "2": DOC_B}
    out = pn.meta_panorama(question, docs, complete=complete)
    sim = pn.sim_panorama(question, docs)
    assert calls and len(calls[0]) <= pn.MAX_PROMPT_CHARS
    assert [{k: c[k] for k in ("id", "statement", "selections")} for c in out] == sim
    assert all(c["mode"] == "sim" and c["fallback"] is True and c["fallback_reason"] == "invalid_json" for c in out)
    assert "prompt_tokens=None" in caplog.text
    assert S2 not in caplog.text
    key = __import__("os").environ.get("MODEL_API_KEY")
    if key:
        assert key not in caplog.text


def test_meta_out_of_range_index_is_dropped(monkeypatch):
    _no_muse(monkeypatch)

    def complete(prompt):
        return json.dumps({"themes": [
            {"statement": "Only the in-range sentence is kept.", "picks": [999, _index(prompt, S2)]},
            {"statement": "A second claim with no usable index.", "picks": [len(prompt)]},
        ]})

    out = pn.meta_panorama("attention", {"1": DOC_A}, complete=complete)
    assert out[0]["mode"] == "meta" and out[0]["fallback"] is False
    assert out[0]["selections"] == [{"paper": "1", "quote": S2}]
    assert out[1]["selections"] == []


def test_meta_duplicate_quote_is_dropped(monkeypatch):
    _no_muse(monkeypatch)
    longer = S2 + " Further sections repeat the same observation with more detail and a second clause."
    doc = {"blocks": [
        p(S2),
        p(longer),
        p(S3),
    ]}

    def complete(prompt):
        dup, good = _index(prompt, S2), _index(prompt, S3)
        assert dup != good
        return json.dumps({"themes": [
            {"statement": "A sentence that occurs in two blocks is not evidence.", "picks": [dup, dup]},
            {"statement": "A sentence that occurs once is kept.", "picks": [good, good]},
        ]})

    out = pn.meta_panorama("attention recurrence", {"4": doc}, complete=complete)
    quotes = [s["quote"] for c in out for s in c["selections"]]
    assert S2 not in quotes
    assert quotes == [S3]
    assert pn.quote_ok(doc, S2) is False
    assert pn.quote_ok(doc, S3) is True
    assert all(c["fallback"] is False for c in out)


def test_meta_logs_token_usage_without_the_prompt(monkeypatch, caplog):
    _no_muse(monkeypatch)
    caplog.set_level(logging.INFO, logger="rrm.panorama")

    def complete(prompt):
        i = _index(prompt, S2)
        return json.dumps({"themes": [
            {"statement": "Attention is the whole model.", "picks": [i]},
            {"statement": "Weights come from queries and keys.", "picks": [_index(prompt, S3)]},
        ]}), {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}

    pn.meta_panorama("attention", {"1": DOC_A}, complete=complete)
    assert "prompt_tokens=20" in caplog.text
    assert "completion_tokens=8" in caplog.text
    assert "total_tokens=28" in caplog.text
    assert "panorama_meta" in caplog.text
    assert S2 not in caplog.text


def test_meta_prompt_stays_within_the_char_cap(monkeypatch):
    _no_muse(monkeypatch)
    sentence = "Attention " + ("maps queries to keys in this long unique sentence. " * 6)
    docs = {str(i): {"blocks": [p(sentence + str(i))]} for i in range(12)}
    seen = {}

    def complete(prompt):
        seen["n"] = len(prompt)
        return "[]"

    pn.meta_panorama("attention", docs, complete=complete)
    assert seen["n"] <= pn.MAX_PROMPT_CHARS


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_meta_quotes_pass_the_ui_gate(monkeypatch):
    _no_muse(monkeypatch)

    def complete(prompt):
        return json.dumps({"themes": [
            {"statement": "Attention replaces recurrence.", "picks": [_index(prompt, S2)]},
            {"statement": "Weights come from queries and keys.", "picks": [_index(prompt, S3)]},
        ]})

    out = pn.meta_panorama("attention", {"1": DOC_A}, complete=complete)
    code = """
      import { validateSelections } from './src/lib/muse.js';
      const docs = JSON.parse(process.argv[1]);
      const sels = JSON.parse(process.argv[2]);
      console.log(JSON.stringify(validateSelections(docs, sels)));
    """
    sels = [s for c in out for s in c["selections"]]
    got = subprocess.run(
        ["node", "--input-type=module", "-e", code, json.dumps({"1": DOC_A}), json.dumps(sels)],
        cwd=READER, capture_output=True, text=True, check=True,
    ).stdout
    parsed = json.loads(got)
    assert parsed["rejected"] == []
    assert [row["quote"] for row in parsed["ok"]] == [S2, S3]


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
    assert "501" not in body and "NotImplementedError" not in body
