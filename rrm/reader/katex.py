"""Batch KaTeX check. One node process, one JSON array in and out."""

import json
import os
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).with_name("katex_check.cjs")
_CANDIDATES = (
    os.environ.get("NODE_PATH", ""),
    "/opt/katex/node_modules",
    "/tmp/katex/node_modules",
)


def katex_available() -> bool:
    for path in _CANDIDATES:
        if path and (Path(path) / "katex").is_dir():
            return True
    return False


def _node_path() -> str:
    parts = [p for p in _CANDIDATES if p]
    return os.pathsep.join(parts)


def check_tex(items: list[str]) -> list[bool]:
    """katex_ok for each string. Missing node or katex leaves every entry None-sized False and raises FileNotFoundError / RuntimeError."""
    if not items:
        return []
    env = dict(os.environ)
    env["NODE_PATH"] = _node_path()
    proc = subprocess.run(
        ["node", str(_SCRIPT)],
        input=json.dumps(items).encode(),
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:400]
        raise RuntimeError(err or "katex check failed")
    out = json.loads(proc.stdout.decode())
    if len(out) != len(items):
        raise RuntimeError("katex check returned the wrong length")
    return [bool(x) for x in out]
