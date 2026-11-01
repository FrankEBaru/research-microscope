"""Frases del autor para la caja. Parseo local: sin FAISS y sin modelo."""

import json
import re
from pathlib import Path

_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
_CHUNK = re.compile(r"\$([^$]+)\$")
_SYMBOL = re.compile(r"\\[A-Za-z]+|[A-Za-z](?:_[A-Za-z0-9]+)+")


def _math_bits(nodes):
    bits = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        if node.get("t") == "math" and node.get("v"):
            bits.append(str(node["v"]))
        if isinstance(node.get("c"), list):
            bits.extend(_math_bits(node["c"]))
    return bits


def collect_phrases(paper):
    """Oraciones con un símbolo, o la última justo antes de una ecuación."""
    from rrm.reader.latex import plain

    section = ""
    blocks = paper.get("blocks") or []
    rows = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        if block.get("kind") == "h":
            section = plain(block.get("inlines") or []) or section
            continue
        if block.get("kind") != "p":
            continue
        sents = block.get("sents") or [block.get("inlines") or []]
        nxt = blocks[index + 1] if index + 1 < len(blocks) else None
        eq = nxt.get("tex") if isinstance(nxt, dict) and nxt.get("kind") == "eq" else ""
        for sent_i, sent in enumerate(sents):
            bits = _math_bits(sent)
            if eq and sent_i == len(sents) - 1:
                bits = bits + [eq]
            text = plain(sent)
            if text and bits:
                rows.append({
                    "paper": paper.get("corpusid"),
                    "section": section,
                    "text": text,
                    "latex": bits,
                })
    return rows


def write_phrases(folder, paper):
    rows = collect_phrases(paper)
    path = Path(folder) / "phrases.json"
    body = {"paper": paper.get("corpusid"), "rows": rows}
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return rows


def read_phrases(folder):
    path = Path(folder) / "phrases.json"
    if not path.is_file():
        return []
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = body.get("rows") if isinstance(body, dict) else None
    return list(rows or [])


def load_rows(root, ids):
    rows = []
    base = Path(root)
    for raw in ids or []:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        folder = base / str(cid)
        got = read_phrases(folder)
        if got:
            rows.extend(got)
            continue
        paper_path = folder / "paper.json"
        if not paper_path.is_file():
            continue
        try:
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.extend(collect_phrases(paper))
    return rows


def query_tokens(text):
    raw = text or ""
    chunks = [piece.strip() for piece in _CHUNK.findall(raw) if piece.strip()]
    bare = _CHUNK.sub(" ", raw)
    words = [word.casefold() for word in _WORD.findall(bare)]
    chunks.extend(piece for piece in _SYMBOL.findall(bare) if piece not in chunks)
    return words, chunks


def _chunk_in(chunk, row):
    needle = re.sub(r"\s+", "", chunk)
    blob = re.sub(r"\s+", "", (row.get("text") or "") + "".join(row.get("latex") or []))
    return bool(needle) and needle.casefold() in blob.casefold()


def search_phrases(rows, text):
    """Cada palabra y cada trozo LaTeX tienen que estar en la frase."""
    words, chunks = query_tokens(text)
    if not words and not chunks:
        return []
    hits = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        flat = (row.get("text") or "").casefold()
        if words and not all(word in flat for word in words):
            continue
        if chunks and not all(_chunk_in(chunk, row) for chunk in chunks):
            continue
        hits.append(row)
    return hits
