"""scripts/e2e_bench.py against a local fake of the burst + reader. No Modal, no Meta, no external network."""

import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import e2e_bench as eb  # noqa: E402

from rrm import panorama as pn  # noqa: E402
from rrm.demo_guard import check  # noqa: E402
from rrm.reader.latex import parse_tex  # noqa: E402
from rrm.reader.pipeline import abstract_paper  # noqa: E402

TEX = r"""
\documentclass{article}
\begin{document}
\begin{abstract}
Scaling laws show that loss falls as a power law in compute, data size and parameters.
\end{abstract}
\section{Results}
Attention is all the model uses to relate positions of the sequence to each other.
\begin{figure}\includegraphics{plot.png}\caption{Loss.}\label{fig:l}\end{figure}
\end{document}
"""
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def make_world(now):
    done = parse_tex(TEX, arxiv_id="1706.03762")
    absonly = abstract_paper({"arxiv": "", "corpusid": 2, "abstract": "Attention helps models relate far apart positions in text.", "title": "B"})
    return {
        1: {"row": {"status": "done", "ocr_gpu_s": 5.0, "ocr_invoked_at": now + 1}, "paper": done},
        2: {"row": {"status": "abstract_only", "reason": "no arXiv e-print and no open-access PDF"}, "paper": absonly},
        3: {"row": {"status": "failed", "reason": "pdf failed: timeout"}, "paper": {"blocks": []}},
    }


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("RRM_DEMO_TOKEN", "t0k")
    world, polls = make_world(time.time()), {"n": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(raw)

        def guard(self, q):
            code = check(self.headers.get("X-RRM-Demo"), (q.get("k") or [None])[0] if self.path.startswith("/file") else None, self.headers.get("Origin"))
            if code:
                self.send(code, {})
            return code

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if self.guard(q):
                return
            if u.path == "/burst":
                papers = [{"corpusid": i, "title": f"P{i}", "year": 2020} for i in world] + [{"corpusid": None, "title": "x"}]
                return self.send(200, {"papers": papers, "edges": [], "subtopics": []})
            if u.path == "/status":
                polls["n"] += 1
                ids = [int(x) for x in q["ids"][0].split(",")]
                rows = [{"id": i, **(world[i]["row"] if polls["n"] > 1 else {"status": "queued"})} for i in ids]
                return self.send(200, {"papers": rows})
            if u.path == "/paper":
                i = int(q["id"][0])
                return self.send(200, {"status": world[i]["row"]["status"], "meta": {}, "paper": world[i]["paper"]})
            if u.path == "/file":
                return self.send(200, PNG, "image/png") if q["name"][0] == "plot.png" else self.send(404, {})
            self.send(404, {})

        def do_POST(self):
            if self.guard({}):
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            question, ids = pn.parse_request(body)
            docs = pn.docs_for("/x", ids, lambda f: world[int(f.name)]["row"], lambda f: world[int(f.name)]["paper"])
            return self.send(200, pn.run(question, docs))

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("BURST", url)
    monkeypatch.setenv("READER", url)
    yield url
    srv.shutdown()


def run(tmp_path, *extra):
    out = tmp_path / "r.json"
    rc = eb.main(["--question", "attention scaling", "--poll-interval", "0.01", "--out", str(out), *extra])
    return rc, json.loads(out.read_text()) if out.exists() else None


def test_happy_path(server, monkeypatch, tmp_path):
    monkeypatch.setenv("RRM_DEMO_TOKEN", "t0k")
    rc, rep = run(tmp_path)
    s = rep["summary"]
    q = rep["questions"][0]
    assert rc == 0, rep
    assert q["states"] == {"done": 1, "abstract_only": 1, "failed": 1}
    assert q["bundle_problems"] == [] and q["figure_file"]["ok"] and q["figure_file"]["bytes"] > 0
    assert q["panorama"]["selections"] >= 1 and q["panorama"]["gate_rejected"] == []
    assert s["gpu_papers_this_run"] == 1 and s["gpu_cost_usd_ESTIMATE"] == round(5 * eb.L4_USD_PER_S, 4)
    assert "t0k" not in json.dumps(rep) and "127.0.0.1" not in json.dumps(rep)


def test_wrong_token_stops_the_run(server, monkeypatch, tmp_path):
    real = eb.Client
    monkeypatch.setattr(eb, "Client", lambda burst, reader, token, budget: real(burst, reader, "wrong", budget))
    rc, rep = run(tmp_path)
    assert rc == 1 and "401" in rep["summary"]["stopped_because"]
    assert "wrong" not in json.dumps(rep)


def test_refuses_remote_host_without_approval(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BURST", "https://burst.invalid")
    monkeypatch.setenv("READER", "https://reader.invalid")
    monkeypatch.setenv("RRM_DEMO_TOKEN", "x")
    assert eb.main(["--question", "q", "--out", str(tmp_path / "r.json")]) == 3
    assert not (tmp_path / "r.json").exists()


def test_dry_run_and_missing_env(monkeypatch, capsys):
    for k in ("BURST", "READER", "RRM_DEMO_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert eb.main(["--question", "q", "--dry-run"]) == 0
    assert eb.main(["--question", "q"]) == 2
    assert eb.main(["--dry-run"]) == 2


def test_request_cap_and_ocr_cap(server, tmp_path):
    rc, rep = run(tmp_path, "--max-requests", "3")
    assert "request cap" in rep["summary"]["stopped_because"]
    out = tmp_path / "r2.json"
    eb.main(["--question", "attention", "--question", "scaling", "--poll-interval", "0.01", "--ocr-cap", "1", "--out", str(out)])
    rep = json.loads(out.read_text())
    assert rep["summary"]["questions_run"] == 1 and "OCR cap" in rep["summary"]["stopped_because"]


def test_check_bundle_reports_what_is_missing():
    assert eb.check_bundle("failed", {}, None) == ["failed without reason"]
    assert eb.check_bundle("failed", {}, "empty parse") == []
    p = {"kind": "p", "inlines": [{"t": "text", "v": "x"}]}
    assert "paragraph without sents" in eb.check_bundle("abstract_only", {"blocks": [dict(p, abs=True), p]})
    t = {"kind": "table", "head": [[1, 2]], "body": [[1, 2]], "hspan": [[1, 1, 1]], "bspan": [[1, 1]]}
    bad = eb.check_bundle("done", {"arxivId": "1", "blocks": [{"kind": "p", "abs": True, "sents": [[]]}, t]})
    assert bad == ["table span shape differs from rows"]
    assert "no arxivId" in eb.check_bundle("done", {"blocks": [{"kind": "p", "abs": True, "sents": [[]]}]})


def test_gate_matches_the_ui_rule():
    s1 = "Attention relates positions of a sequence to each other directly."
    doc = {"blocks": [{"kind": "p", "abs": True, "inlines": [{"t": "text", "v": s1}]}, {"kind": "p", "inlines": [{"t": "text", "v": s1 + " Again."}]}, {"kind": "p", "inlines": [{"t": "text", "v": "Unique sentence of the body of the paper."}]}]}
    ok, rej = eb.gate({"1": doc, "2": None}, [
        {"paper": "1", "quote": s1}, {"paper": "1", "quote": "Unique sentence of the body of the paper."},
        {"paper": "1", "quote": "invented"}, {"paper": "2", "quote": "x"}, {"paper": "9", "quote": "x"}])
    assert ok == 2 and rej == ["not found", "paper not read", "paper not read"]
    ok2, rej2 = eb.gate({"1": {"blocks": doc["blocks"][1:2] * 2}}, [{"paper": "1", "quote": "Again."}])
    assert (ok2, rej2) == (0, ["2 times"])
