"""Portada de LaTeX no entra al top-k. Precisión: párrafos, ecuaciones y definiciones se quedan."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rrm.reader.passage_junk import filter_passage_rows, is_junk_passage, junk_filter_enabled
from rrm.reader.passage_db import search_embedding

_DPO = (
    "Direct preference optimization trains a policy from pairwise preferences "
    "without fitting an explicit reward model, by classifying the preferred "
    "completion against the rejected one."
)
_ATTN = (
    "Scaled dot-product attention computes the weights as a softmax over the "
    "product of queries and keys, divided by the square root of the key dimension."
)
_LORA = (
    "LoRA freezes the pretrained weight and learns a low-rank update, so the "
    "forward pass adds BA to the original matrix while the rank stays small."
)
_ROPE = (
    "Rotary position embeddings rotate each pair of coordinates by an angle "
    "that depends on the token index, which encodes relative position inside the attention score."
)

_KEEP = [
    _DPO,
    _ATTN,
    _LORA,
    _ROPE,
    "The title and the authors sit in the preamble, but this paragraph defines the loss we optimize.",
    "We replace the missing token xxx with the model's estimate and keep training on the remaining labels.",
    r"We do not expand \newcommand{\foo}{bar} inside the training loop of the preference model.",
    (
        r"\begin{abstract} We derive the optimal policy for a preference model and "
        r"show that the same gradient updates the language model without a reward head. "
        r"The experiments cover summarization and dialogue.\end{abstract}"
    ),
    r"The update is $W_0 + BA$, where the rank of the factors is much smaller than the width.",
    "Direct Preference Optimization: Your Language Model is Secretly a Reward Model",
]

_JUNK = [
    r"\icmlaffiliation{yyy}{Meta}",
    r"\icmlauthor{Jane Doe}{yyy}",
    r"\icmltitle{Direct Preference Optimization: Your Language Model is Secretly a Reward Model}",
    r"\icmlkeywords{preference optimization, language models, reinforcement learning}",
    r"\begin{abstract}\end{abstract}",
    r"\begin{abstract} yyy \end{abstract}",
    r"\icmlauthor{Rafael Rafailov}{yyy}" "\n" r"\icmlaffiliation{yyy}{Stanford University}" "\n" r"\icmlaffiliation{xxx}{Meta}",
    r"\documentclass{article}" "\n" r"\usepackage{icml2023}",
    r"\newcommand{\loss}{\sum_i y_i}",
    r"\icmlcorrespondingauthor{A}{a@meta.com}",
    "yyy xxx zzz",
    "yyy Meta",
    r"\title{Attention Is All You Need}",
    r"\author{Ashish Vaswani \and Noam Shazeer} \maketitle",
    r"\begin{keywords} direct preference optimization, language models \end{keywords}",
]


def test_junk_examples_are_front_matter():
    for text in _JUNK:
        assert is_junk_passage(text), text


def test_real_passages_stay():
    for text in _KEEP:
        assert not is_junk_passage(text), text


def test_equations_and_definitions_stay():
    eq = r"\mathrm{softmax}\left(\frac{QK^{\top}}{\sqrt{d_k}}\right)V"
    assert not is_junk_passage("", eq, kind="eq")
    assert not is_junk_passage(_ATTN, eq, kind="eq")
    # La ecuación se queda aunque el texto de alrededor sea la afiliación.
    assert not is_junk_passage(r"\icmlaffiliation{yyy}{Meta}", eq, kind="eq")
    assert is_junk_passage(r"\icmlaffiliation{yyy}{Meta}", "", kind="eq")
    assert not is_junk_passage(
        "LoRA learns a low-rank update of the frozen weight.",
        r"W_0 + BA",
        kind="def",
    )
    assert is_junk_passage(r"\icmlkeywords{LoRA, adapters}", "", kind="def")
    assert not is_junk_passage(_DPO, "", kind="p")


def test_flag_defaults_on_and_can_turn_off(monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES_FILTER_JUNK", raising=False)
    assert junk_filter_enabled() is True
    monkeypatch.setenv("RRM_PASSAGES_FILTER_JUNK", "")
    assert junk_filter_enabled() is True
    rows = [{"text": r"\icmltitle{Direct Preference Optimization}", "latex": "", "kind": "p"}]
    assert filter_passage_rows(rows) == []
    monkeypatch.setenv("RRM_PASSAGES_FILTER_JUNK", "0")
    assert junk_filter_enabled() is False
    assert filter_passage_rows(rows) == rows
    monkeypatch.setenv("RRM_PASSAGES_FILTER_JUNK", "off")
    assert filter_passage_rows(rows) == rows


def _write_db(tmp_path, rows, vectors):
    faiss = pytest.importorskip("faiss")
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "rows.parquet")
    mat = np.asarray(vectors, dtype=np.float32)
    faiss.normalize_L2(mat)
    index = faiss.IndexFlatIP(mat.shape[1])
    index.add(mat)
    faiss.write_index(index, str(tmp_path / "faiss.index"))


def _row(row_id, text, latex="", kind="p"):
    return {
        "id": row_id, "corpusid": 1, "arxiv_id": "1", "kind": kind, "section": "S",
        "text": text, "latex": latex, "license": "", "url": "",
    }


def test_lookup_skips_preamble_and_overfetches(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES_FILTER_JUNK", raising=False)
    rows = [_row(f"j{i}", r"\icmlaffiliation{yyy}{Meta}") for i in range(34)]
    rows.append(_row("real", _DPO))
    vectors = [[1.0, 0.001 * (34 - i)] for i in range(34)]
    vectors.append([0.2, 0.1])
    _write_db(tmp_path, rows, vectors)
    query = np.array([1.0, 0.0], dtype=np.float32)
    got = search_embedding(query, k=1, root=tmp_path)
    assert [row["id"] for row in got] == ["real"]
    assert got[0]["cosine"] < 0.99


def test_flag_off_returns_the_preamble_row(tmp_path, monkeypatch):
    monkeypatch.setenv("RRM_PASSAGES_FILTER_JUNK", "0")
    rows = [
        _row("junk", r"\icmlkeywords{direct preference optimization, language models}"),
        _row("real", _DPO),
    ]
    _write_db(tmp_path, rows, [[1.0, 0.0], [0.2, 0.1]])
    got = search_embedding(np.array([1.0, 0.0], dtype=np.float32), k=1, root=tmp_path)
    assert got[0]["id"] == "junk"


def test_mask_overrides_the_text_rule(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_PASSAGES_FILTER_JUNK", raising=False)
    rows = [_row("marked", _DPO), _row("other", _LORA)]
    _write_db(tmp_path, rows, [[1.0, 0.0], [0.0, 1.0]])
    np.save(tmp_path / "junk_mask.npy", np.array([True, False]))
    got = search_embedding(np.array([1.0, 0.0], dtype=np.float32), k=1, root=tmp_path)
    assert got[0]["id"] == "other"


def test_mask_script_counts_and_writes(tmp_path):
    rows = [
        _row("j", r"\icmlaffiliation{yyy}{Meta}"),
        _row("p", _ATTN),
        _row("e", "", r"\frac{QK}{\sqrt{d_k}}", kind="eq"),
        _row("k", r"\title{Scaled Dot-Product Attention}"),
    ]
    parquet = tmp_path / "rows.parquet"
    pq.write_table(pa.Table.from_pylist(rows), parquet)
    out = tmp_path / "junk_mask.npy"
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "passage_junk_mask.py"),
         "--rows", str(parquet), "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    assert "junk 2 / filas 4 (50.00%)" in proc.stdout
    mask = np.load(out)
    assert mask.tolist() == [True, False, False, True]
    sample = subprocess.run(
        [sys.executable, str(root / "scripts" / "passage_junk_mask.py"),
         "--rows", str(parquet), "--sample", "4", "--seed", "0"],
        check=True, capture_output=True, text=True,
    )
    assert "muestra 4 de 4" in sample.stdout
    assert "50.00%" in sample.stdout
