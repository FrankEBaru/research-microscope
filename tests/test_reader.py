"""Seconds-long checks for the reader parser. No network, Modal, or model download."""

import io
import tarfile
from pathlib import Path

from rrm.reader.fetch import Limiter, canon_arxiv, unpack_eprint
from rrm.reader.katex import katex_available
from rrm.reader.latex import (
    attach_katex,
    collect_macros,
    expand_math,
    is_pdfpages_wrapper,
    materialize_figures,
    parse_tex,
    parse_tree,
    plain,
)
from rrm.reader.ocr import blocks_from_content_list
from rrm.reader.pipeline import abstract_paper, mark_queued
from rrm.reader.sam import parse_sam_text, segment_pdf

MACRO = r"""
\documentclass{article}
\newcommand{\vect}[1]{\mathbf{#1}}
\DeclareMathOperator{\argmax}{arg\,max}
\begin{document}
\begin{equation}
y = \vect{x} + \argmax
\label{eq:y}
\end{equation}
See \eqref{eq:y}.
\end{document}
"""

INPUT_MAIN = r"""
\documentclass{article}
\begin{document}
\input{sec}
\end{document}
"""

FIGURE = r"""
\documentclass{article}
\begin{document}
\section{Intro}
\label{sec:intro}
\section*{Notes}
\begin{figure*}
\includegraphics{plot.pdf}
\caption{The plot of $x$.}
\label{fig:p}
\end{figure*}
\begin{weirdstuff}
keep me
\end{weirdstuff}
\end{document}
"""

WRAPPER = r"""
\documentclass{article}
\usepackage{pdfpages}
\begin{document}
\includepdf[pages=-]{adam.pdf}
\end{document}
"""

REAL = r"""
\documentclass{article}
\usepackage{pdfpages}
\begin{document}
\includepdf[pages=-]{card.pdf}
This paper still has a real discussion of training language models on mixed data
with an actual equation in the body so it must stay on the TeX path for parsing.
\begin{equation}
L = -\sum_i y_i
\end{equation}
\end{document}
"""


def test_macro_expansion_and_label_link():
    macros = collect_macros(MACRO)
    assert expand_math(r"\vect{x}+\argmax", macros) == r"\mathbf{x}+\operatorname{arg\,max}"
    paper = parse_tex(MACRO, arxiv_id="0")
    eqs = [b for b in paper["blocks"] if b["kind"] == "eq"]
    assert len(eqs) == 1
    assert r"\mathbf{x}" in eqs[0]["tex"]
    assert r"\operatorname{arg\,max}" in eqs[0]["tex"]
    assert eqs[0]["label"] == "eq:y"
    assert eqs[0]["number"] == 1
    refs = [x for b in paper["blocks"] if b["kind"] == "p" for x in b["inlines"] if x["t"] == "ref"]
    assert refs and refs[0]["target"] == eqs[0]["id"]
    assert refs[0]["number"] == 1
    if katex_available():
        attach_katex(paper["blocks"])
        assert eqs[0]["katex_ok"] is True


def test_input_inlining(tmp_path: Path):
    (tmp_path / "main.tex").write_text(INPUT_MAIN)
    (tmp_path / "sec.tex").write_text("Hello world from the section file.\n")
    parsed = parse_tree(tmp_path, arxiv_id="1")
    assert parsed["route"] == "latex"
    text = " ".join(plain(b["inlines"]) for b in parsed["paper"]["blocks"] if b["kind"] == "p")
    assert "Hello world from the section file" in text


def test_figure_star_section_star_and_raw(tmp_path: Path):
    (tmp_path / "main.tex").write_text(FIGURE)
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=120, height=80)
    page.insert_text((10, 40), "plot")
    doc.save(tmp_path / "plot.pdf")
    doc.close()
    parsed = parse_tree(tmp_path)
    paper = parsed["paper"]
    kinds = {b["kind"] for b in paper["blocks"]}
    assert kinds <= {"p", "h", "eq", "list", "fig", "table"}
    heads = [b for b in paper["blocks"] if b["kind"] == "h"]
    assert heads[0]["number"] == "1" and heads[0]["unnumbered"] is False
    assert heads[0]["label"] == "sec:intro"
    assert heads[1]["unnumbered"] is True and heads[1]["number"] is None
    fig = next(b for b in paper["blocks"] if b["kind"] == "fig")
    assert fig["label"] == "fig:p"
    assert "plot" in plain(fig["caption"]).lower() or "$x$" in plain(fig["caption"])
    raw = [b for b in paper["blocks"] if b.get("raw")]
    assert raw and "keep me" in plain(raw[0]["inlines"])
    n = materialize_figures(paper["blocks"], tmp_path, tmp_path / "figures")
    assert n == 1
    assert list((tmp_path / "figures").glob("*.png"))


def test_theorem_and_list_keep_display_math():
    tex = r"""
\documentclass{article}
\newtheorem{lem}{Lemma}
\begin{document}
\begin{lem}\label{lem:one}
A transformer computes
\begin{align}
a &= b \label{eq:ab}
\end{align}
\end{lem}
\begin{enumerate}
\item Kept iff
\[z = z\]
\end{enumerate}
\end{document}
"""
    paper = parse_tex(tex)
    eqs = [b for b in paper["blocks"] if b["kind"] == "eq"]
    assert [b["tex"].replace(" ", "") for b in eqs] == ["a&=b", "z=z"] or "a" in eqs[0]["tex"]
    assert any("a" in b["tex"] and "b" in b["tex"] for b in eqs)
    assert any(b["tex"].replace(" ", "") == "z=z" for b in eqs)
    assert any(b.get("label") == "eq:ab" for b in eqs)
    assert any(b["kind"] == "list" for b in paper["blocks"])


def test_pdfpages_wrapper_versus_real_tex():
    assert is_pdfpages_wrapper(WRAPPER)
    assert not is_pdfpages_wrapper(REAL)


def test_def_bracket_is_not_display_math():
    tex = r"""
\documentclass{article}
\def\[{\left[}
\begin{document}
The token \[ is a macro here, and \[x\] should not vanish.
\end{document}
"""
    paper = parse_tex(tex)
    text = " ".join(plain(b.get("inlines") or []) for b in paper["blocks"])
    assert "should not vanish" in text
    assert not any(b["kind"] == "eq" for b in paper["blocks"])


def test_unpack_eprint_tar_and_pdf(tmp_path: Path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = b"\\documentclass{article}\\begin{document}Hi\\end{document}\n"
        info = tarfile.TarInfo("main.tex")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    kind = unpack_eprint(buf.getvalue(), tmp_path / "tex")
    assert kind == "tex"
    assert (tmp_path / "tex" / "main.tex").is_file()
    kind = unpack_eprint(b"%PDF-1.4 fake", tmp_path / "pdf")
    assert kind == "pdf"
    assert (tmp_path / "pdf" / "source.pdf").read_bytes().startswith(b"%PDF")


def test_limiter_uses_the_injected_clock():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    lim = Limiter(3.2, sleep=sleep, now=lambda: now[0])
    lim.wait()
    lim.wait()
    assert slept == [3.2]
    assert canon_arxiv("arXiv:1706.03762v5") == "1706.03762"


def test_ocr_content_list_matches_schema():
    blocks = blocks_from_content_list([
        {"type": "text", "text": "Introduction", "text_level": 1},
        {"type": "equation", "text": "$$E = mc^2$$"},
        {"type": "image", "img_path": "images/a.png", "image_caption": ["Figure 1: a plot"]},
        {"type": "table", "table_caption": ["Table 1"], "table_body": "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"},
        {"type": "header", "text": "running head"},
    ])
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["h", "eq", "fig", "table"]
    eq = next(b for b in blocks if b["kind"] == "eq")
    assert eq["tex"] == "E = mc^2" and eq["source"] == "ocr"
    assert all(b["id"].startswith("b") for b in blocks)
    table = next(b for b in blocks if b["kind"] == "table")
    assert plain(table["head"][0][0]) == "a"
    assert plain(table["body"][0][1]) == "2"


def test_sam_parser_and_missing_key(tmp_path: Path, monkeypatch):
    text = (
        "<0f>0<|box;x1=10;y1=20;x2=40;y2=50;w=100;h=80;c=0.9|>"
        "<|mask;x=0;y=0;c=0.9;data=4,5,!abcd|>,"
        "1<|box;x1=1;y1=1;x2=2;y2=2;w=100;h=80|>"
    )
    hits = parse_sam_text(text)
    assert hits[0]["x1"] == 10 and hits[0]["y2"] == 50 and hits[0]["c"] == 0.9
    assert hits[0]["mask"].startswith("4,5,!")
    assert hits[1]["x2"] == 2
    assert parse_sam_text("") == []
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    pdf = tmp_path / "empty.pdf"
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=100, height=100)
    doc.save(pdf)
    doc.close()
    out = segment_pdf(pdf, tmp_path / "crops", max_pages=1)
    assert out["crops"] == [] and out["error"] == "no MODEL_API_KEY"
    assert (tmp_path / "crops" / "index.json").is_file()


def test_queue_and_abstract_shape(tmp_path: Path):
    assert mark_queued(tmp_path / "5", 5) == "queued"
    assert mark_queued(tmp_path / "5", 5) == "queued"
    paper = abstract_paper({
        "corpusid": 5, "title": "T", "abstract": "Hello there.", "tldr": "short",
        "authors": ["Ada"], "refs": {"s2:9": "Ada. A paper."},
    })
    assert paper["full"] is False and paper["source"] == "abstract"
    assert paper["tldr"] == "short" and paper["authors"] == ["Ada"]
    assert paper["refs"]["s2:9"] == "Ada. A paper."
    assert paper["blocks"][0]["kind"] == "p"


def test_macro_args_let_and_def_file(tmp_path: Path):
    tex = r"""
\documentclass{article}
\newcommand{\p}[2][x]{#1+#2}
\def\vect#1{\mathbf{#1}}
\newcommand{\myvec}[1]{\vec{#1}}
\let\vv\myvec
\DeclareMathOperator{\argmin}{arg\,min}
\begin{document}
\begin{equation}
a = \p{y} + \p[b]{z} + \vect x + \vv{w} + \argmin
\end{equation}
\end{document}
"""
    macros = collect_macros(tex)
    assert expand_math(r"\p{y}", macros) == "x+y"
    assert expand_math(r"\p[b]{z}", macros) == "b+z"
    assert expand_math(r"\vect x", macros) == r"\mathbf{x}"
    assert expand_math(r"\hat\bx_0", {"bx": {"n": 0, "opt": None, "body": r"\mathbf{x}"}}) == r"\hat{\mathbf{x}}_0"
    assert expand_math(r"\defeq p", {"defeq": {"n": 0, "opt": None, "body": r"\coloneqq"}}) == r"\coloneqq p"
    assert expand_math(r"\vv{w}", macros) == r"\vec{w}"
    assert r"\operatorname{arg\,min}" in expand_math(r"\argmin", macros)
    (tmp_path / "main.tex").write_text(r"""
\documentclass{article}
\input{body}
\begin{document}
\begin{equation}
z = \widecheck{q}
\end{equation}
\end{document}
""")
    (tmp_path / "body.tex").write_text("See the equation.\n")
    (tmp_path / "cmds.def").write_text(r"\newcommand{\widecheck}[1]{\check{#1}}" + "\n")
    parsed = parse_tree(tmp_path)
    eq = next(b for b in parsed["paper"]["blocks"] if b["kind"] == "eq")
    assert r"\check{q}" in eq["tex"]
    # unknown environment still keeps the raw TeX
    raw = parse_tex(r"\documentclass{article}\begin{document}\begin{mystery}keep\end{mystery}\end{document}")
    assert any(b.get("raw") and "keep" in plain(b["inlines"]) for b in raw["blocks"])


def test_priority_open_jumps_the_prefetch_queue():
    from rrm.reader.queue import forget, note, release

    order, hot = [], []
    for cid in (1, 2, 3):
        order, hot = note(order, hot, cid, front=False)
    assert order == [1, 2, 3]
    order, hot = note(order, hot, 3, front=True)
    assert order[0] == 3
    order, hot = release(order, hot, 3)
    assert order == [1, 2] and 3 in hot
    order, hot = note(order, hot, 3, front=False)
    assert order[0] == 3
    order, hot = note(order, hot, 9, front=True)
    order, hot = note(order, hot, 1, front=False)
    order, hot = note(order, hot, 9, front=False)
    assert order[0] == 9
    order, hot = forget(order, hot, 9)
    assert 9 not in order and 9 not in hot


def test_arxiv_burst_slots():
    from rrm.reader.fetch import BurstGate, arxiv_index_at, arxiv_slot_start

    starts = [arxiv_slot_start(i) for i in range(8)]
    assert starts[:4] == [0.0, 0.25, 0.5, 0.75]
    assert starts[4] == 2.0
    assert arxiv_index_at(0.8) == 4
    assert arxiv_index_at(0.5) == 2
    now = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    gate = BurstGate(sleep=sleep, now=lambda: now[0])
    for _ in range(5):
        gate.wait()
    # four gaps inside the burst, then the fifth request waits out the 1 s sleep
    assert len(slept) == 4
    assert abs(now[0] - 2.0) < 1e-9


def test_page_split_merges_in_order():
    from rrm.reader.ocr import merge_ocr_parts, page_spans

    assert page_spans(0) == []
    assert page_spans(1) == [(0, 1)]
    assert page_spans(15) == [(0, 4), (4, 8), (8, 12), (12, 15)]
    parts = [
        {"start": 10, "blocks": [{"kind": "p", "id": "b0", "inlines": [{"t": "text", "v": "c"}]}]},
        {"start": 0, "blocks": [{"kind": "h", "id": "b7", "level": 1, "unnumbered": False, "number": "1", "inlines": [{"t": "text", "v": "A"}]}]},
        {"start": 5, "blocks": [{"kind": "eq", "id": "b1", "tex": "b", "env": "display", "katex_ok": None, "source": "ocr", "raw": False, "sents": [1]}]},
    ]
    blocks = merge_ocr_parts(parts)
    assert [b["kind"] for b in blocks] == ["h", "eq", "p"]
    assert [b["id"] for b in blocks] == ["b0", "b1", "b2"]
    assert blocks[1]["tex"] == "b"
    assert "sents" not in blocks[1]


def test_stub_shape_and_ocr_fields():
    from rrm.reader.pipeline import apply_s2_fields, make_stub, paper_from_ocr

    info = {
        "corpusid": 4,
        "title": "Title",
        "authors": ["Ada Lovelace"],
        "abstract": "An abstract.",
        "tldr": "One line.",
        "arxiv": "1706.03762",
        "year": 2017,
        "refs": {"s2:8": "Semantic Scholar corpus 8"},
    }
    stub = make_stub(info)
    assert stub["full"] is False
    assert stub["title"] == "Title" and stub["authors"] == ["Ada Lovelace"]
    assert stub["abstract"] == "An abstract." and stub["tldr"] == "One line."
    assert stub["stage"] == "stub" and stub["stages"]["stub"] == "done"
    assert stub["stages"]["sections"] == "pending" and stub["stages"]["crops"] == "pending"
    assert stub["blocks"][0]["kind"] == "p"
    latex = {"title": "", "authors": [], "abstract": "", "refs": {}, "source": "latex", "blocks": []}
    apply_s2_fields(latex, info)
    assert latex["tldr"] == "One line." and latex["authors"] == ["Ada Lovelace"]
    assert latex["refs"]["s2:8"].startswith("Semantic Scholar")
    ocr = paper_from_ocr(info, [{"kind": "eq", "tex": "E=mc^2", "env": "display", "katex_ok": None, "source": "ocr", "raw": False}])
    assert ocr["source"] == "ocr" and ocr["full"] is True
    assert ocr["authors"] == ["Ada Lovelace"] and ocr["tldr"] == "One line."
    assert ocr["abstract"] == "An abstract." and "s2:8" in ocr["refs"]


def test_sections_land_before_the_parse_finishes(tmp_path: Path, monkeypatch):
    import io
    import tarfile

    from rrm.reader import pipeline

    tex = rb"""\documentclass{article}
\newcommand{\vect}[1]{\mathbf{#1}}
\begin{document}
\section{Intro}
\begin{equation}
y = \vect{x}
\end{equation}
\end{document}
"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("main.tex")
        info.size = len(tex)
        tf.addfile(info, io.BytesIO(tex))
    blob = buf.getvalue()
    monkeypatch.setattr(pipeline, "reader_identity", lambda *a, **k: {
        "corpusid": 9, "title": "From S2", "authors": ["Ada"], "abstract": "Abs",
        "tldr": "tl", "arxiv": "1234.5678", "refs": {"s2:1": "Semantic Scholar corpus 1"}, "year": 2020,
    })
    monkeypatch.setattr(pipeline, "arxiv_eprint", lambda arxiv: blob)
    monkeypatch.setattr(
        pipeline, "arxiv_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no pdf in unit test")),
    )
    stages = []
    real = pipeline._publish

    def spy(folder, meta, paper, commit, stage):
        stages.append(stage)
        return real(folder, meta, paper, commit, stage)

    monkeypatch.setattr(pipeline, "_publish", spy)
    out = pipeline.parse_corpus(9, tmp_path, None)
    assert stages.index("sections") < stages.index("done")
    paper = out["paper"]
    assert paper["tldr"] == "tl"
    assert "Ada" in paper["authors"]
    assert paper["refs"]["s2:1"].startswith("Semantic Scholar")
    eq = next(b for b in paper["blocks"] if b["kind"] == "eq")
    assert r"\mathbf{x}" in eq["tex"]
    assert out["meta"]["first_content_s"] is not None
    assert out["meta"]["sections_s"] <= out["meta"]["full_s"]
    assert paper["stages"]["sections"] == "done"
    assert paper["stages"]["crops"] == "pending"


def test_volume_authors_and_graph_refs(tmp_path: Path):
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    from rrm.reader.fetch import graph_reference_map, reader_identity

    release = tmp_path / "2026-10-20"
    index = release / "index"
    index.mkdir(parents=True)
    papers = release / "papers"
    papers.mkdir()
    abstracts = release / "abstracts"
    abstracts.mkdir()
    pq.write_table(pa.table({
        "corpusid": pa.array([4], type=pa.int64()),
        "title": ["Local title"],
        "arxiv": ["1706.03762"],
        "doi": [None],
        "tldr": ["local tldr"],
    }), index / "display.parquet")
    pq.write_table(pa.table({
        "corpusid": pa.array([4], type=pa.int64()),
        "authors": [[{"authorId": "1", "name": "Ada Lovelace"}]],
        "title": ["Local title"],
        "year": [2017],
    }), papers / "part.parquet")
    pq.write_table(pa.table({
        "corpusid": pa.array([4], type=pa.int64()),
        "abstract": ["From the volume."],
    }), abstracts / "part.parquet")
    np.save(index / "graph_ids.npy", np.array([4, 8], dtype=np.int64))
    np.save(index / "out_indptr.npy", np.array([0, 1, 1], dtype=np.int64))
    np.save(index / "out_indices.npy", np.array([1], dtype=np.int32))
    info = reader_identity(4, index / "display.parquet", remote=False, refs=True)
    assert info["authors"] == ["Ada Lovelace"]
    assert info["abstract"] == "From the volume."
    assert info["tldr"] == "local tldr"
    assert info["refs"]["s2:8"] == "Semantic Scholar corpus 8"
    assert graph_reference_map(index, 99) == {}


def test_crop_pages_are_capped_and_parallel(tmp_path: Path, monkeypatch):
    import pymupdf

    from rrm.reader.sam import parse_pages, segment_pages

    assert parse_pages("1-3,1,9") == [1, 2, 3, 9]
    assert parse_pages(",".join(str(i) for i in range(10))) == [0, 1, 2, 3]
    assert parse_pages("30,31") == []
    calls = []

    def fake(png, phrase, key, timeout=90):
        calls.append((phrase, len(png)))
        return [{"x1": 0, "y1": 0, "x2": 4, "y2": 4, "w": 10, "h": 10}]

    monkeypatch.setattr("rrm.reader.sam.segment_png", fake)
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    pdf = tmp_path / "pages.pdf"
    doc = pymupdf.open()
    for i in range(6):
        page = doc.new_page(width=80, height=80)
        page.insert_text((10, 40), str(i))
    doc.save(pdf)
    doc.close()
    out = segment_pages(pdf, tmp_path / "crops", list(range(6)))
    phrases = {row["phrase"] for row in out["crops"]}
    pages = {row["page"] for row in out["crops"]}
    assert phrases == {"diagram", "table"}
    assert pages == {0, 1, 2, 3}
    assert len(calls) == 8
    assert all(p in ("diagram", "table") for p, _ in calls)


def test_crops_page_with_no_hits_is_done(tmp_path, monkeypatch):
    import rrm.reader.sam as sam
    calls = []
    monkeypatch.setattr(sam, "api_key", lambda: "k")
    monkeypatch.setattr(sam, "render_selected", lambda pdf, pages, dpi=150: {p: b"png" for p in pages})
    monkeypatch.setattr(sam, "segment_png", lambda png, phrase, key, timeout=90: calls.append(phrase) or [])
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    out = sam.segment_pages(pdf, tmp_path / "crops", [0, 1])
    assert out["crops"] == [] and len(calls) == 4
    import json
    index = json.loads((tmp_path / "crops" / "index.json").read_text())
    assert index["done_pages"] == [0, 1]


def test_failed_chunk_merges_in_order_and_retries_once():
    from rrm.reader.latex import plain, text_tokens
    from rrm.reader.ocr import engine_from_log, merge_ocr_parts, page_spans, run_chunk

    assert page_spans(32) == [(i * 4, i * 4 + 4) for i in range(8)]
    assert engine_from_log("using vllm-engine") == "vllm"
    assert engine_from_log("fallback: transformers engine") == "transformers"
    assert engine_from_log("") == "unknown"
    parts = [
        {"start": 0, "end": 4, "ok": True, "blocks": [{"kind": "p", "inlines": text_tokens("A")}]},
        {"start": 4, "end": 8, "failed": True, "ok": False, "error": "timeout", "blocks": []},
        {"start": 8, "end": 12, "ok": True, "blocks": [{"kind": "p", "inlines": text_tokens("C")}]},
    ]
    blocks = merge_ocr_parts(parts)
    assert [plain(b["inlines"]) for b in blocks] == [
        "A",
        "[ocr failed pages 4-8: timeout]",
        "C",
    ]
    assert blocks[1]["raw"] is True and blocks[1]["failed"] is True
    assert [b["id"] for b in blocks] == ["b0", "b1", "b2"]
    calls = {"n": 0}

    def runner(pdf, out, timeout):
        calls["n"] += 1
        raise RuntimeError("hung")

    failed = run_chunk("x", "y", 0, 4, tries=2, runner=runner, load_blocks=lambda path: [])
    assert calls["n"] == 2
    assert failed["failed"] is True and failed["ok"] is False
    assert failed["start"] == 0 and failed["end"] == 4

    def flaky(pdf, out, timeout):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("once")
        return "vllm"

    calls["n"] = 2
    ok = run_chunk(
        "x", "y", 4, 8, tries=2, runner=flaky,
        load_blocks=lambda path: [{"kind": "p", "inlines": text_tokens("ok")}],
    )
    assert ok["ok"] is True and ok["engine"] == "vllm" and ok["attempts"] == 2
    assert plain(ok["blocks"][0]["inlines"]) == "ok"


def test_download_timeout_falls_back_and_gate_releases():
    import threading
    import time

    from rrm.reader.fetch import DownloadError, download_url, fetch_pdf, race_pdf_bytes

    class Slow:
        def read(self, n=65536):
            raise TimeoutError("timed out")

        def close(self):
            pass

    try:
        download_url(
            "http://example.test/slow.pdf", opener=lambda req, timeout: Slow(),
            total_timeout=5, connect_timeout=1,
        )
        raise AssertionError("expected timeout")
    except DownloadError as err:
        assert "30s" in str(err) or "timeout" in str(err)

    class Big:
        def __init__(self):
            self._sent = False

        def read(self, n=65536):
            if self._sent:
                return b""
            self._sent = True
            return b"x" * 200

        def close(self):
            pass

    try:
        download_url(
            "http://example.test/big.pdf", opener=lambda req, timeout: Big(),
            total_timeout=5, connect_timeout=1, max_bytes=100,
        )
        raise AssertionError("expected size cap")
    except DownloadError as err:
        assert "50MB" in str(err)

    def slow():
        raise DownloadError("download exceeded 30s")

    def fast():
        return b"%PDF-1.4\nhello"

    won = race_pdf_bytes([("arxiv_pdf", slow), ("oa_pdf", fast)])
    assert won["source"] == "oa_pdf" and won["data"].startswith(b"%PDF")
    assert any(row["source"] == "arxiv_pdf" and row["ok"] is False for row in won["timings"])

    started = time.time()

    def nap():
        time.sleep(2)
        return b"%PDF-1.4\nslow"

    won = race_pdf_bytes([("slow", nap), ("fast", fast)])
    assert won["source"] == "fast"
    assert time.time() - started < 1.0

    held = threading.Lock()

    class Gate:
        def wait(self):
            assert held.acquire(timeout=1)
            try:
                time.sleep(0.01)
            finally:
                held.release()

    class Body:
        def __init__(self):
            self._sent = False

        def read(self, n=65536):
            assert held.acquire(timeout=1), "gate held during transfer"
            held.release()
            if self._sent:
                return b""
            self._sent = True
            return b"%PDF-1.4\n" + b"a" * 8

        def close(self):
            pass

    data = download_url(
        "http://example.test/a.pdf", Gate(), opener=lambda req, timeout: Body(),
        total_timeout=5, connect_timeout=1,
    )
    assert data.startswith(b"%PDF")

    # Non-arXiv hosts do not take the harvest slot.
    import rrm.reader.fetch as fetch

    def boom():
        raise AssertionError("oa pdf waited on the arxiv gate")

    original_wait = fetch.ARXIV.wait
    original_open = fetch.urllib.request.urlopen
    fetch.ARXIV.wait = boom
    try:
        class Resp:
            def __init__(self):
                self._sent = False

            def read(self, n=65536):
                if self._sent:
                    return b""
                self._sent = True
                return b"%PDF-1.4\n" + b"z" * 8

            def close(self):
                pass

        fetch.urllib.request.urlopen = lambda req, timeout=0: Resp()
        blob = fetch_pdf("https://example.test/paper.pdf")
        assert blob.startswith(b"%PDF")
    finally:
        fetch.ARXIV.wait = original_wait
        fetch.urllib.request.urlopen = original_open


def test_author_templates_prefer_s2_names():
    from rrm.reader.latex import parse_tex
    from rrm.reader.pipeline import apply_s2_fields

    neurips = r"""
\documentclass{article}
\begin{document}
\author{
  Alice Smith\thanks{Equal contribution.} \\
  Department of Computer Science \\
  Stanford University \\
  \And
  Bob Jones \\
  Massachusetts Institute of Technology \\
  \texttt{bob@mit.edu}
}
\end{document}
"""
    assert parse_tex(neurips)["authors"] == ["Alice Smith", "Bob Jones"]
    ieee = r"""
\documentclass{article}
\begin{document}
\author{
\IEEEauthorblockN{Carol Danvers}
\IEEEauthorblockA{Dept. of Physics\\State University}
\and
\IEEEauthorblockN{Diego Vega}
\IEEEauthorblockA{Laboratory of AI}
}
\end{document}
"""
    assert parse_tex(ieee)["authors"] == ["Carol Danvers", "Diego Vega"]
    classic = r"""
\documentclass{article}
\begin{document}
\author{Eve Polastri \and Francis Ngannou\thanks{Work done at DeepMind.}}
\end{document}
"""
    assert parse_tex(classic)["authors"] == ["Eve Polastri", "Francis Ngannou"]
    icml = r"""
\documentclass{article}
\begin{document}
\author{Lin Wang$^{1}$ \and Maya Chen$^{2}$ \\
$^{1}$Google Research \and $^{2}$OpenAI}
\author{Grace Hopper}
\author{John von Neumann, Katherine Johnson}
\end{document}
"""
    assert parse_tex(icml)["authors"] == [
        "Lin Wang", "Maya Chen", "Grace Hopper", "John von Neumann", "Katherine Johnson",
    ]
    paper = parse_tex(classic)
    apply_s2_fields(paper, {"authors": ["Semantic Author"], "tldr": "", "abstract": "", "refs": {}})
    assert paper["authors"] == ["Semantic Author"]


def test_latex_upgrades_ocr_and_never_downgrades(tmp_path, monkeypatch):
    import time

    from rrm.reader import pipeline

    tex = b"\\documentclass{article}\\begin{document}Hello from tex.\\end{document}\n"
    pdf = b"%PDF-1.4\n" + b"0" * 16

    def run(eprint, ocr_fn):
        monkeypatch.setattr(pipeline, "arxiv_eprint", eprint)
        monkeypatch.setattr(pipeline, "arxiv_pdf", lambda *args, **kwargs: pdf)
        published = []

        def publish(paper, stage):
            published.append((stage, paper.get("source"), paper.get("upgraded_from")))

        info = {
            "corpusid": 1, "arxiv": "1234.5678", "title": "T", "authors": ["Ada"],
            "abstract": "A", "tldr": "",
        }
        folder = tmp_path / str(len(published) + id(eprint))
        folder.mkdir()
        meta = {"timings": pipeline._blank_timings(), "reason": None, "corpusid": 1, "ocr_gpu_s": 0.0}
        route, paper, _path = pipeline._fetch_and_parse(
            folder, info, meta, folder / "source.pdf", ocr_fn, publish,
        )
        return route, paper, published

    def slow_eprint(_arxiv):
        time.sleep(0.35)
        return tex

    def quick_ocr(_path, _work):
        time.sleep(0.05)
        return {
            "blocks": [{"kind": "p", "inlines": [{"t": "text", "v": "ocr"}]}],
            "seconds": 0.05, "gpu_s": 0.05, "page_count": 1,
            "chunks": [{"start": 0, "end": 1, "seconds": 0.05, "engine": "vllm", "ok": True}],
        }

    route, paper, published = run(slow_eprint, quick_ocr)
    assert route == "latex" and paper["source"] == "latex"
    assert paper["upgraded_from"] == "ocr"
    assert published[0][1] == "ocr"
    assert any(src == "latex" and up == "ocr" for _stage, src, up in published)
    assert "ocr" in (paper.get("upgraded_from"),)

    kept = pipeline.prefer_parsed({"source": "latex", "blocks": [1]}, {"source": "ocr", "blocks": [2]}, published=True)
    assert kept["source"] == "latex" and "upgraded_from" not in kept
    plain = pipeline.prefer_parsed({"source": "abstract"}, {"source": "ocr", "blocks": [2]}, published=False)
    assert plain["source"] == "ocr" and "upgraded_from" not in plain

    def fast_eprint(_arxiv):
        return tex

    def slow_ocr(_path, _work):
        time.sleep(0.3)
        return {
            "blocks": [{"kind": "p", "inlines": [{"t": "text", "v": "ocr"}]}],
            "seconds": 0.3, "gpu_s": 0.3, "page_count": 1,
        }

    route, paper, published = run(fast_eprint, slow_ocr)
    assert route == "latex" and paper["source"] == "latex"
    assert not paper.get("upgraded_from")
    assert all(src != "ocr" for _stage, src, _up in published)


def test_s2_key_header_and_stub_skips_retry(monkeypatch, tmp_path):
    import io
    import urllib.error
    import urllib.request

    from rrm.reader import fetch

    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        raise urllib.error.HTTPError(req.full_url, 429, "slow", hdrs=None, fp=io.BytesIO(b""))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    slept = []
    monkeypatch.setattr(fetch.time, "sleep", lambda s: slept.append(s))
    fetch.S2_LIMIT.next = 0
    monkeypatch.setenv("S2_API_KEY", "secret-key")
    info = fetch.reader_identity(123, None, remote=True, refs=False, shards=False)
    assert info["corpusid"] == 123
    assert slept == []
    assert len(calls) == 1
    assert calls[0].get_header("X-api-key") == "secret-key"

    monkeypatch.delenv("S2_API_KEY", raising=False)
    calls.clear()

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"[null]"

    def ok_open(req, timeout=30):
        calls.append(req)
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", ok_open)
    fetch.S2_CACHE_DIR = tmp_path
    fetch.S2_LIMIT.next = 0
    fetch.s2_batch([7])
    assert calls and calls[0].get_header("X-api-key") is None
