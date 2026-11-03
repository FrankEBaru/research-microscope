"""Contrato rrm-widget/0.1 que el prompt de código le exige al modelo.

RRM-79 implementa el iframe y el AST. Aquí están los límites y la lista
de rechazos que el verificador offline ya aplica, para que el prompt y
el renderer no se separen.
"""

import os
import re

VERSION = "rrm-widget/0.1"

LIMITS = {
    "draw": 3500,
    "title": 80,
    "explain": 360,
    "question": 160,
    "why": 140,
    "label": 24,
    "questions_min": 2,
    "questions_max": 4,
    "controls_min": 1,
    "controls_max": 4,
}

# El host inyecta estos nombres. El modelo no los declara como controles.
RESERVED_IDS = frozenset({"w", "h", "t"})

_BANNED = (
    ("fetch", re.compile(r"\bfetch\s*\(")),
    ("eval", re.compile(r"\beval\s*\(")),
    ("Function", re.compile(r"\bFunction\s*\(")),
    ("import", re.compile(r"\bimport\s*\(|\bimport\s+")),
    ("require", re.compile(r"\brequire\s*\(")),
    ("document", re.compile(r"\bdocument\b")),
    ("window", re.compile(r"\bwindow\b")),
    ("globalThis", re.compile(r"\bglobalThis\b")),
    ("localStorage", re.compile(r"\blocalStorage\b")),
    ("sessionStorage", re.compile(r"\bsessionStorage\b")),
    ("indexedDB", re.compile(r"\bindexedDB\b")),
    ("postMessage", re.compile(r"\bpostMessage\s*\(")),
    ("navigator", re.compile(r"\bnavigator\b")),
    ("location", re.compile(r"\blocation\b")),
    ("innerHTML", re.compile(r"\binnerHTML\b")),
    ("outerHTML", re.compile(r"\bouterHTML\b")),
    ("setTimeout", re.compile(r"\bsetTimeout\s*\(")),
    ("setInterval", re.compile(r"\bsetInterval\s*\(")),
    ("requestAnimationFrame", re.compile(r"\brequestAnimationFrame\s*\(")),
    ("Math.random", re.compile(r"Math\.random\s*\(")),
    ("Date", re.compile(r"\bDate\b")),
    ("performance", re.compile(r"\bperformance\b")),
    ("WebSocket", re.compile(r"\bWebSocket\b")),
    ("XMLHttpRequest", re.compile(r"\bXMLHttpRequest\b")),
    ("WebAssembly", re.compile(r"\bWebAssembly\b")),
    ("Worker", re.compile(r"\bWorker\b")),
    ("SharedArrayBuffer", re.compile(r"\bSharedArrayBuffer\b")),
    ("atob", re.compile(r"\batob\s*\(")),
    ("btoa", re.compile(r"\bbtoa\s*\(")),
    ("cookie", re.compile(r"\bcookie\b")),
    ("http", re.compile(r"https?://")),
    ("ws", re.compile(r"\bwss?://")),
    ("__proto__", re.compile(r"__proto__")),
    ("constructor", re.compile(r"\bconstructor\b")),
    ("process", re.compile(r"\bprocess\.")),
    ("child_process", re.compile(r"child_process")),
)

_NETWORK = re.compile(r"https?://|\bwss?://|\bfetch\s*\(|\beval\s*\(", re.I)


def live_on() -> bool:
    """Apagado por defecto. Cualquiera de las dos variables enciende el camino vivo."""
    for key in ("RRM_LIVE_ARTIFACTS", "NEXT_PUBLIC_RRM_LIVE_ARTIFACTS"):
        raw = os.environ.get(key, "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
    return False


def banned_in(draw: str) -> list[str]:
    text = draw or ""
    return [name for name, cre in _BANNED if cre.search(text)]


def network_in(value) -> bool:
    if isinstance(value, str):
        return bool(_NETWORK.search(value))
    if isinstance(value, dict):
        return any(network_in(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(network_in(item) for item in value)
    return False
