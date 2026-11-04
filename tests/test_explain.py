"""RRM-100: Explain por sección. Sin red: el modelo es un JSON fijo."""

import numpy as np

from rrm.reader.explain import llm
from rrm.reader.explain.review import Context, assemble, review_e1, review_e2
from rrm.reader.explain.section import paper_units, ptr_of, section_units
from rrm.reader.explain.sheet import key_points


def _t(text):
    return [{"t": "text", "v": text}]


PAPER = {
    "corpusid": 1,
    "blocks": [
        {"id": "b1", "kind": "h", "level": 1, "inlines": _t("Model")},
        {"id": "b2", "kind": "h", "level": 2, "inlines": _t("Attention")},
        {"id": "b3", "kind": "p", "inlines": _t("x"), "sents": [_t("We divide by the root of d_k."), _t("This keeps gradients large.")]},
        {"id": "b4", "kind": "eq", "tex": "a=b"},
        {"id": "b5", "kind": "h", "level": 4, "inlines": _t("Masking.")},
        {"id": "b6", "kind": "list", "items": [_t("Decoder positions cannot see the future.")]},
        {"id": "b7", "kind": "h", "level": 2, "inlines": _t("Training")},
        {"id": "b8", "kind": "p", "inlines": _t("x"), "sents": [_t("We train on WMT 2014 English-German.")]},
    ],
}


def _encode(texts):
    rng = np.random.default_rng(0)
    return np.stack([rng.standard_normal(8).astype(np.float32) + len(t) * 0.0 for t in texts])


def test_section_units_cover_sentences_equations_lists_and_paragraph_titles():
    ids = [u["id"] for u in section_units(PAPER, "b2")]
    assert ids == ["b3#0", "b3#1", "b4", "b5", "b6#0"]
    assert "b8#0" in [u["id"] for u in paper_units(PAPER)]
    assert section_units(PAPER, "nope") == []


def test_ptr_of_reads_the_id_when_the_model_pastes_the_sentence():
    assert ptr_of("[b3#1] This keeps gradients large.") == "b3#1"
    assert ptr_of("b4") == "b4"
    assert ptr_of("sentence 3") == ""


def test_assemble_copies_text_drops_invented_ids_and_keeps_forgotten_sentences():
    ctx = Context(PAPER, "b2", encode=_encode)
    sents = ["You divide by the root of d_k.", "It was trained on ImageNet.", "Masks hide the future."]
    data = {"claims": [
        {"n": 1, "text": "You divide by the root of d_k.", "verdict": "coincide", "why": "Same as the paper.", "paper": ["[b3#0] We divide…"]},
        {"n": 2, "text": "made up words", "verdict": "contradice", "why": "x", "paper": ["b99#0"]},
    ], "missed": [{"paper": ["b6#0"], "why": "Add the decoder mask."}]}
    parts = assemble(ctx, sents, data)
    assert parts["coincide"][0]["cite"] == "We divide by the root of d_k."
    assert parts["coincide"][0]["ptr"] == "b3#0"
    # Un id que no existe no deja un «contradice» sin cita: pasa a sin respaldo con las palabras del lector.
    assert [x["text"] for x in parts["sin_respaldo"]] == ["It was trained on ImageNet.", "Masks hide the future."]
    assert parts["sin_respaldo"][1]["verified"] is False
    assert parts["te_falto"][0]["cite"] == "Decoder positions cannot see the future."


def test_e2_missed_comes_from_core_points_nobody_covered():
    ctx = Context(PAPER, "b2", encode=_encode)
    sheet = {"points": [
        {"id": "k1", "point": "Scores are divided by sqrt(d_k).", "why": "Keeps softmax gradients useful.", "ptrs": ["b3#0"], "core": True, "queries": []},
        {"id": "k2", "point": "The decoder is masked.", "why": "No peeking at future tokens.", "ptrs": ["b6#0"], "core": True, "queries": []},
        {"id": "k3", "point": "A detail.", "why": "", "ptrs": ["b4"], "core": False, "queries": []},
    ], "passages": []}
    reply = {"claims": [{"n": 1, "text": "Divide by root d_k.", "verdict": "coincide", "why": "ok", "paper": ["b3#0"], "points": ["k1"]}]}

    def post(body, timeout=0):
        import json
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(reply)}]}],
                "usage": {"input_tokens": 100, "output_tokens": 10}}

    import rrm.reader.explain.llm as L
    old = L.post_responses
    L.post_responses = post
    try:
        parts, cost, info = review_e2(ctx, "Divide by root d_k.", sheet)
    finally:
        L.post_responses = old
    assert [m["point"] for m in parts["te_falto"]] == ["k2"]
    assert parts["te_falto"][0]["cite"] == "Decoder positions cannot see the future."
    assert cost["cost_usd"] > 0 and info["parsed"]


def test_key_points_keep_only_real_pointers(monkeypatch):
    import json

    reply = {"points": [
        {"point": "Divide by sqrt d_k", "why": "w", "ptrs": ["[b3#0] We divide", "b77#1"], "core": True, "queries": ["q1", "q2", "q3"]},
        {"point": "Invented", "why": "w", "ptrs": ["b90"], "core": True, "queries": []},
    ]}
    monkeypatch.setattr(llm, "post_responses", lambda body, timeout=0: {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(reply)}]}], "usage": {}})
    points, _cost, _s = key_points("Attention", section_units(PAPER, "b2"))
    assert [(p["id"], p["ptrs"]) for p in points] == [("k1", ["b3#0"])]


def test_price_wonder_is_dearer_than_contributor():
    usage = {"input_tokens": 1000, "output_tokens": 100}
    assert llm.price(llm.WONDER, usage)["cost_usd"] > 20 * llm.price(llm.CONTRIBUTOR, usage)["cost_usd"]


def test_salvage_keeps_complete_claims_of_a_looping_reply():
    from rrm.reader.explain.review import salvage

    raw = '{"claims": [{"n": 1, "text": "a", "verdict": "coincide", "why": "w", "paper": ["b3#0"]}, {"n": 2, "text": "b", "why": "jjjj jjjj jjjj'
    assert salvage(raw) == {"claims": [{"n": 1, "text": "a", "verdict": "coincide", "why": "w", "paper": ["b3#0"]}]}
    assert salvage("nothing") is None


def test_clean_why_drops_model_garbage_but_keeps_latex():
    from rrm.reader.explain.review import clean_why

    assert clean_why("Paper divides by $\\sqrt{d_k}$ to keep gradients usable.") == "Paper divides by $\\sqrt{d_k}$ to keep gradients usable."
    assert clean_why("Paper states the same dimensions for queries, keys and values here. A1BC21A2CE0B2D31-D780-4F3C-86D5-75C9BFD1720E") == \
        "Paper states the same dimensions for queries, keys and values here."
    assert clean_why("x " + "jjjjjjjjjj " * 30) == ""
