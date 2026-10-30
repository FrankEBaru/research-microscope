"""Batch KaTeX check. One node process, one JSON array in and out."""

import json
import os
import re
import subprocess
from pathlib import Path

# The check script lives here: add_local_python_source ships only .py files,
# so a separate .cjs never reached the Modal container.
_JS = r'''
const katex = require("katex");
const fs = require("fs");
const items = JSON.parse(fs.readFileSync(0, "utf8") || "[]");
const out = items.map((tex) => {
  const tries = [tex, "\\begin{equation}" + tex + "\\end{equation}", "\\begin{align}" + tex + "\\end{align}"];
  for (const t of tries) {
    try { katex.renderToString(t, { throwOnError: true, displayMode: true }); return true; } catch (e) {}
  }
  return false;
});
process.stdout.write(JSON.stringify(out));
'''
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


# siunitx names that show up in Instant-NGP. Unknown units fall through as \\mathrm{name}.
_SI_UNITS = {
    "minute": "min",
    "second": "s",
    "hour": "h",
    "meter": "m",
    "metre": "m",
    "gram": "g",
    "kilogram": "kg",
}


def _si_repl(match: re.Match) -> str:
    num = match.group(1).strip()
    unit = match.group(2).strip()
    if unit.startswith("\\"):
        unit = unit[1:]
    unit = _SI_UNITS.get(unit, unit)
    return f"{num}\\,\\mathrm{{{unit}}}"


def for_katex(tex: str) -> str:
    """Render-time TeX. The stored source is unchanged.

    KaTeX has no \\\\mbox. NeRF and Instant-NGP redefine \\\\left / \\\\right as
    ``\\\\mathopen{}\\\\mathclose\\\\bgroup\\\\originalleft`` and
    ``\\\\aftergroup\\\\egroup\\\\originalright``; the expander unrolls that
    about a dozen times. \\\\nicefrac, \\\\num, and \\\\SI are the other misses
    in those two papers. ``\\\\partialm`` is ``\\\\partial`` glued to the
    one-letter macro ``\\\\nn`` (body ``m``).
    """
    tex = tex or ""
    tex = re.sub(r"\\mbox(?![A-Za-z])", r"\\text", tex)
    tex = re.sub(r"(?:\\mathopen\{\}\s*\\mathclose(?![A-Za-z])\s*\\bgroup\s*)+", "", tex)
    tex = re.sub(r"(?:\\aftergroup\s*\\egroup\s*)+", "", tex)
    tex = re.sub(r"\\originalleft(?![A-Za-z])", r"\\left", tex)
    tex = re.sub(r"\\originalright(?![A-Za-z])", r"\\right", tex)
    tex = re.sub(r"\\mathopen(?![A-Za-z])\s*", "", tex)
    tex = re.sub(r"\\mathclose(?![A-Za-z])\s*", "", tex)
    tex = re.sub(r"\\nicefrac(?![A-Za-z])", r"\\frac", tex)
    tex = re.sub(r"\\num(?![A-Za-z])\s*\{([^{}]*)\}", r"\1", tex)
    tex = re.sub(r"\\SI(?![A-Za-z])\s*\{([^{}]*)\}\s*\{([^{}]*)\}", _si_repl, tex)
    tex = re.sub(r"\\partialm(?![A-Za-z])", r"\\partial m", tex)
    tex = re.sub(r"\\mathds(?![A-Za-z])", r"\\mathbb", tex)
    return tex


def check_tex(items: list[str]) -> list[bool]:
    """katex_ok for each string. Missing node or katex leaves every entry None-sized False and raises FileNotFoundError / RuntimeError."""
    if not items:
        return []
    items = [for_katex(s) for s in items]
    env = dict(os.environ)
    env["NODE_PATH"] = _node_path()
    proc = subprocess.run(
        ["node", "-e", _JS],
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
