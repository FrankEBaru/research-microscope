"""RRM-51: display text keeps its casing; generated text starts with a capital."""

import numpy as np

from rrm.reader.feedback import _sentences, layer1
from rrm.search.layout import place_papers
from rrm.textcase import cap_first


def test_cap_first_only_touches_a_plain_lowercase_start(monkeypatch):
    monkeypatch.delenv("RRM_CASE", raising=False)
    assert cap_first("so it trains in parallel") == "So it trains in parallel"
    assert cap_first("«the encoder") == "«The encoder"
    assert cap_first("in-context learning") == "In-context learning"
    for keep in ("NeRF in the wild", "iPhone photos", "word2vec learns", "mip-NeRF models", "Already up", "¿qué", "3D scenes"):
        assert cap_first(keep) == (keep if keep != "¿qué" else "¿Qué")
    monkeypatch.setenv("RRM_CASE", "raw")
    assert cap_first("so it trains") == "so it trains"


def test_group_names_keep_the_titles_spelling(monkeypatch):
    monkeypatch.delenv("RRM_CASE", raising=False)
    rng = np.random.default_rng(2)
    titles = ["Mip-NeRF for NeRF scenes", "Fast NeRF scenes", "Graph neural networks for molecules", "Graph neural networks on molecules"]
    blobs = []
    for t in range(2):
        center = np.zeros(768)
        center[t] = 5.0
        blobs.append(center + rng.normal(scale=0.05, size=(20, 768)))
    papers = [{"corpusid": i + 1, "title": titles[(i // 20) * 2 + i % 2]} for i in range(40)]
    names = sorted(group["name"] for group in place_papers(papers, [], np.vstack(blobs))["groups"])
    assert names == ["NeRF scenes", "Neural networks"], names
    monkeypatch.setenv("RRM_CASE", "raw")
    raw = sorted(group["name"] for group in place_papers(papers, [], np.vstack(blobs))["groups"])
    assert all(name == name.lower() for name in raw), raw


def test_claims_start_with_a_capital_and_semicolons_do_not_cut(monkeypatch):
    monkeypatch.delenv("RRM_CASE", raising=False)
    assert _sentences("It uses LSTM layers; attention only links them. Done.") == [
        "It uses LSTM layers; attention only links them.",
        "Done.",
    ]
    kept = layer1({"afirmaciones": [{"text": "can be trained in parallel", "clase": "sin_respaldo", "cite": "", "paper_id": ""}], "te_falto": []}, [{"paper": 7, "text": "x"}])
    assert kept["sin_respaldo"][0]["text"] == "Can be trained in parallel"
