"""scripts/live.sh sin Modal ni Meta: modal, curl y el resto son dobles en PATH."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from rrm.reader.sam import sam_enabled

ROOT = Path(__file__).parents[1]
TOKEN = "super-secret-token-xyz"
BURST = "https://example--rrm-burst-burstsearch-api.modal.run"
READER = "https://example--rrm-reader-api.modal.run"


def test_sam_enabled_default_on(monkeypatch):
    monkeypatch.delenv("RRM_SAM", raising=False)
    assert sam_enabled() is True
    for off in ("off", "0", "false", "no", " OFF "):
        monkeypatch.setenv("RRM_SAM", off)
        assert sam_enabled() is False
    monkeypatch.setenv("RRM_SAM", "on")
    assert sam_enabled() is True


def _exe(path: Path, body: str):
    path.write_text(body)
    path.chmod(0o755)


def _fakes(tmp_path: Path, *, hold_deploy=False, fail_reader=False, sleep_immediate=False):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "commands.log"
    hold = "1" if hold_deploy else "0"
    fail = "1" if fail_reader else "0"
    sleep_body = "#!/bin/bash\necho \"sleep $*\" >> \"$RRM_FAKE_LOG\"\nexit 0\n" if sleep_immediate else (
        "#!/bin/bash\necho \"sleep $*\" >> \"$RRM_FAKE_LOG\"\nexec /bin/sleep \"$@\"\n"
    )
    _exe(bindir / "sleep", sleep_body)
    _exe(bindir / "modal", f"""#!/bin/bash
echo "modal $*" >> "$RRM_FAKE_LOG"
echo "PANORAMA=${{RRM_PANORAMA_MODE-}} SAM=${{RRM_SAM-}}" >> "$RRM_FAKE_LOG"
echo "FEATURES=${{RRM_FEATURES-}}" >> "$RRM_FAKE_LOG"
if [[ "$1" == "deploy" ]]; then
  if [[ "$2" == *reader* && "{fail}" == "1" ]]; then
    echo "boom {TOKEN}" >&2
    exit 1
  fi
  if [[ "$2" == *reader* ]]; then
    printf '%b\n' '{READER}\\033\\033[2;4m{READER}'
  else
    printf '%b\n' '{BURST}\\033\\033[2;4m{BURST}'
  fi
  if [[ "{hold}" == "1" ]]; then
    /bin/sleep 30
  fi
  exit 0
fi
if [[ "$1" == "app" && "$2" == "list" ]]; then
  echo "APP LIST"
fi
exit 0
""")
    _exe(bindir / "curl", """#!/bin/bash
echo "curl $*" >> "$RRM_FAKE_LOG"
exit 0
""")
    _exe(bindir / "npm", """#!/bin/bash
echo "npm $*" >> "$RRM_FAKE_LOG"
if [[ "$1" == "ci" ]]; then
  exit 0
fi
echo "token_len=${#NEXT_PUBLIC_RRM_DEMO_TOKEN}" >> "$RRM_FAKE_LOG"
echo "burst=${NEXT_PUBLIC_BURST_URL-}" >> "$RRM_FAKE_LOG"
echo "reader=${NEXT_PUBLIC_READER_URL-}" >> "$RRM_FAKE_LOG"
echo "offline=${NEXT_PUBLIC_RRM_OFFLINE-}" >> "$RRM_FAKE_LOG"
echo "features=${NEXT_PUBLIC_RRM_FEATURES-}" >> "$RRM_FAKE_LOG"
while true; do /bin/sleep 0.2; done
""")
    _exe(bindir / "node", "#!/bin/bash\nexit 0\n")
    _exe(bindir / "python3", """#!/bin/bash
echo "python3 $*" >> "$RRM_FAKE_LOG"
if [[ "$1" == "-c" ]]; then
  exit 0
fi
if [[ "$1" == *build_ui_fixtures.py ]]; then
  mkdir -p "$3" && echo '{"queries":[]}' > "$3/manifest.json"
  exit 0
fi
if [[ "$1" == *fetch_offline_fixtures.py ]]; then
  exec /usr/bin/python3 "$@"
fi
echo "OFFLINE_PAN=${RRM_OFFLINE_PANORAMA-}" >> "$RRM_FAKE_LOG"
echo "PAN_MODE=${RRM_PANORAMA_MODE-}" >> "$RRM_FAKE_LOG"
echo "FEATURES=${RRM_FEATURES-}" >> "$RRM_FAKE_LOG"
while true; do /bin/sleep 0.2; done
""")
    _exe(bindir / "gh", """#!/bin/bash
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
  if [[ -z "${RRM_FAKE_COMPASS:-}" ]]; then
    echo "no hay copia local de compass" >&2
    exit 1
  fi
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
        sys.stderr.write("no está " + rel + "\\n")
        sys.exit(1)
    sys.stdout.buffer.write(target.read_bytes())
    sys.exit(0)
if not target.exists():
    sys.stderr.write("no está " + rel + "\\n")
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
exit 1
""")
    return bindir, log


def _env(bindir: Path, log: Path, **extra):
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "RRM_FAKE_LOG": str(log),
        "RRM_MAX_MINUTES": "30",
    }
    env.update(extra)
    return env


def _run(env, timeout=8):
    proc = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "live.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout


def _start(env):
    return subprocess.Popen(
        ["/bin/bash", str(ROOT / "scripts" / "live.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _wait_log(log: Path, needle: str, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log.is_file() and needle in log.read_text(encoding="utf-8"):
            return
        time.sleep(0.05)
    raise AssertionError(f"no apareció {needle!r} en {log}")


def _stop(proc, sig, timeout=5):
    os.killpg(proc.pid, sig)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate(timeout=timeout)
        raise AssertionError("el script no terminó tras la señal")
    return proc.returncode, out


def _stops(text: str):
    assert "modal app stop --yes rrm-burst" in text
    assert "modal app stop --yes rrm-reader" in text
    assert "modal app list" in text


def _off_sin_datos(tmp_path, **extra):
    bindir, log = _fakes(tmp_path)
    extra.setdefault("RRM_OFFLINE_SYNTH", "1")
    env = _env(bindir, log, RRM_DEMO_TOKEN=TOKEN, RRM_OFFLINE_SYNTH_DIR=str(tmp_path / "synth"), **extra)
    proc = _start(env)
    try:
        _wait_log(log, "npm run dev")
        code, out = _stop(proc, signal.SIGTERM)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    return code, out, log.read_text(encoding="utf-8")


def test_off_reusa_offline_y_no_toca_modal(tmp_path):
    code, out, text = _off_sin_datos(tmp_path, RRM_LIVE="off")
    assert "gh " not in text
    assert "build_ui_fixtures.py --out" in text
    assert f"python3 -m rrm.offline --root {tmp_path / 'synth'}" in text
    assert "sintéticos" in out
    assert "modal " not in text
    assert "curl " not in text
    assert TOKEN not in out
    assert TOKEN not in text


def test_default_es_off(tmp_path):
    code, out, text = _off_sin_datos(tmp_path)
    assert "gh " not in text and "modal " not in text and "build_ui_fixtures.py" in text
    assert TOKEN not in out


def test_modo_desconocido(tmp_path):
    bindir, log = _fakes(tmp_path)
    code, out = _run(_env(bindir, log, RRM_LIVE="sideways"))
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert code == 2
    assert "modal " not in text
    assert "off, on, modal, meta o full" in out


def test_modal_despliega_sim_sin_sam_y_ctrl_c_para(tmp_path):
    bindir, log = _fakes(tmp_path, hold_deploy=True)
    proc = _start(_env(bindir, log, RRM_LIVE="modal", RRM_DEMO_TOKEN=TOKEN))
    try:
        _wait_log(log, "modal deploy rrm/search/serve.py")
        code, out = _stop(proc, signal.SIGINT)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    text = log.read_text(encoding="utf-8")
    assert "modal deploy rrm/reader/serve.py" not in text or "modal app stop rrm-burst" in text
    _stops(text)
    assert "PANORAMA=sim SAM=off" in text
    assert "FEATURES=core" in text
    assert "curl " not in text
    assert TOKEN not in out
    assert TOKEN not in text
    assert code != 0 or "Modo: modal" in out


def test_modal_llega_a_la_ui_con_urls_y_sin_imprimir_el_token(tmp_path):
    bindir, log = _fakes(tmp_path)
    proc = _start(_env(bindir, log, RRM_LIVE="modal", RRM_DEMO_TOKEN=TOKEN))
    try:
        _wait_log(log, "token_len=")
        code, out = _stop(proc, signal.SIGINT)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    text = log.read_text(encoding="utf-8")
    assert "modal deploy rrm/search/serve.py" in text
    assert "modal deploy rrm/reader/serve.py" in text
    assert "npm ci" in text and "npm run dev" in text
    assert f"token_len={len(TOKEN)}" in text
    assert f"burst={BURST}" in text
    assert f"reader={READER}" in text
    assert "offline=" in text
    assert "offline=1" not in text
    assert "features=core" in text
    _stops(text)
    assert BURST in out and READER in out
    assert TOKEN not in out and TOKEN not in text
    assert "Modo: modal" in out
    assert code is not None


def test_fallo_de_deploy_igual_para_las_apps(tmp_path):
    bindir, log = _fakes(tmp_path, fail_reader=True)
    code, out = _run(_env(bindir, log, RRM_LIVE="full", RRM_DEMO_TOKEN=TOKEN))
    text = log.read_text(encoding="utf-8")
    assert code != 0
    assert "modal deploy rrm/search/serve.py" in text
    assert "modal deploy rrm/reader/serve.py" in text
    assert "PANORAMA=sim SAM=off" in text
    assert "FEATURES=core" in text
    assert "npm run dev" not in text
    _stops(text)
    assert "[redacted]" in out
    assert TOKEN not in out
    assert TOKEN not in text


def test_sin_token_no_despliega_y_el_trap_corre(tmp_path):
    bindir, log = _fakes(tmp_path)
    code, out = _run(_env(bindir, log, RRM_LIVE="modal"))
    text = log.read_text(encoding="utf-8")
    assert code == 1
    assert "Falta RRM_DEMO_TOKEN" in out
    assert "modal deploy" not in text
    _stops(text)


def test_meta_no_despliega_y_panorama_queda_en_vivo(tmp_path):
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "manifest.json").write_text('{"queries":[]}', encoding="utf-8")
    bindir, log = _fakes(tmp_path)
    proc = _start(_env(
        bindir, log,
        RRM_LIVE="meta",
        RRM_DEMO_TOKEN=TOKEN,
        RRM_OFFLINE_DIR=str(fx),
    ))
    try:
        _wait_log(log, "npm run dev")
        code, out = _stop(proc, signal.SIGINT)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    text = log.read_text(encoding="utf-8")
    assert "modal deploy" not in text
    assert "curl " not in text
    assert "python3 -m rrm.offline" in text
    assert "OFFLINE_PAN=" in text
    assert "OFFLINE_PAN=meta" not in text
    assert "PAN_MODE=sim" in text
    assert "FEATURES=core" in text
    assert "features=core" in text
    assert "burst=http://127.0.0.1:8787" in text
    assert "reader=http://127.0.0.1:8787" in text
    assert "offline=1" in text
    assert "token_len=5" in text
    _stops(text)
    assert TOKEN not in out and TOKEN not in text
    assert "Modo: meta" in out
    assert code is not None


def test_full_pasa_meta_y_sam(tmp_path):
    bindir, log = _fakes(tmp_path)
    proc = _start(_env(bindir, log, RRM_LIVE="full", RRM_DEMO_TOKEN=TOKEN))
    try:
        _wait_log(log, "token_len=")
        _stop(proc, signal.SIGTERM)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    text = log.read_text(encoding="utf-8")
    assert "PANORAMA=sim SAM=off" in text
    assert "FEATURES=core" in text
    assert "modal deploy rrm/search/serve.py" in text
    assert "modal deploy rrm/reader/serve.py" in text
    assert f"token_len={len(TOKEN)}" in text
    _stops(text)
    assert TOKEN not in text


def test_el_tope_de_minutos_dispara_el_trap(tmp_path):
    bindir, log = _fakes(tmp_path, sleep_immediate=True)
    code, out = _run(_env(bindir, log, RRM_LIVE="modal", RRM_DEMO_TOKEN=TOKEN, RRM_MAX_MINUTES="1"), timeout=8)
    text = log.read_text(encoding="utf-8")
    _stops(text)
    assert "Corte: RRM_MAX_MINUTES=1." in out
    assert TOKEN not in out and TOKEN not in text
    assert code != 0


def _sin_fixtures_locales():
    fx = ROOT / "offline-fixtures"
    if fx.exists():
        shutil.rmtree(fx)
    return fx


def test_off_sin_gh_auth_se_detiene(tmp_path):
    _sin_fixtures_locales()
    bindir, log = _fakes(tmp_path)
    code, out = _run(_env(bindir, log, RRM_LIVE="off", RRM_OFFLINE_SYNTH_DIR=str(tmp_path / "synth")))
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert code != 0
    assert "gh no está autenticado" in out
    assert "gh auth login" in out
    assert "gh auth status" in text
    assert "build_ui_fixtures.py" not in text
    assert "modal " not in text


def test_off_baja_v3_de_compass(tmp_path):
    from test_fetch_offline import write_compass

    fx = _sin_fixtures_locales()
    cache = ROOT / "offline-fixtures.cache"
    if cache.exists():
        shutil.rmtree(cache)
    compass = tmp_path / "compass"
    write_compass(compass)
    bindir, log = _fakes(tmp_path)
    env = _env(
        bindir, log,
        RRM_LIVE="off",
        RRM_DEMO_TOKEN=TOKEN,
        RRM_FAKE_GH_AUTH="1",
        RRM_OFFLINE_VERSION="v3",
        RRM_FAKE_COMPASS=str(compass),
        RRM_OFFLINE_SYNTH_DIR=str(tmp_path / "synth"),
    )
    proc = _start(env)
    try:
        _wait_log(log, "npm run dev")
        code, out = _stop(proc, signal.SIGTERM)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        shutil.rmtree(fx, ignore_errors=True)
        shutil.rmtree(cache, ignore_errors=True)
    text = log.read_text(encoding="utf-8")
    assert "contents/datos/offline" in text
    assert "ref=claude%2Frrm-50-plan-b1" in text
    assert "release download" not in text
    assert "build_ui_fixtures.py" not in text
    assert "modal " not in text
    assert "sintéticos" not in out
    assert code is not None


def test_la_version_por_defecto_es_v2():
    script = f"""
set -euo pipefail
source "{ROOT}/scripts/_fixtures.sh"
unset RRM_OFFLINE_VERSION
unset RRM_OFFLINE_BRANCH
printf 'branch=%s\\n' "$COMPASS_BRANCH"
offline_version
RRM_OFFLINE_VERSION=v3 offline_version
RRM_OFFLINE_VERSION=3 offline_version
RRM_OFFLINE_VERSION=offline-fixtures-v2 offline_version
RRM_OFFLINE_BRANCH=otra/rama
source "{ROOT}/scripts/_fixtures.sh"
printf 'branch=%s\\n' "$COMPASS_BRANCH"
"""
    proc = subprocess.run(["/bin/bash", "-c", script], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == [
        "branch=claude/rrm-50-plan-b1",
        "v2",
        "v3",
        "v3",
        "v2",
        "branch=otra/rama",
    ]


def test_minutos_invalidos(tmp_path):
    bindir, log = _fakes(tmp_path)
    code, out = _run(_env(bindir, log, RRM_LIVE="meta", RRM_MAX_MINUTES="0"))
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert code == 2
    assert "RRM_MAX_MINUTES" in out
    assert "modal " not in text


def test_on_sin_llave_no_despliega(tmp_path):
    bindir, log = _fakes(tmp_path)
    code, out = _run(_env(bindir, log, RRM_LIVE="on", S2_API_KEY="s2-test-key-should-not-print"))
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert code == 1
    assert "Falta MODEL_API_KEY" in out
    assert "modal deploy" not in text
    assert "s2-test-key-should-not-print" not in out
    _stops(text)


def test_on_sin_s2_no_despliega(tmp_path):
    bindir, log = _fakes(tmp_path)
    code, out = _run(_env(bindir, log, RRM_LIVE="on", MODEL_API_KEY="mk-test-key-should-not-print"))
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert code == 1
    assert "S2_API_KEY" in out
    assert "modal deploy" not in text
    assert "mk-test-key-should-not-print" not in out
    _stops(text)


def test_on_despliega_b1_y_no_imprime_llaves(tmp_path):
    bindir, log = _fakes(tmp_path)
    proc = _start(_env(
        bindir, log,
        RRM_LIVE="on",
        MODEL_API_KEY="mk-test-key-should-not-print",
        S2_API_KEY="s2-test-key-should-not-print",
    ))
    try:
        _wait_log(log, "token_len=")
        code, out = _stop(proc, signal.SIGINT)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    text = log.read_text(encoding="utf-8")
    assert "PANORAMA=sim SAM=off" in text
    assert "FEATURES=core" in text
    assert "features=core" in text
    assert "modal deploy rrm/search/serve.py" in text
    assert "modal deploy rrm/reader/serve.py" in text
    assert "offline=1" not in text
    assert "token_len=48" in text
    assert "mk-test-key-should-not-print" not in out
    assert "mk-test-key-should-not-print" not in text
    assert "s2-test-key-should-not-print" not in out
    assert "s2-test-key-should-not-print" not in text
    _stops(text)
    assert code is not None


def test_full_con_all_sigue_la_superficie_vieja(tmp_path):
    bindir, log = _fakes(tmp_path)
    proc = _start(_env(bindir, log, RRM_LIVE="full", RRM_FEATURES="all", RRM_DEMO_TOKEN=TOKEN))
    try:
        _wait_log(log, "token_len=")
        _stop(proc, signal.SIGTERM)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
    text = log.read_text(encoding="utf-8")
    assert "PANORAMA=meta SAM=on" in text
    assert "FEATURES=all" in text
    assert TOKEN not in text


def test_run_online_es_el_modo_on(tmp_path):
    bindir, log = _fakes(tmp_path)
    env = _env(bindir, log, RRM_MODE="online", S2_API_KEY="s2-test-key-should-not-print")
    proc = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts" / "run.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=8,
        check=False,
    )
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert proc.returncode == 1
    assert "Falta MODEL_API_KEY" in proc.stdout
    assert "modal deploy" not in text
    assert "s2-test-key-should-not-print" not in proc.stdout
