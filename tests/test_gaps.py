"""Candidatos de hueco, sin red."""

from rrm.reader.gaps import find_gaps, sqrt_denominator

ATTN = r"\mathrm{Attention}(Q, K, V) = \mathrm{softmax}(\frac{QK^T}{\sqrt{d_k}})V"
PE = (
    r"PE_{(pos,2i)} = sin(pos / 10000^{2i/d_{\text{model}}}) \\ "
    r"PE_{(pos,2i+1)} = cos(pos / 10000^{2i/d_{\text{model}}})"
)


def _h(bid, text):
    return {"id": bid, "kind": "h", "level": 2, "inlines": [{"t": "text", "v": text}]}


def _p(bid, text):
    sent = [{"t": "text", "v": text}]
    return {"id": bid, "kind": "p", "inlines": sent, "sents": [sent]}


def _eq(bid, tex):
    return {"id": bid, "kind": "eq", "tex": tex}


def _long(n=30):
    return " ".join(["palabra"] * n)


def test_attention_tex_hints():
    pe = find_gaps([_eq("b48", PE)])
    assert pe["equations"][0]["hint"] == "matriz"
    att = find_gaps([_eq("b26", ATTN)])
    assert att["equations"][0]["hint"] == "con_sin"
    assert att["equations"][0]["drop"] == r"\sqrt{d_k}"


def test_split_pe_needs_no_paragraph_between():
    left = r"PE_{(pos,2i)} = sin(pos / 10000^{2i/d_{\text{model}}})"
    right = r"PE_{(pos,2i+1)} = cos(pos / 10000^{2i/d_{\text{model}}})"
    joined = find_gaps([_eq("a", left), _eq("b", right)])
    assert joined["equations"][0]["hint"] == "matriz"
    assert joined["equations"][0]["blocks"] == ["a", "b"]
    split = find_gaps([_eq("a", left), _p("m", "en medio"), _eq("b", right)])
    assert all(row["hint"] != "matriz" for row in split["equations"])


def test_denominator_parser():
    whole = r"\frac{a}{\sqrt{b}+\frac{c}{d}}"
    assert sqrt_denominator(whole) == r"\sqrt{b}+\frac{c}{d}"
    assert sqrt_denominator(r"\frac{a}{\sqrt{b}") == ""
    assert find_gaps([_eq("e", r"\alpha_i = 1")])["equations"][0]["hint"] == ""


def test_defined_token_is_not_a_gap():
    later = find_gaps([
        _eq("e", "z = q_z"),
        _p("p", "después se nombra q_z"),
    ])
    assert later["equations"] == []
    earlier = find_gaps([
        _h("h", "Scaled Dot-Product Attention"),
        _p("p1", "aquí d_k vale sesenta"),
        _p("p2", "este párrafo no lo nombra"),
        _eq("e", "z = d_k"),
    ])
    assert earlier["equations"] == []
    missing = find_gaps([_h("h", "Model"), _p("p", "nada"), _eq("e", "z = q_z")])
    assert missing["equations"][0]["missing"] == ["q_z"]
    assert missing["equations"][0]["hint"] == ""


def test_text_model_matches_d_model():
    got = find_gaps([
        _p("p", "usamos d_model en el texto"),
        _eq("e", r"y = d_{\text{model}}"),
    ])
    assert got["equations"] == []


def test_reminder_and_references():
    blocks = [
        _h("h1", "Introduction"),
        _p("p1", "La primera vez el símbolo es d_k en esta frase."),
        _h("h2", "Results"),
        _p("p2", "Más adelante vuelve d_k."),
        _h("h3", "References"),
        _p("r", _long()),
    ]
    got = find_gaps(blocks)
    assert any(row["token"] == "d_k" and row["generated"] is False for row in got["reminders"])
    assert got["sentences"] == []
    intro = find_gaps([
        _h("h", "Introduction"),
        _p("p", _long()),
        _h("r", "References"),
        _p("b", _long()),
    ])
    assert len(intro["sentences"]) == 1
    assert intro["sentences"][0]["block_id"] == "p"
