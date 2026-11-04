"""Compuerta de licencia. Mapa de prueba en tmp_path; sin datos reales ni red."""

import copy
import importlib.util
import json
import threading
from pathlib import Path

import pytest

from rrm.offline import make_server
from rrm.reader.notes import license_open
from rrm.reader.rights import (
    clip_text,
    gate_ask,
    gate_file,
    gate_on,
    gate_paper_response,
    gate_status_row,
    license_class,
    license_label,
    load_map,
    map_size,
    rights_for,
    share_alike,
    warn_map,
)

ROOT = Path(__file__).parents[1]
BODY = "UNIQUE BODY SENTENCE THAT MUST NOT LEAK FROM THE CLOSED PAPER."
LLAMA = "http://creativecommons.org/licenses/by/4.0/"
DPO = "http://creativecommons.org/licenses/by/4.0/"
DETR = "http://creativecommons.org/publicdomain/zero/1.0/"
ATTN = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
NC = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
ND = "https://creativecommons.org/licenses/by-nc-nd/4.0/"
SA = "https://creativecommons.org/licenses/by-sa/4.0/"
BY3 = "https://creativecommons.org/licenses/by/3.0/"
PD = "http://creativecommons.org/licenses/publicdomain/"


def _map(tmp_path):
    body = {
        "_source": "unit test",
        "2302.13971": {"license": LLAMA, "version": "v1", "corpusid": 1},
        "2305.18290": {"license": DPO, "version": "v3", "corpusid": 2},
        "2005.12872": {"license": DETR, "version": "v3", "corpusid": 3},
        "1706.03762": {"license": ATTN, "version": "v7", "corpusid": 4},
        "0000.00001": {"license": NC, "version": "v1", "corpusid": 5},
        "0000.00002": {"license": SA, "version": "v1", "corpusid": 6},
    }
    path = tmp_path / "licenses.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return load_map(path)


def _paper(cid, arxiv, sentence=BODY):
    return {
        "status": "done",
        "meta": {"corpusid": cid, "arxiv": arxiv, "status": "done", "pdf": True, "oa_pdf": "https://example.test/a.pdf", "pdf_path": "/tmp/a.pdf"},
        "paper": {
            "corpusid": cid,
            "arxivId": arxiv,
            "title": "T",
            "authors": ["A"],
            "date": "2020",
            "abstract": "Abstract stays.",
            "full": True,
            "license": "TeX notice stays",
            "figures": ["fig.png"],
            "images": ["fig.png"],
            "tables": [{"id": "t"}],
            "oaPdf": "https://example.test/a.pdf",
            "pdf": "source.pdf",
            "crops": [{"page": 0}],
            "refs": {"r": sentence},
            "blocks": [
                {"id": "b0", "kind": "p", "abs": True, "inlines": [{"t": "text", "v": "Abstract stays."}]},
                {"id": "b1", "kind": "p", "inlines": [{"t": "text", "v": sentence}]},
                {"id": "b2", "kind": "fig", "images": ["fig.png"]},
                {"id": "b3", "kind": "table", "body": [sentence]},
            ],
        },
    }


def test_class_and_label_table():
    rows = [
        (LLAMA, "open", "CC BY 4.0", False),
        (DPO, "open", "CC BY 4.0", False),
        (DETR, "open", "CC0 1.0", False),
        (PD, "open", "Public domain", False),
        (BY3, "open", "CC BY 3.0", False),
        (SA, "open", "CC BY-SA 4.0", True),
        (ATTN, "closed", "arXiv license", False),
        (NC, "closed", "CC BY-NC-SA 4.0", False),
        (ND, "closed", "CC BY-NC-ND 4.0", False),
        ("", "closed", "License unknown", False),
        ("https://example.test/custom", "closed", "License unknown", False),
        ("CC BY 4.0", "open", "CC BY 4.0", False),
    ]
    for url, cls, label, sa in rows:
        assert license_class(url) == cls, url
        assert license_label(url) == label, url
        assert share_alike(url) is sa, url
    assert license_open(LLAMA) is True
    assert license_open(PD) is True
    assert license_open(ATTN) is False
    assert license_open("") is False


def test_rows_and_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_LICENSE_GATE", raising=False)
    assert gate_on() is True
    m = _map(tmp_path)
    cases = [
        ("2302.13971", 1, "open", False, "CC BY 4.0", "v1"),
        ("2305.18290", 2, "open", False, "CC BY 4.0", "v3"),
        ("2005.12872", 3, "open", False, "CC0 1.0", "v3"),
        ("1706.03762", 4, "closed", True, "arXiv license", "v7"),
        ("0000.00001", 5, "closed", True, "CC BY-NC-SA 4.0", "v1"),
        ("0000.00002", 6, "open", False, "CC BY-SA 4.0", "v1"),
    ]
    for arxiv, cid, cls, gated, label, ver in cases:
        got = rights_for({"paper": {"arxivId": arxiv, "corpusid": cid}}, m)
        assert got["cls"] == cls and got["gated"] is gated and got["label"] == label and got["version"] == ver
        assert (got["sa"] is True) if arxiv == "0000.00002" else got["sa"] is False
    missing = rights_for({"paper": {"arxivId": "1999.00001", "corpusid": 99}}, m)
    assert missing["cls"] == "closed" and missing["gated"] is True and missing["label"] == "License unknown"
    no_ax = rights_for({"paper": {"corpusid": 100, "title": "no arxiv"}}, m)
    assert no_ax["cls"] == "closed" and no_ax["gated"] is True
    assert rights_for(4, m)["label"] == "arXiv license"


def test_closed_paper_keeps_only_the_abstract(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_LICENSE_GATE", raising=False)
    m = _map(tmp_path)
    src = _paper(4, "1706.03762v7")
    original = copy.deepcopy(src)
    out = gate_paper_response(src, m)
    assert src == original
    assert out["paper"]["full"] is False
    assert out["paper"]["rights"]["gated"] is True
    assert [b["id"] for b in out["paper"]["blocks"]] == ["b0"]
    assert out["paper"]["license"] == "TeX notice stays"
    assert out["status"] == "done"
    for key in ("figures", "images", "tables", "oaPdf", "pdf", "crops", "refs"):
        assert key not in out["paper"]
    assert "pdf" not in out["meta"] and "oa_pdf" not in out["meta"] and "pdf_path" not in out["meta"]
    assert BODY not in json.dumps(out)
    assert "Abstract stays." in json.dumps(out)
    opened = gate_paper_response(_paper(1, "2302.13971v1", sentence=BODY), m)
    assert opened["paper"]["full"] is True and len(opened["paper"]["blocks"]) == 4
    assert BODY in json.dumps(opened)


def test_status_file_crops_and_ask(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_LICENSE_GATE", raising=False)
    m = _map(tmp_path)
    row = gate_status_row({"id": 4, "status": "done", "text": True}, m)
    assert row["license"] == "arXiv license" and row["gated"] is True and row["text"] is False
    open_row = gate_status_row({"id": 1, "status": "done", "text": True}, m)
    assert open_row["text"] is True and open_row["gated"] is False
    assert gate_file(4, m) is True and gate_file(1, m) is False

    long = ("This sentence is long enough to clip. " * 20).strip()
    ask = {
        "extracts": [
            {"paper": 4, "section": "Body", "text": long, "contexts": ["around the body"]},
            {"paper": 1, "section": "Intro", "text": "Open extract stays.", "contexts": ["keep"]},
        ]
    }
    fresh = copy.deepcopy(ask)
    got = gate_ask(ask, m)
    assert ask == fresh
    closed, opened = got["extracts"]
    assert len(closed["text"]) <= 300 and closed["text"].endswith(".")
    assert "contexts" not in closed and closed["license"] == "arXiv license" and closed["arxiv"] == "1706.03762"
    assert opened == fresh["extracts"][1]
    assert clip_text("no period " * 40).endswith("…")

    root = tmp_path / "fx"
    (root / "papers").mkdir(parents=True)
    (root / "status").mkdir()
    (root / "crops").mkdir()
    (root / "files" / "1").mkdir(parents=True)
    (root / "files" / "4").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"version": 1, "queries": [{"slug": "q", "q": "q"}]}), encoding="utf-8")
    (root / "burst" / "q.json").parent.mkdir(parents=True)
    (root / "papers" / "1.json").write_text(json.dumps(_paper(1, "2302.13971")), encoding="utf-8")
    (root / "papers" / "4.json").write_text(json.dumps(_paper(4, "1706.03762")), encoding="utf-8")
    (root / "status" / "q.json").write_text(json.dumps({"papers": [{"id": 1, "status": "done", "text": True}, {"id": 4, "status": "done", "text": True}]}), encoding="utf-8")
    (root / "crops" / "1.json").write_text(json.dumps({"crops": [{"page": 0}]}), encoding="utf-8")
    (root / "crops" / "4.json").write_text(json.dumps({"crops": [{"page": 0, "file": "secret.png"}]}), encoding="utf-8")
    (root / "files" / "1" / "a.png").write_bytes(b"open-png")
    (root / "files" / "4" / "a.png").write_bytes(b"closed-png")
    (root / "licenses.json").write_text((tmp_path / "licenses.json").read_text(encoding="utf-8"), encoding="utf-8")
    httpd = make_server(root, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    def get(path):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    try:
        code, raw = get("/file?id=1&name=a.png")
        assert code == 200 and raw == b"open-png"
        code, raw = get("/file?id=4&name=a.png")
        assert code == 404
        code, raw = get("/crops?id=1")
        assert code == 200 and json.loads(raw)["crops"]
        code, raw = get("/crops?id=4")
        assert code == 200 and json.loads(raw) == {"crops": []}
        paper = json.loads(get("/paper?id=4")[1])
        assert BODY not in json.dumps(paper) and paper["paper"]["full"] is False
    finally:
        httpd.shutdown()


def test_gate_flag_words(monkeypatch):
    monkeypatch.setenv("RRM_LICENSE_GATE", "0")
    assert gate_on() is False
    monkeypatch.setenv("RRM_LICENSE_GATE", "on")
    assert gate_on() is True
    monkeypatch.setenv("RRM_LICENSE_GATE", "OFF")
    assert gate_on() is False


def test_gate_off_keeps_today(tmp_path, monkeypatch):
    monkeypatch.setenv("RRM_LICENSE_GATE", "off")
    m = _map(tmp_path)
    src = _paper(4, "1706.03762")
    out = gate_paper_response(src, m)
    bare = copy.deepcopy(out)
    bare["paper"].pop("rights")
    assert bare == src
    assert out["paper"]["rights"]["gated"] is False and out["paper"]["rights"]["label"] == "arXiv license"
    row = {"id": 4, "status": "done", "text": True}
    got = gate_status_row(row, m)
    assert got["text"] is True and got["gated"] is False and got["license"] == "arXiv license"
    assert gate_file(4, m) is False
    ask = {"extracts": [{"paper": 4, "text": BODY, "contexts": ["ctx"]}]}
    assert gate_ask(ask, m) is ask


def test_build_license_map_from_tiny_parquet(tmp_path):
    pytest.importorskip("pyarrow")
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({
        "id": ["2302.13971", "1706.03762", "9999.99999"],
        "license": [LLAMA, ATTN, SA],
        "versions": [["v1"], ["v1", "v2", "v3", "v4", "v5", "v6", "v7"], ["v1", "v2", "v3"]],
    })
    snap = tmp_path / "tiny.parquet"
    pq.write_table(table, snap)
    ids = tmp_path / "ids.txt"
    ids.write_text("2302.13971\n1706.03762\n", encoding="utf-8")
    corpus = tmp_path / "union_meta.json"
    corpus.write_text(json.dumps({"2302.13971": {"corpusid": 11}, "1706.03762": 44}), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("build_license_map", ROOT / "scripts" / "build_license_map.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "licenses.json"
    built = mod.build(str(snap), str(ids), str(out), str(corpus))
    assert built["2302.13971"] == {"license": LLAMA, "version": "v1", "corpusid": 11}
    assert built["1706.03762"]["version"] == "v7" and built["1706.03762"]["corpusid"] == 44
    assert "9999.99999" not in built and built["_source"]
    assert load_map(out)["by_corpus"]["44"]["arxiv"] == "1706.03762"

    papers = tmp_path / "fx" / "papers"
    papers.mkdir(parents=True)
    (papers / "11.json").write_text(json.dumps({
        "paper": {"arxivId": "2302.13971", "corpusid": 11},
    }), encoding="utf-8")
    (papers / "44.json").write_text(json.dumps({
        "meta": {"arxiv": "1706.03762v7", "corpusid": 44},
    }), encoding="utf-8")
    from_dir = mod.build(str(snap), str(ids), str(tmp_path / "from-dir.json"), str(tmp_path / "fx"))
    assert from_dir["2302.13971"]["corpusid"] == 11 and from_dir["1706.03762"]["corpusid"] == 44

    import sqlite3
    db = tmp_path / "passages.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE passages (arxiv TEXT, corpusid INTEGER, text TEXT)")
    con.execute("INSERT INTO passages VALUES ('2302.13971', 11, 'body')")
    con.execute("INSERT INTO passages VALUES ('1706.03762', 44, 'body')")
    con.commit()
    con.close()
    from_db = mod.build(str(snap), str(ids), str(tmp_path / "from-db.json"), str(db))
    assert from_db["1706.03762"]["corpusid"] == 44 and from_db["2302.13971"]["corpusid"] == 11


def test_fixture_open_does_not_weaken_the_live_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_LICENSE_GATE", raising=False)
    monkeypatch.delenv("RRM_LICENSE_FIXTURE", raising=False)
    body = {
        "_source": "unit test",
        "1706.03762": {"license": ATTN, "version": "v7", "corpusid": 4, "fixture_open": True},
        "2302.13971": {"license": LLAMA, "version": "v1", "corpusid": 1},
    }
    path = tmp_path / "licenses.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    m = load_map(path)
    closed = rights_for({"paper": {"arxivId": "1706.03762", "corpusid": 4}}, m)
    assert closed["cls"] == "closed" and closed["label"] == "arXiv license"
    assert closed["fixture"] is False and closed["gated"] is True
    stripped = gate_paper_response(_paper(4, "1706.03762v7"), m)
    assert stripped["paper"]["full"] is False
    assert BODY not in json.dumps(stripped)
    monkeypatch.setenv("RRM_LICENSE_FIXTURE", "true")
    still = rights_for({"paper": {"arxivId": "1706.03762", "corpusid": 4}}, m)
    assert still["gated"] is True and still["fixture"] is False
    monkeypatch.setenv("RRM_LICENSE_FIXTURE", "1")
    opened = rights_for({"paper": {"arxivId": "1706.03762", "corpusid": 4}}, m)
    assert opened["cls"] == "closed" and opened["label"] == "arXiv license"
    assert opened["fixture"] is True and opened["gated"] is False
    full = gate_paper_response(_paper(4, "1706.03762v7"), m)
    assert full["paper"]["full"] is True and BODY in json.dumps(full)
    neighbor = rights_for({"paper": {"arxivId": "2302.13971", "corpusid": 1}}, m)
    assert neighbor["fixture"] is False and neighbor["gated"] is False and neighbor["cls"] == "open"
    missing = rights_for({"paper": {"arxivId": "1999.00001", "corpusid": 99}}, m)
    assert missing["fixture"] is False and missing["gated"] is True


def test_warn_map_when_empty(capsys):
    assert warn_map("", {"by_arxiv": {}, "by_corpus": {}}) == 0
    text = capsys.readouterr().out
    assert "WARNING" in text and "closed" in text
    row = {"license": LLAMA}
    assert map_size({"by_arxiv": {"2302.13971": row}, "by_corpus": {"11": row}}) == 1
    assert warn_map("licenses.json", {"by_arxiv": {"2302.13971": row}, "by_corpus": {}}) == 1
    assert capsys.readouterr().out == ""
