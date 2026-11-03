"""Baja v2 (dos partes, sha unido) y v3 desde archivos de una rama, sin Releases."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parents[1]

_GH = r"""#!/bin/bash
echo "gh $*" >> "$RRM_FAKE_LOG"
if [[ "$1" == "auth" ]]; then
  if [[ "${RRM_FAKE_GH_AUTH:-}" == "1" ]]; then
    exit 0
  fi
  echo "You are not logged into any GitHub hosts." >&2
  exit 1
fi
if [[ "${RRM_FAKE_GH_AUTH:-}" != "1" ]]; then
  echo "not logged in" >&2
  exit 1
fi
if [[ "$1" == "api" ]]; then
  raw=0
  endpoint=""
  for arg in "$@"; do
    if [[ "$arg" == *github.raw* ]]; then raw=1; fi
    endpoint="$arg"
  done
  echo "gh api endpoint=$endpoint raw=$raw" >> "$RRM_FAKE_LOG"
  /usr/bin/python3 - "$RRM_FAKE_COMPASS" "$endpoint" "$raw" << 'PY'
import json, sys
from pathlib import Path
from urllib.parse import unquote
root, endpoint, raw = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "1"
pathpart = endpoint.split("?", 1)[0]
idx = pathpart.find("contents/")
rel = unquote(pathpart[idx + 9:]) if idx >= 0 else ""
target = root / rel
if raw:
    if not target.is_file():
        sys.stderr.write("no está " + rel + "\n")
        sys.exit(1)
    sys.stdout.buffer.write(target.read_bytes())
    sys.exit(0)
if not target.exists():
    sys.stderr.write("no está " + rel + "\n")
    sys.exit(1)
if target.is_file():
    json.dump({"type": "file", "name": target.name, "path": rel, "size": target.stat().st_size, "sha": "abc"}, sys.stdout)
    sys.exit(0)
items = []
for child in sorted(target.iterdir()):
    items.append({
        "type": "dir" if child.is_dir() else "file",
        "name": child.name,
        "path": str(Path(rel) / child.name),
        "size": child.stat().st_size if child.is_file() else 0,
        "sha": "abc",
    })
json.dump(items, sys.stdout)
PY
  exit $?
fi
echo "gh no implementa $*" >&2
exit 1
"""


def _tar(query: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def add(name: str, data: bytes):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        manifest = json.dumps({"queries": [{"slug": "q1", "q": query}]}).encode()
        burst = json.dumps({
            "papers": [{"corpusid": 1, "title": "Attention", "year": 2017}],
            "edges": [],
        }).encode()
        add("offline-fixtures/manifest.json", manifest)
        add("offline-fixtures/burst/q1.json", burst)
    return buf.getvalue()


def write_compass(root: Path, *, sha_in_readme: bool = False, pack: bool = False) -> dict:
    """Árbol datos/offline: v2 en dos partes, v3 en un tar. Devuelve los sha256."""
    v2 = _tar("pregunta v2 grabada")
    v3 = _tar("pregunta v3 grabada")
    mid = max(1, len(v2) // 2)
    part_a, part_b = v2[:mid], v2[mid:]
    sha2 = hashlib.sha256(v2).hexdigest()
    sha3 = hashlib.sha256(v3).hexdigest()
    base = root / "datos" / "offline"
    v2dir = base / "v2"
    v3dir = base / "v3"
    v2dir.mkdir(parents=True)
    v3dir.mkdir()
    (v2dir / "offline-fixtures-v2.tar.gz.part-aa").write_bytes(part_a)
    (v2dir / "offline-fixtures-v2.tar.gz.part-ab").write_bytes(part_b)
    (v3dir / "offline-fixtures-v3.tar.gz").write_bytes(v3)
    readme = (
        "# Fixtures\n\n"
        "No hay Releases. v2 son dos partes; el sha256 es el del archivo unido.\n\n"
        f"## v2\n\nsha256 {sha2 if sha_in_readme else 'ver el archivo .sha256'}\n\n"
        f"## v3\n\nsha256 {sha3 if sha_in_readme else 'ver el archivo .sha256'}\n"
    )
    (base / "README.md").write_text(readme, encoding="utf-8")
    if not sha_in_readme:
        (v2dir / "offline-fixtures-v2.tar.gz.sha256").write_text(sha2 + "\n", encoding="utf-8")
        (v3dir / "offline-fixtures-v3.tar.gz.sha256").write_text(f"{sha3}  offline-fixtures-v3.tar.gz\n", encoding="utf-8")
    if pack:
        (base / "manifest.json").write_text(json.dumps({
            "v2": {
                "parts": [
                    "v2/offline-fixtures-v2.tar.gz.part-aa",
                    "v2/offline-fixtures-v2.tar.gz.part-ab",
                ],
                "sha256": sha2,
            },
            "v3": {"file": "v3/offline-fixtures-v3.tar.gz", "sha256": sha3},
        }), encoding="utf-8")
    return {"v2": sha2, "v3": sha3}


def _clean():
    for name in ("offline-fixtures", "offline-fixtures.cache"):
        path = ROOT / name
        if path.exists():
            shutil.rmtree(path)


def _env(tmp_path: Path, compass: Path, **extra):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    gh = bindir / "gh"
    gh.write_text(_GH)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:/usr/bin:/bin"
    env["RRM_FAKE_LOG"] = str(log)
    env["RRM_FAKE_GH_AUTH"] = "1"
    env["RRM_FAKE_COMPASS"] = str(compass)
    env.update(extra)
    return env, log


def _resolve(env):
    script = f"""
set -euo pipefail
source "{ROOT}/scripts/_fixtures.sh"
resolve_fixtures "{ROOT}"
python3 -c 'import json,pathlib,os; print(json.load(open(os.environ["FIX"]))["queries"][0]["q"])'
"""
    env = dict(env)
    env["FIX"] = str(ROOT / "offline-fixtures" / "manifest.json")
    return subprocess.run(
        ["/bin/bash", "-c", script],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_v2_une_partes_y_comprueba_sha(tmp_path):
    _clean()
    compass = tmp_path / "compass"
    digests = write_compass(compass)
    env, log = _env(tmp_path, compass, RRM_OFFLINE_VERSION="v2")
    try:
        proc = _resolve(env)
        assert proc.returncode == 0, proc.stdout
        assert proc.stdout.strip().splitlines()[-1] == "pregunta v2 grabada"
        stamp = (ROOT / "offline-fixtures" / ".rrm-release").read_text(encoding="utf-8")
        assert stamp.startswith("branch=claude/rrm-50-plan-b1 version=v2 sha256=")
        assert digests["v2"] in stamp
        text = log.read_text(encoding="utf-8")
        assert "part-aa" in text and "part-ab" in text
        assert "release download" not in text
        log.write_text("", encoding="utf-8")
        again = _resolve(env)
        assert again.returncode == 0, again.stdout
        assert log.read_text(encoding="utf-8") == ""
    finally:
        _clean()


def test_v3_y_cache_de_blobs(tmp_path):
    _clean()
    compass = tmp_path / "compass"
    write_compass(compass)
    env, log = _env(tmp_path, compass, RRM_OFFLINE_VERSION="v3")
    try:
        proc = _resolve(env)
        assert proc.returncode == 0, proc.stdout
        assert proc.stdout.strip().splitlines()[-1] == "pregunta v3 grabada"
        shutil.rmtree(ROOT / "offline-fixtures")
        log.write_text("", encoding="utf-8")
        again = _resolve(env)
        assert again.returncode == 0, again.stdout
        assert again.stdout.strip().splitlines()[-1] == "pregunta v3 grabada"
        raw = [line for line in log.read_text(encoding="utf-8").splitlines() if "raw=1" in line]
        assert raw
        assert all("sha256" in line or "README.md" in line for line in raw)
    finally:
        _clean()


def test_sha_mal_no_instala(tmp_path):
    _clean()
    compass = tmp_path / "compass"
    write_compass(compass)
    bad = compass / "datos" / "offline" / "v2" / "offline-fixtures-v2.tar.gz.sha256"
    bad.write_text("0" * 64 + "\n", encoding="utf-8")
    env, _log = _env(tmp_path, compass, RRM_OFFLINE_VERSION="v2")
    try:
        proc = _resolve(env)
        assert proc.returncode != 0
        assert "sha256 no coincide" in proc.stdout
        assert not (ROOT / "offline-fixtures" / "manifest.json").exists()
    finally:
        _clean()


def test_sha_en_el_readme(tmp_path):
    _clean()
    compass = tmp_path / "compass"
    write_compass(compass, sha_in_readme=True)
    env, _log = _env(tmp_path, compass, RRM_OFFLINE_VERSION="v2")
    try:
        proc = _resolve(env)
        assert proc.returncode == 0, proc.stdout
        assert "pregunta v2 grabada" in proc.stdout
    finally:
        _clean()


def test_manifest_de_paquete_y_rama(tmp_path):
    _clean()
    compass = tmp_path / "compass"
    write_compass(compass, pack=True)
    env, log = _env(
        tmp_path, compass,
        RRM_OFFLINE_VERSION="v3",
        RRM_OFFLINE_BRANCH="otra/rama",
    )
    try:
        proc = _resolve(env)
        assert proc.returncode == 0, proc.stdout
        assert "pregunta v3 grabada" in proc.stdout
        text = log.read_text(encoding="utf-8")
        assert "ref=otra%2Frama" in text
        stamp = (ROOT / "offline-fixtures" / ".rrm-release").read_text(encoding="utf-8")
        assert stamp.startswith("branch=otra/rama version=v3 ")
    finally:
        _clean()


def _offline_server(env):
    proc = subprocess.Popen(
        ["/bin/bash", str(ROOT / "scripts" / "offline.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 20
    seen = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            rest = proc.stdout.read() if proc.stdout else ""
            raise AssertionError(f"offline.sh salió {proc.returncode}: {seen}{rest}")
        line = proc.stdout.readline() if proc.stdout else ""
        seen += line
        if "API local:" in line or "offline en http" in seen:
            return proc, seen
    os.killpg(proc.pid, 9)
    proc.wait(timeout=5)
    raise AssertionError(f"no arrancó: {seen}")


def _stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, 15)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, 9)
            proc.wait(timeout=5)


def _get(path: str) -> dict:
    with urllib.request.urlopen("http://127.0.0.1:8787" + path, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_offline_sh_v2_y_v3_de_punta_a_punta(tmp_path):
    if not shutil.which("node") or not shutil.which("npm"):
        import pytest
        pytest.skip("hace falta node y npm")
    _clean()
    compass = tmp_path / "compass"
    write_compass(compass)
    env, _log = _env(tmp_path, compass, RRM_OFFLINE_NO_UI="1", RRM_OFFLINE_VERSION="v2")
    node_dir = str(Path(shutil.which("node")).parent)
    npm_dir = str(Path(shutil.which("npm")).parent)
    env["PATH"] = f"{tmp_path / 'bin'}:{node_dir}:{npm_dir}:/usr/bin:/bin"
    proc = None
    try:
        proc, _seen = _offline_server(env)
        body = _get("/")
        assert body["queries"] == ["pregunta v2 grabada"]
        burst = _get("/burst?q=pregunta%20v2%20grabada")
        assert burst["papers"][0]["corpusid"] == 1
        _stop(proc)
        proc = None
        env["RRM_OFFLINE_VERSION"] = "v3"
        proc, _seen = _offline_server(env)
        body = _get("/")
        assert body["queries"] == ["pregunta v3 grabada"]
        burst = _get("/burst?q=pregunta%20v3%20grabada")
        assert burst["papers"][0]["title"] == "Attention"
    finally:
        if proc is not None:
            _stop(proc)
        _clean()
