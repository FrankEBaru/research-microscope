"""Sandbox for GET /file. Figures and crops, or the paper's own source.pdf."""

import os
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


def resolve_source_pdf(papers_root, corpusid, name) -> Path | None:
    """Solo papers/{id}/source.pdf. No abre el resto de la carpeta."""
    if name != "source.pdf":
        return None
    cid = str(corpusid or "")
    if not cid.isdigit():
        return None
    root = (Path(papers_root) / cid).resolve()
    path = (root / "source.pdf").resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.is_file() else None


def atomic_write(path, text: str) -> None:
    """Replace the file under a lock. A reader sees the previous bytes or the new ones."""
    import fcntl

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            fcntl.flock(lock, fcntl.LOCK_UN)
