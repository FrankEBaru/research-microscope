"""Servidor local de las consultas grabadas. Misma API, sin Modal.

Lee un directorio (el Release ``offline-fixtures-v1``) y responde
``/burst``, ``/status``, ``/paper``, ``/file``, ``/crops``, ``/subtopics``
y ``POST /panorama``. Si la consulta no está en la grabación, responde
``consulta no grabada``. La autenticación es opcional: no hace falta token.

Por defecto ``/panorama`` y ``/crops`` reproducen el JSON grabado y no llaman
a Meta. ``RRM_OFFLINE_PANORAMA=meta`` hace que ``POST /panorama`` llame a Muse
(``rrm.panorama.meta_panorama``) con los papers grabados. ``/crops`` sigue
grabado: no hay PDF local para SAM.
"""

import argparse
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rrm.features import core_mode, features_mode
from rrm.search.layout import place_papers

MISS = "consulta no grabada"
_NAME = re.compile(r"^[A-Za-z0-9._-]{1,180}$")
_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
}


def safe_name(name: str) -> bool:
    return isinstance(name, str) and bool(_NAME.fullmatch(name)) and ".." not in name and Path(name).suffix.lower() in _TYPES


def _load(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class Store:
    def __init__(self, root):
        self.root = Path(root)
        manifest = _load(self.root / "manifest.json")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("queries"), list):
            raise SystemExit(f"falta manifest.json en {self.root}")
        self.queries = {}
        for row in manifest["queries"]:
            slug = str(row["slug"])
            question = str(row["q"]).strip()
            self.queries[question] = {
                "slug": slug,
                "burst": _load(self.root / "burst" / f"{slug}.json"),
                "subtopics": _load(self.root / "subtopics" / f"{slug}.json"),
                "panorama": _load(self.root / "panorama" / f"{slug}.json"),
            }
        self.status = {}
        status_dir = self.root / "status"
        if status_dir.is_dir():
            for path in sorted(status_dir.glob("*.json")):
                body = _load(path) or {}
                for row in body.get("papers") or []:
                    if isinstance(row, dict) and str(row.get("id", "")).lstrip("-").isdigit():
                        self.status[str(int(row["id"]))] = row
        self.papers = {}
        papers = self.root / "papers"
        if papers.is_dir():
            for path in papers.glob("*.json"):
                if path.stem.isdigit():
                    self.papers[str(int(path.stem))] = _load(path)
        self.crops = {}
        crops = self.root / "crops"
        if crops.is_dir():
            for path in crops.glob("*.json"):
                if path.stem.isdigit():
                    self.crops[str(int(path.stem))] = _load(path)
        self.files = {}
        files = self.root / "files"
        if files.is_dir():
            for path in files.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(files)
                if len(rel.parts) != 2:
                    continue
                cid, name = rel.parts
                if cid.isdigit() and safe_name(name):
                    self.files[(str(int(cid)), name)] = path.resolve()

    def question(self, raw: str):
        return self.queries.get((raw or "").strip())


def _miss():
    return 404, {"error": MISS}


def panorama_is_live() -> bool:
    """Muse only in `all`. Core replays the recording and does not call Meta."""
    if core_mode():
        return False
    return (os.environ.get("RRM_OFFLINE_PANORAMA") or "").strip().lower() == "meta"


def _paper_doc(raw):
    """The bundle ``meta_panorama`` reads. The fixture stores the ``/paper`` response."""
    if not isinstance(raw, dict):
        return None
    status = raw.get("status")
    if status is None and isinstance(raw.get("meta"), dict):
        status = raw["meta"].get("status")
    if status not in (None, "done", "abstract_only"):
        return None
    inner = raw.get("paper")
    if isinstance(inner, dict):
        return inner
    if isinstance(raw.get("blocks"), list):
        return raw
    return None


def live_panorama(store: Store, item):
    """Muse over the recorded papers. Raises ValueError on a bad body."""
    from rrm.panorama import meta_panorama, parse_request

    question, ids = parse_request(item)
    docs = {pid: _paper_doc(store.papers.get(pid)) for pid in ids}
    return meta_panorama(question, docs)


def build_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        # No loguear la query: puede traer ?k=
        def log_message(self, fmt, *args):
            return

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-RRM-Demo, Content-Type")

        def _send(self, code: int, body, content_type: str, cache: str = "no-store"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self._cors()
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, code: int, body):
            self._send(code, body, "application/json; charset=utf-8")

        def do_OPTIONS(self):
            self._send(204, b"", "text/plain; charset=utf-8")

        def do_GET(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path.rstrip("/") or "/"
            one = lambda key: (qs.get(key) or [""])[0]

            def cid_of():
                raw = one("id").strip()
                if not raw.isdigit():
                    return ""
                return str(int(raw))
            if path == "/":
                self._json(200, {"ok": True, "queries": sorted(store.queries)})
                return
            if path == "/warm":
                self._json(200, {"ready": True, "features": features_mode(), "loaded": ["fixtures"]})
                return
            if path == "/burst":
                hit = store.question(one("q"))
                body = None if hit is None else hit.get("burst")
                if body is None:
                    self._json(*_miss())
                    return
                try:
                    n = int(one("n") or "10")
                except ValueError:
                    n = 10
                n = max(0, min(100, n))
                out = dict(body)
                if isinstance(out.get("papers"), list):
                    out["papers"] = out["papers"][:n]
                # Fixtures have citations and years, not SPECTER2 vectors.
                # A stored specter layout (if a future recording has one) is kept.
                stored = out.get("layout") if isinstance(out.get("layout"), dict) else None
                if not stored or stored.get("method") != "specter2-pca":
                    out["layout"] = place_papers(out.get("papers") or [], out.get("edges") or [])
                self._json(200, out)
                return
            if path == "/subtopics":
                hit = store.question(one("q"))
                body = None if hit is None else hit.get("subtopics")
                if body is None:
                    self._json(*_miss())
                    return
                self._json(200, body)
                return
            if path == "/status":
                ids = []
                for part in one("ids").split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if not part.isdigit():
                        self._json(*_miss())
                        return
                    ids.append(str(int(part)))
                if not ids:
                    self._json(*_miss())
                    return
                known = [part for part in ids if part in store.status]
                if not known:
                    self._json(*_miss())
                    return
                rows = []
                for part in ids:
                    if part in store.status:
                        rows.append(store.status[part])
                    else:
                        rows.append({"id": int(part), "status": "missing", "reason": MISS})
                self._json(200, {"papers": rows})
                return
            if path == "/paper":
                cid = cid_of()
                if not cid or cid not in store.papers:
                    self._json(*_miss())
                    return
                self._json(200, store.papers[cid])
                return
            if path == "/crops":
                cid = cid_of()
                if not cid or cid not in store.crops:
                    self._json(*_miss())
                    return
                body = dict(store.crops[cid])
                raw_pages = one("pages")
                if raw_pages:
                    wanted = []
                    for part in raw_pages.split(","):
                        part = part.strip()
                        if part.isdigit():
                            wanted.append(int(part))
                    recorded = {int(p) for p in (body.get("pages") or []) if str(p).lstrip("-").isdigit()}
                    if recorded and wanted and not (set(wanted) & recorded):
                        self._json(*_miss())
                        return
                    rows = body.get("crops") or []
                    body["pages"] = wanted
                    body["crops"] = [row for row in rows if row.get("page") in set(wanted)]
                self._json(200, body)
                return
            if path == "/file":
                cid = cid_of()
                name = one("name")
                path_file = store.files.get((cid, name)) if cid and safe_name(name) else None
                if path_file is None or not path_file.is_file():
                    self._json(*_miss())
                    return
                data = path_file.read_bytes()
                self._send(200, data, _TYPES[path_file.suffix.lower()], cache="public, max-age=86400")
                return
            self._json(*_miss())

        def do_POST(self):
            url = urlparse(self.path)
            path = url.path.rstrip("/") or "/"
            if path == "/prepare":
                length = int(self.headers.get("Content-Length") or "0")
                if length < 0 or length > 2_000_000:
                    self._json(400, {"error": "body"})
                    return
                raw = self.rfile.read(length) if length else b""
                try:
                    item = json.loads(raw.decode("utf-8") or "null")
                except (UnicodeError, json.JSONDecodeError):
                    self._json(400, {"error": "body must be a JSON object"})
                    return
                ids = item.get("ids") if isinstance(item, dict) else None
                rows = []
                for raw_id in ids or []:
                    try:
                        cid = str(int(raw_id))
                    except (TypeError, ValueError):
                        continue
                    known = store.status.get(cid) or {"id": int(cid), "status": "missing"}
                    rows.append(dict(known))
                self._json(200, {"papers": rows, "front": bool(isinstance(item, dict) and item.get("front"))})
                return
            if path != "/panorama":
                self._json(*_miss())
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length < 0 or length > 2_000_000:
                self._json(400, {"error": "body"})
                return
            raw = self.rfile.read(length) if length else b""
            try:
                item = json.loads(raw.decode("utf-8") or "null")
            except (UnicodeError, json.JSONDecodeError):
                self._json(400, {"error": "body must be a JSON object"})
                return
            if panorama_is_live():
                try:
                    self._json(200, live_panorama(store, item))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            question = item.get("question") if isinstance(item, dict) else None
            if not isinstance(question, str) or not question.strip():
                self._json(400, {"error": "question must be a non-empty string"})
                return
            hit = store.question(question)
            body = None if hit is None else hit.get("panorama")
            if body is None:
                self._json(*_miss())
                return
            self._json(200, body)

    return Handler


def make_server(root, host="127.0.0.1", port=8787):
    store = Store(root)
    httpd = ThreadingHTTPServer((host, int(port)), build_handler(store))
    return httpd


def main(argv=None):
    parser = argparse.ArgumentParser(description="API local con las consultas grabadas. Sin Modal. Meta solo si RRM_OFFLINE_PANORAMA=meta.")
    parser.add_argument("--root", default="offline-fixtures")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    httpd = make_server(args.root, args.host, args.port)
    bound = httpd.server_address
    print(f"offline en http://{bound[0]}:{bound[1]}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
