"""Servidor offline. Sin red: fixture mínimo en un directorio temporal."""

import json
import threading
import urllib.error
import urllib.request

from rrm.offline import MISS, make_server


def _tree(tmp_path):
    root = tmp_path / "fx"
    (root / "burst").mkdir(parents=True)
    (root / "status").mkdir()
    (root / "subtopics").mkdir()
    (root / "panorama").mkdir()
    (root / "papers").mkdir()
    (root / "crops").mkdir()
    (root / "files" / "7").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({
        "version": 1,
        "queries": [{"slug": "hello", "q": "hello world", "panorama_mode": "sim", "panorama_fallback": True}],
    }), encoding="utf-8")
    (root / "burst" / "hello.json").write_text(json.dumps({
        "query": "hello world", "papers": [{"corpusid": 7, "title": "T"}],
    }), encoding="utf-8")
    (root / "status" / "hello.json").write_text(json.dumps({
        "papers": [{"id": 7, "status": "done"}],
    }), encoding="utf-8")
    (root / "subtopics" / "hello.json").write_text(json.dumps({
        "query": "hello world", "subtopics": ["a"],
    }), encoding="utf-8")
    (root / "panorama" / "hello.json").write_text(json.dumps([
        {"id": "t0", "statement": "s", "selections": [], "mode": "sim", "fallback": True, "fallback_reason": "timeout"},
    ]), encoding="utf-8")
    (root / "papers" / "7.json").write_text(json.dumps({
        "status": "done", "paper": {"corpusid": 7, "title": "T"},
    }), encoding="utf-8")
    (root / "crops" / "7.json").write_text(json.dumps({
        "id": 7, "status": "done", "pages": [0, 1], "crops": [{"page": 0, "file": "p0.png"}],
    }), encoding="utf-8")
    (root / "files" / "7" / "p0.png").write_bytes(b"png-bytes")
    return root


def _server(root):
    httpd = make_server(root, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _get(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, res.read(), res.headers.get("Content-Type")
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers.get("Content-Type")


def _post(port, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode())


def test_grabada_y_no_grabada(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_OFFLINE_PANORAMA", raising=False)
    httpd = _server(_tree(tmp_path))
    port = httpd.server_address[1]
    try:
        code, raw, _ = _get(port, "/burst?q=hello%20world&n=10")
        assert code == 200
        assert json.loads(raw)["papers"][0]["corpusid"] == 7

        code, raw, _ = _get(port, "/burst?q=otra%20pregunta")
        assert code == 404
        assert json.loads(raw)["error"] == MISS

        code, raw, _ = _get(port, "/burst?q=hello%20world&n=10", headers={"X-RRM-Demo": "cualquier-cosa"})
        assert code == 200

        code, raw, _ = _get(port, "/status?ids=7")
        assert json.loads(raw)["papers"][0]["status"] == "done"
        code, raw, _ = _get(port, "/status?ids=999")
        assert code == 404 and json.loads(raw)["error"] == MISS

        code, raw, _ = _get(port, "/paper?id=7")
        assert json.loads(raw)["paper"]["title"] == "T"
        code, raw, _ = _get(port, "/paper?id=8")
        assert json.loads(raw)["error"] == MISS

        code, raw, ctype = _get(port, "/file?id=7&name=p0.png")
        assert code == 200 and raw == b"png-bytes" and ctype.startswith("image/png")
        code, raw, _ = _get(port, "/file?id=7&name=../manifest.json")
        assert code == 404 and json.loads(raw)["error"] == MISS

        code, raw, _ = _get(port, "/crops?id=7&pages=0,1")
        body = json.loads(raw)
        assert code == 200 and body["crops"][0]["file"] == "p0.png"
        code, raw, _ = _get(port, "/crops?id=7&pages=9")
        assert json.loads(raw)["error"] == MISS

        code, raw, _ = _get(port, "/subtopics?q=hello%20world")
        assert json.loads(raw)["subtopics"] == ["a"]
        code, raw, _ = _get(port, "/subtopics?q=no")
        assert json.loads(raw)["error"] == MISS

        code, body = _post(port, "/panorama", {"question": "hello world", "ids": ["7"]})
        assert code == 200 and body[0]["fallback"] is True and body[0]["mode"] == "sim"
        code, body = _post(port, "/panorama", {"question": "no esta", "ids": ["7"]})
        assert code == 404 and body["error"] == MISS
    finally:
        httpd.shutdown()


_SENT = "The Transformer relies entirely on attention and dispenses with recurrence and convolution."


def _paper_with_sentence(root):
    paper = {
        "status": "done",
        "paper": {
            "corpusid": 7,
            "blocks": [{
                "kind": "p",
                "abs": True,
                "sents": [[{"t": "text", "v": _SENT}]],
                "inlines": [{"t": "text", "v": _SENT}],
            }],
        },
    }
    (root / "papers" / "7.json").write_text(json.dumps(paper), encoding="utf-8")


def test_panorama_meta_usa_los_papers_grabados(tmp_path, monkeypatch):
    """RRM_OFFLINE_PANORAMA=meta llama a Muse. El doble no toca la red."""
    root = _tree(tmp_path)
    _paper_with_sentence(root)
    calls = []

    def fake_muse(prompt, timeout):
        calls.append(prompt)
        return json.dumps({
            "themes": [{"statement": "Attention replaces recurrence.", "picks": ["0"]}],
        }), {"total_tokens": 3}

    monkeypatch.setenv("RRM_OFFLINE_PANORAMA", "meta")
    monkeypatch.setattr("rrm.panorama._muse", fake_muse)
    httpd = _server(root)
    port = httpd.server_address[1]
    try:
        code, body = _post(port, "/panorama", {"question": "how does attention replace recurrence", "ids": ["7"]})
        assert code == 200
        assert calls
        assert body[0]["mode"] == "meta" and body[0]["fallback"] is False
        assert body[0]["selections"][0]["quote"] == _SENT
        code, raw, _ = _get(port, "/crops?id=7&pages=0,1")
        assert json.loads(raw)["crops"][0]["file"] == "p0.png"
        code, body = _post(port, "/panorama", {"question": "", "ids": ["7"]})
        assert code == 400
    finally:
        httpd.shutdown()


def test_sin_flag_el_panorama_sigue_grabado(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_OFFLINE_PANORAMA", raising=False)
    monkeypatch.setenv("RRM_PANORAMA_MODE", "meta")

    def boom(*_a, **_k):
        raise AssertionError("no debe llamar a Muse")

    monkeypatch.setattr("rrm.panorama._muse", boom)
    httpd = _server(_tree(tmp_path))
    port = httpd.server_address[1]
    try:
        code, body = _post(port, "/panorama", {"question": "hello world", "ids": ["7"]})
        assert code == 200 and body[0]["mode"] == "sim" and body[0]["fallback_reason"] == "timeout"
    finally:
        httpd.shutdown()
