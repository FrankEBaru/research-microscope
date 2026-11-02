"""RRM-55: texto embebido, encabezado no genérico, citas a ecuaciones y ancla sin vector.

Datos sintéticos. Sin Modal, sin arXiv, sin Meta. El test del tokenizer usa
el de allenai/specter2_base solo si ya está en el caché local de HF.
"""

import pytest

from rrm.passages.cut import cut_flags, resolve_seeds, union_from_reports
from rrm.passages.embed import (
    BEFORE_WORDS,
    LATEX_TOKENS,
    LATEX_RATE,
    embed_policy,
    embed_rows,
    header_text,
    passage_text,
)
from rrm.passages.rows import extract_rows, generic_headings, heading_generic, specific_heading
from rrm.passages.store import build_manifest
from rrm.reader.latex import parse_tex


def _t(value):
    return [{"t": "text", "v": value}]


def _p(nodes):
    return {"kind": "p", "inlines": nodes, "sents": [nodes]}


def _paper():
    ref = [{"t": "text", "v": "As shown in "}, {"t": "ref", "label": "eq:attn", "target": "b3"}, {"t": "text", "v": ", scaling matters."}]
    plain_ref = _t("Equation (1) is cheap to compute on GPUs.")
    nested = [{"t": "em", "c": [{"t": "ref", "label": "eq:other,eq:attn"}]}, {"t": "text", "v": " again."}]
    blocks = [
        {"kind": "h", "level": 1, "number": "1", "inlines": _t("Introduction")},
        _p(nested),
        {"kind": "h", "level": 1, "number": "3", "inlines": _t("Model Architecture")},
        {"kind": "h", "level": 2, "number": "3.2", "inlines": _t("Attention")},
        {"kind": "h", "level": 3, "number": "3.2.1", "inlines": _t("Scaled Dot-Product Attention")},
        _p(_t("We compute the dot products of the query with all keys.")),
        {"kind": "eq", "tex": r"\mathrm{softmax}(QK^T/\sqrt{d_k})V", "label": "eq:attn", "labels": ["eq:attn"], "number": 1},
        _p(_t("The scaling counteracts large dot products.")),
        {"kind": "h", "level": 1, "number": "5", "inlines": _t("Experiments")},
        _p(ref),
        _p(plain_ref),
        _p(_t("Unrelated paragraph about BLEU.")),
    ]
    for i, block in enumerate(blocks):
        block["id"] = f"b{i}"
    # el target del ref apunta al id real de la ecuación
    blocks[9]["inlines"][1]["target"] = "b6"
    return {"corpusid": 7, "arxivId": "9999.00007", "title": "Attention Is All You Need", "blocks": blocks}


def test_generic_headings_list_and_most_specific_non_generic():
    assert heading_generic("1 Introduction")
    assert heading_generic("5. Experiments")
    assert heading_generic("Conclusiones")
    assert heading_generic("Introducción")
    assert not heading_generic("3.2.1 Scaled Dot-Product Attention")
    assert specific_heading(["Model Architecture", "Attention", "3.2.1 Scaled Dot-Product Attention"]) == "Scaled Dot-Product Attention"
    assert specific_heading(["Graph Convolutions", "Experiments"]) == "Graph Convolutions"
    assert specific_heading(["1 Introduction"]) == ""
    assert "introduction" in generic_headings() and "related work" in generic_headings()
    manifest = build_manifest([], [])
    assert manifest["generic_headings"] == generic_headings()
    assert manifest["embed_text"]["before_words"] == BEFORE_WORDS


def test_rows_carry_title_head_and_eq_context_ids():
    rows = extract_rows(_paper())
    by = {row["id"]: row for row in rows}
    eq = [row for row in rows if row["kind"] == "eq"][0]
    assert eq["title"] == "Attention Is All You Need"
    assert eq["head"] == "Scaled Dot-Product Attention"
    assert eq["section"] == "Scaled Dot-Product Attention"
    assert eq["ctx_before"] == "7:5" and eq["ctx_after"] == "7:7"
    # \ref con target, nested \cref con dos etiquetas y "Equation (1)"; máx 2, los más cercanos
    assert eq["ctx_refs"] == ["7:9", "7:10"]
    assert "7:11" not in eq["ctx_refs"]
    intro = by["7:1"]
    assert intro["head"] == "" and intro["title"] == "Attention Is All You Need"
    assert by["7:9"]["head"] == ""
    from rrm.passages.rows import _referencing_paragraphs

    paper = _paper()
    near = _referencing_paragraphs(paper["blocks"], 6, set(), {5, 7, 9, 10})
    assert near == [1]  # \cref{eq:other,eq:attn} anidado en \emph
    # el texto mostrado no cambia
    assert eq["text"] == "We compute the dot products of the query with all keys.\nThe scaling counteracts large dot products."


def test_embedded_string_order_and_header():
    rows = extract_rows(_paper())
    eq = [row for row in rows if row["kind"] == "eq"][0]
    by_id = {row["id"]: row for row in rows if row["kind"] == "p"}
    text = passage_text(eq, by_id)
    lines = text.split("\n")
    assert lines[0] == "Attention Is All You Need \u203a Scaled Dot-Product Attention"
    assert lines[1].startswith("We compute the dot products")
    assert lines[2] == eq["latex"]
    assert lines[3].startswith("The scaling counteracts")
    assert any(line.startswith("As shown in") for line in lines[4:])
    assert "Unrelated paragraph" not in text
    intro = [row for row in rows if row["kind"] == "p" and row["id"] == "7:1"][0]
    assert passage_text(intro, by_id).split("\n")[0] == "Attention Is All You Need"
    # sin título queda solo la sección; sin nada, solo el texto
    assert header_text({"title": "", "head": "Scaled Dot-Product Attention"}) == "Scaled Dot-Product Attention"
    bare = passage_text({"kind": "p", "text": "solo texto", "latex": ""})
    assert bare == "solo texto\n"
    # embed_rows arma el mapa de párrafos solo
    seen = []
    embed_rows(rows, lambda texts: (seen.extend(texts), [[0.0, 1.0]] * len(texts))[1], batch=4)
    assert seen[[row["id"] for row in rows].index(eq["id"])] == text


def test_long_before_paragraph_is_cut_from_the_left_and_latex_stays():
    long_before = " ".join(f"w{i}" for i in range(400))
    row = {"kind": "eq", "title": "T", "head": "", "text": "", "latex": "x" * 2000,
           "ctx_before": "1:0", "ctx_after": "1:2", "ctx_refs": []}
    by_id = {"1:0": {"text": long_before}, "1:2": {"text": " ".join(["after"] * 200)}}
    text = passage_text(row, by_id)
    lines = text.split("\n")
    assert lines[1].endswith("w399") and "w0 " not in lines[1]
    assert len(lines[1].split()) <= BEFORE_WORDS
    assert len(lines[2]) == int(LATEX_TOKENS / LATEX_RATE)
    assert embed_policy()["window_tokens"] <= 510


def _specter_tokenizer():
    tokenizers = pytest.importorskip("tokenizers")
    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download("allenai/specter2_base", "tokenizer.json", local_files_only=True)
    except Exception:
        pytest.skip("tokenizer de specter2_base no está en el caché local")
    return tokenizers.Tokenizer.from_file(path)


def test_latex_inside_512_with_the_real_tokenizer():
    tok = _specter_tokenizer()
    prose = ("The query $q_i$ attends to every key $k_j$ with weight $\\alpha_{ij}$ and "
             "we divide by $\\sqrt{d_k}$ before the softmax. ") * 20
    latex = r"H^{(l+1)} = \sigma\left(\tilde{D}^{-\frac{1}{2}}\tilde{A}\tilde{D}^{-\frac{1}{2}}H^{(l)}W^{(l)}\right) \quad " * 8
    row = {"kind": "eq", "title": "Semi-Supervised Classification with Graph Convolutional Networks",
           "head": "Fast Approximate Convolutions on Graphs", "text": "", "latex": latex,
           "ctx_before": "a", "ctx_after": "b", "ctx_refs": ["c", "d"]}
    by_id = {key: {"text": prose} for key in "abcd"}
    text = passage_text(row, by_id)
    lines = text.split("\n")
    # BERT separa por espacios antes de wordpiece: el prefijo se tokeniza igual que en el texto entero
    upto_latex = len(tok.encode("\n".join(lines[:3])).ids)  # con [CLS] y [SEP]
    assert lines[2] and upto_latex <= 512
    assert len(tok.encode(text).ids) > 512  # lo de después (siguiente y citas) sí puede quedar cortado
    # caso típico: ecuación corta, el párrafo previo llega a BEFORE_WORDS
    short = dict(row, latex=r"\mathrm{softmax}(QK^T/\sqrt{d_k})V")
    lines = passage_text(short, by_id).split("\n")
    assert len(lines[1].split()) == BEFORE_WORDS
    assert len(tok.encode("\n".join(lines[:3])).ids) <= 512


def test_parser_keeps_labels_and_links_eqref():
    tex = r"""
\documentclass{article}
\title{Ref Note}
\begin{document}
\section{Scaled Scores}
The score divides by the factor below.
\begin{equation}
\sqrt{d_k}\label{eq:scale}
\end{equation}
That factor keeps the product from growing.

Some filler paragraph here.

As \eqref{eq:scale} shows, the scale is cheap.
\end{document}
"""
    paper = parse_tex(tex, arxiv_id="9999.00009")
    paper["corpusid"] = 9
    eqb = [b for b in paper["blocks"] if b["kind"] == "eq"][0]
    assert eqb.get("label") == "eq:scale" and eqb.get("number") == 1
    rows = extract_rows(paper, title="Ref Note")
    eq = [row for row in rows if row["kind"] == "eq"][0]
    assert len(eq["ctx_refs"]) == 1
    cited = {row["id"]: row for row in rows}[eq["ctx_refs"][0]]
    assert "the scale is cheap" in cited["text"]
    assert eq["head"] == "Scaled Scores"


def test_anchor_without_vector_falls_back_to_text_then_fails_loudly():
    spec = {"name": "gcn", "anchor": None, "title": "Semi-Supervised Classification with Graph Convolutional Networks"}
    asked = []
    out = resolve_seeds(
        spec,
        neighbors_of=lambda anchor: [],
        first_hit=None,
        title_hit=lambda title: 3144218,
        text_neighbors=lambda text: (asked.append(text), [3144218, 11, 12, 13])[1],
        text_of=lambda cid: "Semi-Supervised Classification with Graph Convolutional Networks",
    )
    assert asked and out["via"] == "text" and out["error"] is None
    assert out["seeds"][0] == 3144218 and 3144218 not in out["seeds"][1:]
    assert out["neighbors"] == 3
    dead = resolve_seeds(spec, neighbors_of=lambda anchor: [], first_hit=None,
                         title_hit=lambda title: 3144218, text_neighbors=lambda text: [], text_of=None)
    assert dead["error"] == "ancla sin vecinos" and dead["seeds"] == []
    flags = cut_flags([{**dead, "top": [], "ranked_ids": []}])
    assert flags["errors"] == ["gcn"]
    with pytest.raises(RuntimeError, match="sin semillas"):
        union_from_reports([{**dead, "top": [], "ranked_ids": []}])
    assert union_from_reports([{**dead, "top": [], "ranked_ids": []}], ignore_stop=True)["ids"] == []


def test_cached_paper_without_license_asks_only_the_license(tmp_path):
    from rrm.passages.arxiv import ArxivClient
    from rrm.passages.cache import store_reader_cache
    from rrm.passages.harvest import harvest_one
    from rrm.reader.pipeline import load_meta, save_meta

    paper = _paper()
    folder = tmp_path / "papers" / "7"
    store_reader_cache(folder, dict(paper, source="latex"))
    meta = load_meta(folder)
    meta["license"] = ""  # como el caché viejo del lector
    save_meta(folder, meta)
    urls = []

    def opener(url, ua):
        urls.append(url)
        return b'<entry><arxiv:license>http://creativecommons.org/licenses/by/4.0/</arxiv:license></entry>'

    client = ArxivClient(opener=opener, sleep=lambda s: None)
    out = harvest_one({"corpusid": 7, "arxiv_id": "9999.00007", "title": "Attention Is All You Need"},
                      client=client, papers_root=tmp_path / "papers", dest=tmp_path / "passages",
                      license_lookup=True)
    assert out["downloaded"] is False and out["rows"] > 0
    assert len(urls) == 1 and "/oai2?verb=GetRecord" in urls[0] and "oai:arXiv.org:9999.00007" in urls[0]
    import json

    saved = json.loads((tmp_path / "passages" / "papers" / "7.json").read_text(encoding="utf-8"))
    assert saved["paper"]["license"] == "http://creativecommons.org/licenses/by/4.0/"
    again = harvest_one({"corpusid": 7, "arxiv_id": "9999.00007"}, client=client,
                        papers_root=tmp_path / "papers", dest=tmp_path / "passages", retry=True,
                        license_lookup=True)
    assert again["rows"] == out["rows"] and len(urls) == 2


def test_oai_license_parse_errors_are_reported_and_gate_is_shared(tmp_path):
    from rrm.passages.arxiv import ArxivClient, HarvestGate, LicenseLookupError, parse_oai_license
    from rrm.passages.harvest import harvest_one

    ok = b'<OAI-PMH><GetRecord><record><metadata><arXiv><id>1706.03762</id><license>http://arxiv.org/licenses/nonexclusive-distrib/1.0/</license></arXiv></metadata></record></GetRecord></OAI-PMH>'
    assert parse_oai_license(ok) == "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
    with pytest.raises(LicenseLookupError, match="idDoesNotExist"):
        parse_oai_license(b'<OAI-PMH><error code="idDoesNotExist">No matching identifier</error></OAI-PMH>')
    with pytest.raises(LicenseLookupError, match="sin <license>"):
        parse_oai_license(b"<OAI-PMH><GetRecord><record><metadata><arXiv><id>x</id></arXiv></metadata></record></GetRecord></OAI-PMH>")

    clock = {"t": 0.0}
    gate = HarvestGate(sleep=lambda d: clock.__setitem__("t", clock["t"] + d), now=lambda: clock["t"])
    client = ArxivClient(opener=lambda url, ua: b"<error code=\"badArgument\">x</error>" if "oai2" in url else b"not a tarball",
                         gate=gate, sleep=lambda d: None)
    client.now = lambda: clock["t"]
    out = harvest_one({"corpusid": 21, "arxiv_id": "9999.00021"}, client=client,
                      papers_root=tmp_path / "papers", dest=tmp_path / "passages", license_lookup=True)
    assert out["license"] == "" and out["license_error"].startswith("oai badArgument")
    assert [e["url"].split("/")[3][:5] for e in client.log] == ["oai2?", "e-pri"]
    assert client.gaps() and min(client.gaps()) >= 3.5



def test_license_off_by_default_and_retry_after_is_honored(tmp_path):
    import urllib.error

    from rrm.passages.arxiv import ArxivClient, HarvestGate, retry_after
    from rrm.passages.harvest import harvest_one

    urls = []
    client = ArxivClient(opener=lambda url, ua: (urls.append(url), b"not a tarball")[1],
                         gate=HarvestGate(sleep=lambda d: None, now=lambda: 0.0), sleep=lambda d: None)
    out = harvest_one({"corpusid": 22, "arxiv_id": "9999.00022"}, client=client,
                      papers_root=tmp_path / "papers", dest=tmp_path / "passages")
    assert out["license"] == "" and out["license_error"] is None
    assert len(urls) == 1 and "/e-print/" in urls[0]

    assert retry_after({"Retry-After": "30"}) == 30.0 and retry_after({}) is None and retry_after(None) is None
    sleeps = []
    codes = [429, 200]

    def flaky(url, ua):
        code = codes.pop(0)
        if code != 200:
            raise urllib.error.HTTPError(url, code, "slow", {"Retry-After": "20"}, None)
        return b"ok"

    client = ArxivClient(flaky, gate=HarvestGate(sleep=sleeps.append, now=lambda: 0.0), sleep=sleeps.append)
    assert client.get("https://export.arxiv.org/e-print/1") == b"ok"
    assert 20.0 in sleeps and client.log[0]["status"] == 429 and client.log[0]["retry_after"] == 20.0
