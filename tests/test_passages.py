"""Base de pasajes. Grafos, LaTeX y red sintéticos. Sin Modal, sin arXiv, sin el grafo real."""

import ast
import json
import threading
import urllib.error
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from rrm.passages.arxiv import (
    HOST,
    MIN_INTERVAL,
    ArxivClient,
    ArxivStopped,
    HarvestGate,
    parse_license,
    user_agent,
)
from rrm.passages.cache import latex_cache_ready, reader_cache_ready
from rrm.passages.cost import stage_estimate
from rrm.passages.cut import apply_anchor_overrides, cut_flags, resolve_seeds, theme_report, union_from_reports
from rrm.passages.embed import l2_normalize, passage_text, uses_proximity
from rrm.passages.harvest import acquire_harvest_lock, harvest_ids, harvest_one
from rrm.passages.load import answer, attach
from rrm.passages.meta import lookup_meta, meta_from_files
from rrm.passages.query import contains_symbol, query_rows
from rrm.passages.rows import extract_rows, excluded_headings, row_id
from rrm.passages.score import assemble_seeds, rank_by_citations, rank_neighborhood
from rrm.passages.store import build_manifest, compile_store, read_rows, save_paper_rows, write_faiss
from rrm.passages.union import even_quotas, quotas_for, title_notes, union_papers
from rrm.reader.latex import parse_tex
from rrm.reader.phrases import read_phrases
from rrm.search.encode import use_proximity
from rrm.search.graph import Graph

TEX = r"""
\documentclass{article}
\title{A Synthetic Scale Note}
\author{A. Example}
\begin{document}
\begin{abstract}
This note defines a toy scale for a score.
\end{abstract}
\section{Method}
The score divides by the factor below.
\begin{equation}
\sqrt{d_k}
\end{equation}
That factor keeps the product from growing.

The later sentence sets $\alpha$ to one.
\section{Results}
The toy run prints a single number.
\section*{Acknowledgments}
Thanks to nobody in particular.
\section{References}
A. Example wrote a note that is not a passage.
\appendix
\section{Grid}
\begin{tabular}{cc}
a & b \\
c & d \\
\end{tabular}
\end{document}
"""


def _text(value, math=None):
    nodes = [{"t": "text", "v": value}]
    if math:
        nodes = [{"t": "text", "v": value}, {"t": "math", "v": math}]
    return nodes


def _paper():
    before = _text("Before uses the symbol. ", r"\beta")
    after = _text("After the display.")
    later = _text("Alpha means one. ", r"\alpha")
    results = _text("The toy run prints one number.")
    thanks = _text("Thanks.")
    cited = _text("A fake citation.")
    return {
        "corpusid": 5,
        "arxivId": "9999.00001",
        "blocks": [
            {"kind": "h", "level": 1, "inlines": _text("Method")},
            {"kind": "p", "inlines": before, "sents": [before]},
            {"kind": "eq", "tex": r"\sqrt{d_k}"},
            {"kind": "h", "level": 2, "inlines": _text("Detail")},
            {"kind": "eq", "tex": r"\gamma"},
            {"kind": "p", "inlines": after, "sents": [after]},
            {"kind": "p", "inlines": later, "sents": [later]},
            {"kind": "h", "level": 1, "inlines": _text("Acknowledgments")},
            {"kind": "p", "inlines": thanks, "sents": [thanks]},
            {"kind": "h", "level": 1, "inlines": _text("References")},
            {"kind": "p", "inlines": cited, "sents": [cited]},
            {"kind": "h", "level": 1, "number": "A", "inlines": _text("Grid")},
            {"kind": "table", "head": [], "body": []},
            {"kind": "h", "level": 1, "number": "B", "inlines": _text("Notes")},
            {"kind": "p", "inlines": _text("A proof sentence stays."), "sents": [_text("A proof sentence stays.")]},
            {"kind": "h", "level": 1, "inlines": _text("Results")},
            {"kind": "p", "inlines": results, "sents": [results]},
        ],
    }


def _graph():
    ids = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90], dtype=np.int64)
    # 0 cita 40, 50 y 90. 1 cita 40 y 80. 5 (afuera) cita 30 y 40. 6 no cita.
    src = np.array([0, 0, 0, 1, 1, 5, 5], dtype=np.int64)
    dst = np.array([3, 4, 8, 3, 7, 2, 3], dtype=np.int64)
    cc = np.array([0, 0, 1000, 5, 5, 0, 9, 500, 5], dtype=np.int64)
    return Graph.from_edges(ids, src, dst), cc


def _row(rid, kind, text, latex, vector):
    return {
        "id": rid,
        "corpusid": 5,
        "arxiv_id": "9999.00001",
        "kind": kind,
        "section": "Method",
        "text": text,
        "latex": latex,
        "license": "http://creativecommons.org/licenses/by/4.0/",
        "url": "https://arxiv.org/abs/9999.00001",
        "vector": vector,
    }


class _Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []
        self._lock = threading.Lock()

    def now(self):
        with self._lock:
            return self.t

    def sleep(self, delay):
        with self._lock:
            self.sleeps.append(float(delay))
            self.t += float(delay)


def test_neighborhood_ignores_outside_cites_and_breaks_ties():
    graph, cc = _graph()
    ranked = rank_neighborhood(graph, [10, 20, 70, 10], cc)
    scores = {row["corpusid"]: row["score"] for row in ranked}
    assert scores[40] == 2
    assert scores[50] == 1 and scores[90] == 1 and scores[80] == 1
    assert 30 not in scores  # solo lo cita alguien de afuera
    assert 70 not in scores  # ancla: nadie del vecindario la cita
    assert [row["corpusid"] for row in ranked] == [40, 80, 50, 90]
    assert [row["corpusid"] for row in rank_by_citations(ranked)] == [80, 40, 50, 90]


def test_title_note_does_not_change_order():
    graph, cc = _graph()
    ranked = rank_neighborhood(graph, [10, 20], cc)
    notes = title_notes("A Survey and Primer")
    assert notes == ["survey", "primer"]
    assert title_notes("Experimental results") == []
    assert [row["corpusid"] for row in ranked] == [40, 80, 50, 90]


def test_seeds_put_anchor_first_and_cap_neighbors():
    assert assemble_seeds(7, [7, 8, 9, 10], k=2) == [7, 8, 9]
    resolved = resolve_seeds(
        {"name": "gcn", "anchor": None, "title": "GCN", "question": None},
        neighbors_of=lambda anchor: [anchor, 2, 3],
        first_hit=lambda question: 99,
        title_hit=lambda title: 4,
        k=200,
    )
    assert resolved["anchor"] == 4 and resolved["seeds"][0] == 4 and resolved["how"] == "title"
    assert apply_anchor_overrides(
        ({"name": "attention", "anchor": 1, "title": "t", "question": "q"},),
        "attention=15",
    )[0]["anchor"] == 15


def test_union_quotas_skip_duplicates_and_stop_at_the_cap():
    quotas = even_quotas(3, 2000)
    assert sum(quotas) == 2000 and max(quotas) - min(quotas) <= 1
    burst, source = quotas_for([1, 1, 2], 2000)
    assert source == "bursts" and sum(burst) == 2000 and burst[2] > burst[0]
    missing, source = quotas_for(None, 2000)
    assert missing == [] and source == "even"
    picked, took = union_papers([[1, 2, 3], [2, 4, 5]], [2, 2], limit=2000)
    assert picked == [1, 2, 4, 5] and took == [2, 2]
    capped, _took = union_papers([[1, 2, 3], [4]], [2, 2], limit=3)
    assert capped == [1, 2, 4]
    same, took = union_papers([[1, 1, 2]], [2], limit=10)
    assert same == [1, 2] and took == [2]


def test_extract_rows_context_defs_and_exclusions():
    rows = extract_rows(_paper(), arxiv_id="9999.00001", license="http://creativecommons.org/licenses/by/4.0/")
    again = extract_rows(_paper(), arxiv_id="9999.00001", license="http://creativecommons.org/licenses/by/4.0/")
    assert [row["id"] for row in rows] == [row["id"] for row in again]
    eqs = [row for row in rows if row["kind"] == "eq"]
    assert [row["latex"] for row in eqs] == [r"\sqrt{d_k}", r"\gamma"]
    assert eqs[0]["text"] == eqs[1]["text"]
    assert "Before uses the symbol." in eqs[0]["text"]
    assert "After the display." in eqs[0]["text"]
    assert eqs[0]["id"] == row_id(5, 2)
    sections = {row["section"] for row in rows}
    assert "Acknowledgments" not in sections and "References" not in sections and "Grid" not in sections
    assert any(row["kind"] == "p" and "proof sentence" in row["text"] and row["section"] == "Notes" for row in rows)
    assert any(row["kind"] == "p" and row["section"] == "Results" for row in rows)
    assert any(row["kind"] == "p" and "Before uses" in row["text"] for row in rows)
    defs = [row for row in rows if row["kind"] == "def"]
    assert len(defs) == 1 and defs[0]["latex"] == r"\alpha"
    assert defs[0]["id"] == row_id(5, 6, 0)
    assert all(r"\beta" not in row["latex"] or row["kind"] != "def" for row in rows)
    assert all(row["url"] == "https://arxiv.org/abs/9999.00001" for row in rows)
    assert "references" in excluded_headings()


def test_parsed_synthetic_tex_keeps_body_and_drops_back_matter():
    paper = parse_tex(TEX, arxiv_id="9999.00001")
    paper["corpusid"] = 11
    rows = extract_rows(paper, license="http://creativecommons.org/licenses/by/4.0/")
    eqs = [row for row in rows if row["kind"] == "eq"]
    assert len(eqs) == 1 and r"\sqrt{d_k}" in eqs[0]["latex"]
    assert "factor below" in eqs[0]["text"] and "keeps the product" in eqs[0]["text"]
    bodies = [row for row in rows if row["kind"] == "p"]
    assert any("factor below" in row["text"] for row in bodies)
    assert any("single number" in row["text"] for row in bodies)
    blob = " ".join((row["text"] + " " + row["section"]) for row in rows).lower()
    assert "thanks to nobody" not in blob
    assert "not a passage" not in blob
    assert all(row["section"] != "Grid" for row in rows)
    assert all(row["text"].strip() not in {"a", "b", "c", "d"} for row in rows)
    defs = [row for row in rows if row["kind"] == "def"]
    assert any(row["latex"] == r"\alpha" for row in defs)
    assert not any(row["kind"] == "def" and r"\sqrt" in row["latex"] for row in defs)


def test_symbol_query_returns_the_stored_row_or_empty():
    literal = _row("5:2", "eq", "Before the display.\nAfter the display.", r"\sqrt{d_k}", [1.0, 0.0])
    paraphrase = _row("5:9", "p", "the square root of d k", "", [0.0, 1.0])
    spaced = _row("5:4", "eq", "Other.", r"\sqrt{ d_k }", [0.2, 0.8])
    rows = [paraphrase, spaced, literal]
    vectors = l2_normalize([row.pop("vector") for row in rows])
    empty = query_rows(rows, vectors, {"symbol": r"\sqrt{missing}", "vector": [1.0, 0.0]})
    assert empty == []
    hits = query_rows(rows, vectors, {"symbol": r"\sqrt{d_k}", "local": "scale", "vector": [1.0, 0.0]})
    assert [row["id"] for row in hits] == ["5:2", "5:4"]
    assert hits[0]["text"] == "Before the display.\nAfter the display."
    assert hits[0]["cosine"] > hits[1]["cosine"]
    assert all(row["text"] != "the square root of d k" for row in hits)
    assert contains_symbol(spaced, r"\sqrt{d_k}")


def test_claim_returns_literal_rows_with_link_and_rerank_cannot_rewrite():
    prose = _row("5:8", "p", "We use this scale because the product grows.", "", [1.0, 0.0])
    other = _row("5:2", "eq", "Before.\nAfter.", r"\sqrt{d_k}", [0.0, 1.0])
    rows = [other, prose]
    vectors = l2_normalize([row.pop("vector") for row in rows])
    hits = query_rows(rows, vectors, {"claim": "why this scale", "vector": [1.0, 0.0]})
    assert hits[0]["kind"] == "p"
    assert hits[0]["text"] == "We use this scale because the product grows."
    assert hits[0]["url"].startswith("https://arxiv.org/abs/")
    assert hits[0]["license"].startswith("http://creativecommons.org/")
    assert hits[0]["cosine"] > hits[1]["cosine"]
    seen = {}

    def rerank(top):
        seen["n"] = len(top)
        top[0]["text"] = "paraphrase from the model"
        return list(reversed(top))

    extra = [_row(f"9:{i}", "p", f"row {i}", "", [0.0, 1.0]) for i in range(12)]
    pool = rows + extra
    vecs = np.vstack([vectors, l2_normalize(np.tile([0.0, 1.0], (12, 1)))])
    out = query_rows(pool, vecs, {"claim": "scale", "vector": [1.0, 0.0]}, rerank=rerank)
    assert seen["n"] == 10
    assert out[0]["text"] != "paraphrase from the model"
    assert {row["text"] for row in out} <= {row["text"] for row in pool}


def test_arxiv_gap_backoff_and_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("RRM_ARXIV_CONTACT", "ada@example.com")
    assert "ada@example.com" in user_agent()
    assert HOST == "https://export.arxiv.org"
    clock = _Clock()
    gate = HarvestGate(interval=1.0, sleep=clock.sleep, now=clock.now)
    assert gate.interval >= MIN_INTERVAL
    calls = []

    def opener(url, ua):
        calls.append((url, ua))
        return b"ok"

    client = ArxivClient(opener, gate=gate, sleep=clock.sleep)
    client.get(client.eprint_url("1706.03762v5"))
    client.get(client.eprint_url("1609.02907"))
    assert calls[0][0] == "https://export.arxiv.org/e-print/1706.03762"
    assert "ada@example.com" in calls[0][1]
    assert clock.sleeps and min(clock.sleeps) >= MIN_INTERVAL

    clock2 = _Clock()
    codes = [503, 200]

    def flaky(url, ua):
        code = codes.pop(0)
        if code != 200:
            raise urllib.error.HTTPError(url, code, "slow", {}, None)
        return b"<?xml"
    client = ArxivClient(flaky, gate=HarvestGate(sleep=clock2.sleep, now=clock2.now), sleep=clock2.sleep)
    assert client.get("https://export.arxiv.org/api/query?id_list=1") == b"<?xml"
    assert clock2.sleeps and min(s for s in clock2.sleeps if s > 0) >= MIN_INTERVAL

    burst = _Clock()
    codes = [429, 429, 429]

    def reject(url, ua):
        raise urllib.error.HTTPError(url, codes.pop(0), "slow", {}, None)

    client = ArxivClient(reject, gate=HarvestGate(sleep=burst.sleep, now=burst.now), sleep=burst.sleep)
    with pytest.raises(ArxivStopped):
        client.get("https://export.arxiv.org/e-print/1")
    assert burst.sleeps == sorted(burst.sleeps)
    assert burst.sleeps[-1] > burst.sleeps[0]

    entered = []
    shared = _Clock()

    def marker(url, ua):
        entered.append(shared.now())
        return b"x"

    client = ArxivClient(marker, gate=HarvestGate(sleep=shared.sleep, now=shared.now), sleep=shared.sleep)
    threads = [
        threading.Thread(target=client.get, args=(f"https://export.arxiv.org/e-print/{i}",))
        for i in (1, 2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    assert all(not thread.is_alive() for thread in threads)
    assert max(entered) - min(entered) >= MIN_INTERVAL

    assert parse_license(b'<entry><arxiv:license href="http://creativecommons.org/licenses/by/4.0/" /></entry>') == (
        "http://creativecommons.org/licenses/by/4.0/"
    )

    calls = {"n": 0}

    def fake(url, ua):
        calls["n"] += 1
        if "oai2" in url:
            return b'<arxiv:license href="http://creativecommons.org/licenses/by/4.0/" />'
        return TEX.encode("utf-8")

    client = ArxivClient(fake, gate=HarvestGate(sleep=lambda delay: None, now=lambda: 0.0), sleep=lambda delay: None)
    meta = {"corpusid": 11, "arxiv_id": "9999.00001", "title": "A Synthetic Scale Note", "has_emb": False}
    first = harvest_one(meta, client=client, papers_root=tmp_path / "papers", dest=tmp_path / "passages")
    second = harvest_one(meta, client=client, papers_root=tmp_path / "papers", dest=tmp_path / "passages")
    assert first["rows"] >= 1 and first["downloaded"] is True
    assert second["skipped"] is True and second["reason"] == "rows"
    assert calls["n"] == 1  # licencia apagada por defecto: solo el e-print
    folder = tmp_path / "papers" / "11"
    assert reader_cache_ready(folder) and latex_cache_ready(folder)
    assert read_phrases(folder)
    assert (folder / "src" / "main.tex").is_file()
    paper = json.loads((folder / "paper.json").read_text(encoding="utf-8"))
    assert paper["source"] == "latex" and paper["blocks"]


def test_manifest_metadata_and_serving_flag(tmp_path, monkeypatch):
    display = pa.table({
        "corpusid": pa.array([10], type=pa.int64()),
        "title": ["Attention Survey"],
        "year": pa.array([2017], type=pa.int64()),
        "venue": ["NeurIPS"],
        "citationcount": pa.array([9], type=pa.int64()),
        "arxiv": ["1706.03762v1"],
    })
    ext = pa.table({
        "corpusid": pa.array([20], type=pa.int64()),
        "title": ["Outside CS"],
        "year": pa.array([2018], type=pa.int64()),
        "venue": ["Other"],
        "citationcount": pa.array([3], type=pa.int64()),
    })
    cs = lookup_meta(10, display, ext, has_emb=True)
    assert cs["table"] == "display" and cs["arxiv_id"] == "1706.03762" and cs["authors"] == []
    assert cs["url"] == "https://arxiv.org/abs/1706.03762" and cs["has_emb"] is True
    other = lookup_meta(20, display, ext, arxiv_lookup=lambda cid: "9999.00001")
    assert other["table"] == "display_ext" and other["arxiv_id"] == "9999.00001"
    bare = lookup_meta(20, display, ext)
    assert bare["arxiv_id"] == "" and bare["authors"] == []

    import pyarrow.parquet as pq

    pq.write_table(display, tmp_path / "display.parquet")
    pq.write_table(ext, tmp_path / "display_ext.parquet")
    from_file = meta_from_files(10, tmp_path / "display.parquet", tmp_path / "display_ext.parquet")
    assert from_file["title"] == "Attention Survey" and from_file["arxiv_id"] == "1706.03762"

    meta = dict(cs)
    meta["license"] = "http://creativecommons.org/licenses/by/4.0/"
    rows = extract_rows(_paper(), arxiv_id=meta["arxiv_id"], license=meta["license"], url=meta["url"])
    meta["corpusid"] = 5
    save_paper_rows(tmp_path / "passages", meta, rows)
    save_paper_rows(tmp_path / "passages", {**meta, "corpusid": 5}, rows)
    from rrm.passages.store import save_failure

    save_failure(tmp_path / "passages", 20, "sin arxiv id")
    vectors = l2_normalize(np.ones((len(rows), 4), dtype=np.float32))
    write_faiss(tmp_path / "passages", vectors)
    manifest = compile_store(tmp_path / "passages", quota_source="even", commit="abc")
    assert manifest["quota_source"] == "even"
    assert manifest["excluded_headings"] == excluded_headings()
    assert manifest["failures"][0]["reason"] == "sin arxiv id"
    assert manifest["counts"]["eq"] >= 1 and manifest["counts"]["p"] >= 1 and manifest["counts"]["def"] == 1
    assert manifest["index"]["type"] == "IndexFlatIP" and manifest["index"]["built"] is True
    assert manifest["versions"]["parser"] == "rrm.reader.latex"
    assert manifest["reader_cache"].startswith("save_paper")
    again = compile_store(tmp_path / "passages")
    assert again["quota_source"] == "even"
    stored = read_rows(tmp_path / "passages" / "rows.parquet")
    assert stored[0]["text"] == rows[0]["text"] and stored[0]["latex"] == rows[0]["latex"]

    monkeypatch.delenv("RRM_PASSAGES", raising=False)
    holder = type("Holder", (), {"loaded": ["faiss"]})()
    attach(holder, tmp_path)
    assert not hasattr(holder, "passages") and holder.loaded == ["faiss"]
    assert answer(None, {"symbol": r"\sqrt{d_k}"}) == {"enabled": False, "rows": []}

    monkeypatch.setenv("RRM_PASSAGES", "1")
    attach(holder, tmp_path)
    assert "passages" in holder.loaded
    payload = answer(holder.passages, {"symbol": r"\sqrt{d_k}", "vector": np.ones(4, dtype=np.float32)})
    assert payload["enabled"] is True
    assert payload["rows"] and r"\sqrt{d_k}" in (payload["rows"][0]["latex"] + payload["rows"][0]["text"])
    assert payload["rows"][0]["text"] == next(row["text"] for row in rows if row["kind"] == "eq")
    missing = answer(holder.passages, {"symbol": r"\notasymbol"})
    assert missing["rows"] == []


def test_cut_stops_when_the_top_matches_global_citations():
    graph, cc = _graph()
    report = theme_report(graph, cc, [10, 20], lambda cid: {"title": "A Primer", "year": 2017})
    assert report["top"][0]["corpusid"] == 40
    assert report["by_citations"][0]["corpusid"] == 80
    assert report["top"][0]["title_notes"] == ["primer"]
    assert report["same_order"] is False
    flags = cut_flags([{"same_order": True, "top": [1, 2, 3, 4, 5], "overlap": 5}])
    assert flags["stop"] is True
    with pytest.raises(RuntimeError):
        union_from_reports([{"ranked_ids": [1, 2], "same_order": True, "top": [1, 2, 3, 4, 5], "overlap": 5}])
    forced = union_from_reports(
        [{"ranked_ids": [1, 2, 3], "same_order": True, "top": [1, 2, 3, 4, 5], "overlap": 5}],
        ignore_stop=True,
    )
    assert forced["ids"] == [1, 2, 3] and forced["quota_source"] == "even"


def test_lock_blocks_a_second_machine(tmp_path):
    acquire_harvest_lock(tmp_path)
    with pytest.raises(RuntimeError, match="una sola máquina"):
        acquire_harvest_lock(tmp_path)
    harvest_ids([], {}, client=None, papers_root=tmp_path, dest=tmp_path, break_lock=True)
    assert not (tmp_path / "harvest.lock").exists()


def test_missing_arxiv_id_adds_no_rows(tmp_path):
    result = harvest_one(
        {"corpusid": 8, "title": "Outside"},
        client=None,
        papers_root=tmp_path / "papers",
        dest=tmp_path / "passages",
    )
    assert result["reason"] == "sin arxiv id" and result["rows"] == 0
    again = harvest_one(
        {"corpusid": 8, "arxiv_id": "9999.00008"},
        client=None,
        papers_root=tmp_path / "papers",
        dest=tmp_path / "passages",
    )
    assert again["skipped"] is True and again["reason"] == "failed"


def test_pdf_eprint_is_a_recorded_miss(tmp_path):
    def opener(url, ua):
        if "api/query" in url:
            return b"<feed></feed>"
        return b"%PDF-1.4 synthetic"

    client = ArxivClient(opener, gate=HarvestGate(sleep=lambda delay: None, now=lambda: 0.0), sleep=lambda delay: None)
    result = harvest_one(
        {"corpusid": 3, "arxiv_id": "9999.00002"},
        client=client,
        papers_root=tmp_path / "papers",
        dest=tmp_path / "passages",
    )
    assert result["reason"] == "sin TeX" and result["rows"] == 0
    again = harvest_one(
        {"corpusid": 3, "arxiv_id": "9999.00002"},
        client=client,
        papers_root=tmp_path / "papers",
        dest=tmp_path / "passages",
    )
    assert again["skipped"] is True


def test_passage_text_asks_for_proximity_and_stage_costs_are_estimates():
    row = {"text": "short", "latex": r"\sqrt{d_k}"}
    assert uses_proximity(row) is True
    assert use_proximity("short query") is False
    assert "\n" in passage_text(row)
    total = 0.0
    for stage in ("e0", "e1", "e2", "e3", "e4"):
        est = stage_estimate(stage)
        assert est["measured"] is False and est["note"].startswith("[I]")
        total += est["usd_total"]
    assert total < 1.0


def test_modal_entrypoints_exist_and_are_not_imported():
    source = Path("rrm/passages/app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert {"e0", "e1", "e2", "e3", "e4"} <= names
    assert "modal run rrm/passages/app.py::e0" in source
    assert "RRM_PASSAGES=1" in source
    serve = Path("rrm/search/serve.py").read_text(encoding="utf-8")
    assert "attach(self, root)" in serve
    assert "def passages_query" in serve
    assert "def encode_proximity" in Path("rrm/search/encode.py").read_text(encoding="utf-8")
