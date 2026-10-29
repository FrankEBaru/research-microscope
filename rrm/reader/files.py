"""Sandbox for GET /file. Figures and crops only; nothing else on the paper folder."""

import re
from pathlib import Path

_NAME = re.compile(r"^[A-Za-z0-9._-]{1,180}$")
_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt"}


def resolve_figure(papers_root, corpusid, name) -> Path | None:
    cid = str(corpusid or "")
    if not cid.isdigit():
        return None
    if not isinstance(name, str) or not _NAME.fullmatch(name) or ".." in name:
        return None
    if Path(name).suffix.lower() not in _TYPES:
        return None
    root = Path(papers_root)
    for folder in ("figures", "crops"):
        base = (root / cid / folder).resolve()
        path = (base / name).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            continue
        if path.is_file():
            return path
    return None
