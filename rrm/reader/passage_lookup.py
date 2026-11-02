"""Consulta corta de un símbolo. No importa la base si el flag está apagado."""

import importlib.util
import json
import os
import re
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "passages_demo.json"


def adapt_row(row):
    """Fila de pasajes o de phrases → {id, paper, section, text, latex}."""
    if not isinstance(row, dict):
        return {"id": "", "paper": "", "section": "", "text": "", "latex": ""}
    paper = row.get("paper")
    if paper is None and row.get("corpusid") is not None:
        paper = row.get("corpusid")
    latex = row.get("latex")
    if isinstance(latex, list):
        latex = " ".join(str(bit) for bit in latex)
    return {
        "id": str(row.get("id") or ""),
        "paper": str(paper or ""),
        "section": str(row.get("section") or ""),
        "text": str(row.get("text") or ""),
        "latex": str(latex or ""),
    }


def _needle(symbol):
    return re.sub(r"\s+", "", symbol or "")


def _hit(row, symbol):
    needle = _needle(symbol)
    if not needle:
        return False
    adapted = adapt_row(row)
    blob = re.sub(r"\s+", "", adapted["text"] + adapted["latex"])
    return needle in blob


def _fixture_rows():
    if not _FIXTURE.is_file():
        return []
    try:
        data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _flag_on():
    return os.environ.get("RRM_PASSAGES", "").strip() == "1"


def _volume_hits(symbol, limit):
    """Base real. Solo se llama con el flag prendido. Si falta, lista vacía."""
    if importlib.util.find_spec("rrm.passages") is None:
        return []
    root = Path(os.environ.get("RRM_DATA", "/data")) / "passages"
    if not root.is_dir():
        return []
    from rrm.passages.load import load_passages

    index = load_passages(root)
    got = index.query({"symbol": symbol}, k=max(int(limit), 1))
    return list(got or [])


def lookup(symbol, limit=3, rows=None, burst_ids=None):
    """Símbolo en la base, luego en las filas del caller, luego en el fixture. Tope `limit`."""
    found = []
    if _flag_on():
        try:
            found.extend(_volume_hits(symbol, limit))
        except Exception:
            pass
    caller = [row for row in (rows or []) if _hit(row, symbol)]
    found.extend(caller)
    prefer = {str(item) for item in (burst_ids or [])}
    fixture = []
    rest_fix = []
    for row in _fixture_rows():
        if not _hit(row, symbol):
            continue
        adapted = adapt_row(row)
        (fixture if adapted["paper"] in prefer else rest_fix).append(row)
    ordered = [adapt_row(row) for row in fixture]
    seen = {row["id"] for row in ordered if row["id"]}
    for row in list(found) + rest_fix:
        item = adapt_row(row)
        if item["id"] and item["id"] in seen:
            continue
        if not item["text"] and not item["latex"]:
            continue
        if item["id"]:
            seen.add(item["id"])
        ordered.append(item)
    return ordered[: max(0, int(limit))]
