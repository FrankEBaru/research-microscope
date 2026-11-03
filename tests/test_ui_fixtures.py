"""Los fixtures sintéticos de la UI cargan en rrm.offline.Store y tienen la forma que lee la UI."""

import importlib.util
import json
import threading
import urllib.request
from pathlib import Path

from rrm.offline import Store, make_server

ROOT = Path(__file__).parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location("build_ui_fixtures", ROOT / "scripts" / "build_ui_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as res:
        return json.loads(res.read().decode())


def _post(port, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        return json.loads(res.read().decode())


def test_store_carga_el_set_sintetico(tmp_path, monkeypatch):
    monkeypatch.setenv("RRM_FEATURES", "core")
    mod = _builder()
    root = mod.build(tmp_path / "synth")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 2 and manifest["queries"][0]["slug"] == "prueba"
    store = Store(root)
    hit = store.question("prueba de interfaz")
    assert hit and hit["burst"] and hit["labels"]
    burst = hit["burst"]
    assert len(burst["papers"]) == 10 and len(burst["similar"]) == 14
    assert any(not row.get("year") for row in burst["papers"])
    assert all(2014 <= row["year"] <= 2024 for row in burst["papers"] + burst["similar"] if row.get("year"))
    layout = burst["layout"]
    assert layout["method"] == "specter2-knn" and len(layout["points"]) == 24
    assert len(layout["groups"]) == 4 and any(g.get("far") for g in layout["groups"])
    assert all(g["name"].startswith("test group") for g in layout["groups"])
    assert len(hit["labels"]["by_id"]) == 24
    flags = list(hit["labels"]["by_id"].values())
    assert sum(1 for f in flags if f["survey"]) == 1 and sum(1 for f in flags if f["retracted"]) == 1
    states = [row["status"] for row in store.status.values()]
    assert states.count("done") == 7 and states.count("abstract_only") == 2 and states.count("failed") == 1
    assert len(store.papers) == 3 and len(store.notes) == 1 and len(store.asks) == 2
    assert store.licenses["by_corpus"][str(mod.FULL)]["license"].endswith("/by/4.0/")
    assert "nonexclusive-distrib" in store.licenses["by_corpus"][str(mod.CLOSED)]["license"]


def test_el_servidor_responde_con_los_sinteticos(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_LICENSE_GATE", raising=False)
    monkeypatch.setenv("RRM_FEATURES", "core")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    mod = _builder()
    root = mod.build(tmp_path / "synth")
    httpd = make_server(root, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        burst = _get(port, "/burst?q=prueba%20de%20interfaz&n=10")
        assert burst["layout"]["method"] == "specter2-knn" and len(burst["papers"]) == 10
        assert _get(port, "/labels?q=prueba%20de%20interfaz")["ok"] is True
        full = _get(port, f"/paper?id={mod.FULL}")
        assert full["paper"]["rights"]["cls"] == "open" and full["paper"]["full"] is True
        kinds = {b["kind"] for b in full["paper"]["blocks"]}
        assert {"h", "p", "eq", "table", "fig"} <= kinds
        eq = next(b for b in full["paper"]["blocks"] if b["kind"] == "eq")
        assert eq["number"] == 1 and "\\sqrt{d_k}" in eq["tex"]
        table = next(b for b in full["paper"]["blocks"] if b["kind"] == "table")
        assert len(table["body"]) == 6
        closed = _get(port, f"/paper?id={mod.CLOSED}")
        blob = json.dumps(closed)
        assert closed["paper"]["rights"]["gated"] is True and closed["paper"]["full"] is False
        assert closed["paper"]["blocks"] and all(b.get("abs") for b in closed["paper"]["blocks"])
        assert "Cuerpo cerrado de prueba" not in blob
        notes = _post(port, "/notes", {"id": mod.FULL})
        assert sum(1 for n in notes["notes"] if n["generated"]) == 3
        assert any(n.get("kind") == "supuesto" and n["generated"] is False for n in notes["notes"])
        assert {a["type"] for a in notes["artifacts"]} == {"con_sin", "forma"}
        block_ids = {b["id"] for b in full["paper"]["blocks"]}
        assert all(n["block_id"] in block_ids for n in notes["notes"]) and all(a["block_id"] in block_ids for a in notes["artifacts"])
        for stage in ("frases", "revisar"):
            body = _post(port, "/ask", {"ids": [mod.FULL], "text": mod.ASK_TEXT, "stage": stage, "focus": str(mod.FULL)})
            assert all(body["parts"][name] for name in ("coincide", "contradice", "sin_respaldo", "te_falto"))
        assert _post(port, "/phrases", {"id": mod.FULL}) == {"ok": True, "offline": True}
    finally:
        httpd.shutdown()


def test_no_hay_texto_de_papers_reales(tmp_path):
    mod = _builder()
    root = mod.build(tmp_path / "synth")
    blob = " ".join(path.read_text(encoding="utf-8") for path in root.rglob("*.json"))
    assert "Paper de prueba" in blob and "Autora Prueba" in blob
    assert "Attention Is All You Need" not in blob and "Vaswani" not in blob
