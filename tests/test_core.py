"""RRM-31: flag core, caché de pregunta y offline sin Meta. Sin red ni Modal."""

import json
from pathlib import Path

from rrm.features import core_mode, features_mode
from rrm.offline import make_server
from rrm.search.qcache import (
    apply_status_cache,
    cached_burst,
    load_entry,
    normalize_question,
    save_entry,
)


def test_features_default_is_core(monkeypatch):
    monkeypatch.delenv("RRM_FEATURES", raising=False)
    assert features_mode() == "core"
    assert core_mode() is True
    monkeypatch.setenv("RRM_FEATURES", "all")
    assert features_mode() == "all" and core_mode() is False
    monkeypatch.setenv("RRM_FEATURES", "sí")
    assert features_mode() == "core"


def test_question_cache_roundtrip_and_short_list(tmp_path):
    assert normalize_question("  Cómo   Hacen ") == "cómo hacen"
    burst = {"query": "Cómo hacen", "n": 2, "papers": [{"corpusid": 1, "title": "A", "tldr": "uno"}, {"corpusid": 2, "title": "B"}]}
    save_entry(tmp_path, " cómo   hacen ", burst=burst, papers={"1": {"id": 1, "status": "done"}})
    got = load_entry(tmp_path, "CÓMO hacen")
    assert got["q"] == "cómo hacen"
    assert got["papers"]["1"]["status"] == "done"
    hit = cached_burst(got, 2)
    assert hit["cached"] is True and len(hit["papers"]) == 2 and hit["papers"][0]["tldr"] == "uno"
    assert cached_burst(got, 3) is None
    rows = apply_status_cache(
        [{"id": 1, "status": "missing"}, {"id": 2, "status": "queued"}],
        got["papers"],
    )
    assert rows[0]["status"] == "done" and rows[0]["cached"] is True
    assert rows[1]["status"] == "queued"


def test_normalize_matches_the_browser_rule():
    """The JS cache uses trim + lower + collapsed spaces. Keep these pairs in step."""
    pairs = [
        ("Attention Is All You Need", "attention is all you need"),
        ("  ¿Cuánto   cómputo? ", "¿cuánto cómputo?"),
        ("", ""),
    ]
    for raw, want in pairs:
        assert normalize_question(raw) == want


def test_offline_warm_file_cache_and_core_skips_muse(tmp_path, monkeypatch):
    root = tmp_path / "fx"
    (root / "burst").mkdir(parents=True)
    (root / "panorama").mkdir()
    (root / "subtopics").mkdir()
    (root / "status").mkdir()
    (root / "papers").mkdir()
    (root / "files" / "7").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({
        "version": 1,
        "queries": [{"slug": "hello", "q": "hello world"}],
    }), encoding="utf-8")
    (root / "burst" / "hello.json").write_text("{}", encoding="utf-8")
    (root / "subtopics" / "hello.json").write_text("{}", encoding="utf-8")
    (root / "panorama" / "hello.json").write_text(json.dumps([{"id": "t0", "mode": "sim"}]), encoding="utf-8")
    (root / "files" / "7" / "p0.png").write_bytes(b"png")
    monkeypatch.setenv("RRM_FEATURES", "core")
    monkeypatch.setenv("RRM_OFFLINE_PANORAMA", "meta")
    calls = []
    monkeypatch.setattr("rrm.panorama._muse", lambda *args, **kwargs: calls.append(args))
    httpd = make_server(root, "127.0.0.1", 0)
    port = httpd.server_address[1]
    import threading
    import urllib.request
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/warm", timeout=5) as res:
            body = json.loads(res.read().decode())
            assert res.status == 200 and body["ready"] is True and body["features"] == "core"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/file?id=7&name=p0.png", timeout=5) as res:
            assert res.headers.get("Cache-Control") == "public, max-age=86400"
            assert res.read() == b"png"
        data = json.dumps({"question": "hello world", "ids": ["7"]}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/panorama",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            body = json.loads(res.read().decode())
        assert body[0]["mode"] == "sim"
        assert calls == []
        prep = json.dumps({"ids": [7], "front": True}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/prepare",
            data=prep,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            body = json.loads(res.read().decode())
        assert body["front"] is True and body["papers"][0]["status"] == "missing"
    finally:
        httpd.shutdown()


def test_reader_serves_figures_in_parallel_and_core_skips_meta():
    root = Path(__file__).parents[1]
    reader = (root / "rrm/reader/serve.py").read_text(encoding="utf-8")
    burst = (root / "rrm/search/serve.py").read_text(encoding="utf-8")
    assert "@modal.concurrent(max_inputs=8)" in reader
    assert "enable_memory_snapshot=True" in burst
    assert "min_containers=" not in reader and "min_containers=" not in burst
    assert 'reason": "core"' in burst
    assert "if core_mode():" in reader
    ui = (root / "apps/reader/src/components/Engine.tsx").read_text(encoding="utf-8")
    assert "preparando el motor…" in ui
    assert "calentando el motor" not in ui
    assert "quiero leer este" in ui
    assert "data-devlog" in ui
