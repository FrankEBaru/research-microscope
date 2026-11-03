"""Consulta corta de un símbolo. No abre la base si el flag está apagado."""

import json
import os
import re
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "passages_demo.json"
# Mismo tope que rights.clip_text: la cita de un paper cerrado no pasa de aquí.
_QUOTE_LIMIT = 300


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


def _sentences(text):
    flat = " ".join(str(text or "").split())
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", flat) if part.strip()]
    return parts


def short_quote(text, symbol="", limit=_QUOTE_LIMIT):
    """A lo más dos oraciones, y nunca más largo que el tope de cita."""
    from rrm.reader.rights import clip_text

    parts = _sentences(text)
    if not parts:
        return ""
    needle = _needle(symbol)
    start = 0
    if needle:
        for index, part in enumerate(parts):
            if needle in _needle(part):
                start = index
                break
    chunk = " ".join(parts[start:start + 2])
    quoted = clip_text(chunk, limit)
    if needle and needle not in _needle(quoted) and needle in _needle(chunk) and symbol and symbol in chunk:
        at = chunk.find(symbol)
        quoted = clip_text(chunk[max(0, at - limit // 2):], limit)
    return quoted


def _link(row):
    url = str((row or {}).get("url") or "").strip()
    if url:
        return url
    arxiv = str((row or {}).get("arxiv_id") or "").strip()
    if arxiv:
        return f"https://arxiv.org/abs/{arxiv}"
    paper = (row or {}).get("corpusid")
    if paper is None:
        paper = (row or {}).get("paper")
    if paper is None or str(paper).strip() == "":
        return ""
    return f"https://www.semanticscholar.org/paper/{paper}"


def reproduces(passage, text):
    """True si `text` trae una oración o un tramo largo del pasaje guardado."""
    source = " ".join(str(passage or "").split())
    out = " ".join(str(text or "").split())
    if not source or not out:
        return False
    if len(source) >= 24 and source in out:
        return True
    for sent in _sentences(source):
        if len(sent) >= 24 and sent in out:
            return True
    span = 48
    if len(source) >= span and len(out) >= span:
        for index in range(0, len(source) - span + 1, 16):
            if source[index:index + span] in out:
                return True
    return False


def scrub_passage(text, passage):
    """Quita del texto visible cualquier copia del pasaje. Deja a lo más dos oraciones."""
    from rrm.reader.rights import clip_text

    parts = _sentences(text)
    if not parts:
        flat = " ".join(str(text or "").split())
        parts = [flat] if flat else []
    kept = [part for part in parts if part and not reproduces(passage, part)]
    quote = clip_text(" ".join(kept[:2]), _QUOTE_LIMIT)
    if reproduces(passage, quote):
        return ""
    return quote


def _describe(row):
    """Fila completa para el modelo, con papel, tipo y si la licencia es cerrada."""
    from rrm.reader.rights import license_class

    item = adapt_row(row)
    if not isinstance(row, dict):
        return item
    if row.get("kind"):
        item["kind"] = str(row.get("kind") or "")
    link = _link(row)
    if link:
        item["url"] = link
    item["license"] = str(row.get("license") or "")
    item["from_db"] = True
    item["closed"] = license_class(item["license"]) != "open"
    return item


def _keep(item, row):
    if not isinstance(row, dict):
        return item
    if row.get("from_db"):
        item["from_db"] = True
        item["closed"] = bool(row.get("closed"))
        if row.get("license"):
            item["license"] = str(row.get("license") or "")
    if row.get("kind"):
        item["kind"] = str(row.get("kind") or "")
    if row.get("url"):
        item["url"] = str(row.get("url") or "")
    return item


def _query_vector(text):
    """Vector proximity del hueco. El newline usa el mismo adaptador que el índice e3."""
    try:
        from rrm.reader.similar import specter_encode

        raw = str(text or "").strip()
        if not raw:
            return None
        if "\n" not in raw:
            raw = raw + "\n"
        vec = specter_encode([raw])
        return vec[0]
    except Exception:
        return None


def _volume_hits(symbol, limit, query=None):
    """Top-k por embedding. Solo con el flag. El texto sale completo."""
    from rrm.reader.passage_db import passages_dir, search_embedding

    root = passages_dir()
    if not (root / "rows.parquet").is_file() or not (root / "faiss.index").is_file():
        return []
    vector = _query_vector(query or symbol)
    if vector is None:
        return []
    found = search_embedding(vector, k=max(int(limit), 1), root=root)
    return [_describe(row) for row in found]


def lookup(symbol, limit=3, rows=None, burst_ids=None, query=None, volume=True):
    """Símbolo en la base, luego en las filas del caller, luego en el fixture. Tope `limit`.

    Con el flag, la base se consulta por embedding (`query` o el símbolo) y
    devuelve el pasaje completo. `volume=False` deja solo las filas locales.
    """
    found = []
    if volume and _flag_on():
        try:
            found.extend(_volume_hits(symbol, limit, query=query))
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
        item = _keep(adapt_row(row), row)
        if item["id"] and item["id"] in seen:
            continue
        if not item["text"] and not item["latex"]:
            continue
        if item["id"]:
            seen.add(item["id"])
        ordered.append(item)
    return ordered[: max(0, int(limit))]
