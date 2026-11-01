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


_CAP = 12
_PER_PAPER = 3


def _chunk_in(chunk, row):
    needle = re.sub(r"\s+", "", chunk)
    blob = (row.get("text") or "") + "".join(row.get("latex") or [])
    if not needle:
        return False
    if len(needle) <= 2 and needle.isalpha():
        return re.search(rf"(?<![A-Za-z]){re.escape(needle)}(?![A-Za-z])", blob, re.I) is not None
    flat = re.sub(r"\s+", "", blob)
    return needle.casefold() in flat.casefold()


def rank_phrases(rows, text):
    """Palabras y LaTeX en la misma frase. Símbolo + palabras van primero. Tope 3 por paper y 12."""
    words, chunks = query_tokens(text)
    if not words and not chunks:
        return [], 0
    scored = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        flat = (row.get("text") or "").casefold()
        word_hits = sum(1 for word in words if word in flat)
        if words and word_hits != len(words):
            continue
        chunk_hits = sum(1 for chunk in chunks if _chunk_in(chunk, row))
        if chunks and chunk_hits != len(chunks):
            continue
        both = 1 if words and chunks else 0
        scored.append((both, word_hits + chunk_hits, row))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    picked, per = [], {}
    for _both, _score, row in scored:
        pid = row.get("paper")
        if per.get(pid, 0) >= _PER_PAPER:
            continue
        per[pid] = per.get(pid, 0) + 1
        picked.append(row)
        if len(picked) >= _CAP:
            break
    return picked, len(scored)


def search_phrases(rows, text):
    hits, _total = rank_phrases(rows, text)
    return hits


def store_progress(root, ids):
    from pathlib import Path

    ready = total = 0
    base = Path(root) if root else None
    for raw in ids or []:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        total += 1
        if base and (base / str(cid) / "phrases.json").is_file():
            ready += 1
    return {"ready": ready, "total": total}
