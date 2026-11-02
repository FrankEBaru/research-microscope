"""Filas `eq`, `p` y `def` desde los bloques que ya parsea el lector.

Un pasaje `eq` es la ecuación en bloque más el párrafo de inmediatamente
antes y el de inmediatamente después. Un encabezado en medio no corta la
búsqueda del párrafo. Dos ecuaciones seguidas pueden compartir párrafo.

Cada bloque `p` del cuerpo tiene su propia fila, aunque ya esté dentro de
un pasaje de ecuación. Una fila `def` es una oración con símbolo matemático
(el mismo `_math_bits` de phrases.py) que no está dentro de ese pasaje.

No se guardan párrafos bajo referencias, bibliografía o agradecimientos, ni
un apéndice cuyo contenido (fuera de encabezados) son solo tablas.
"""

import re
import unicodedata

from rrm.reader.latex import plain
from rrm.reader.phrases import _math_bits

# Lista cerrada. Va también en el manifest. No se adivina por paper.
EXCLUDED_HEADINGS = (
    "references",
    "reference",
    "references and notes",
    "bibliography",
    "bibliografia",
    "referencias",
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
    "agradecimientos",
    "agradecimiento",
)


def excluded_headings():
    return list(EXCLUDED_HEADINGS)


def heading_key(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def heading_excluded(text):
    key = heading_key(text)
    return bool(key) and key in EXCLUDED_HEADINGS


def _heading_text(block):
    return plain(block.get("inlines") or [])


def _is_appendix_heading(block):
    if not isinstance(block, dict) or block.get("kind") != "h":
        return False
    number = str(block.get("number") or "")
    if number[:1].isalpha():
        return True
    key = heading_key(_heading_text(block))
    return key == "appendix" or key.startswith("appendix ") or key.startswith("apendice")


def _table_only_appendix(blocks):
    """Índices de un apéndice donde todo lo que no es encabezado es una tabla."""
    drop = set()
    n = len(blocks)
    i = 0
    while i < n:
        block = blocks[i]
        if not _is_appendix_heading(block):
            i += 1
            continue
        level = int(block.get("level") or 1)
        j = i + 1
        while j < n:
            nxt = blocks[j]
            if isinstance(nxt, dict) and nxt.get("kind") == "h" and int(nxt.get("level") or 1) <= level:
                break
            j += 1
        kinds = [
            b.get("kind")
            for b in blocks[i + 1 : j]
            if isinstance(b, dict) and b.get("kind") != "h"
        ]
        if kinds and all(kind == "table" for kind in kinds):
            drop.update(range(i, j))
        i = j
    return drop


def _section_state(blocks):
    excluded = [False] * len(blocks)
    sections = [""] * len(blocks)
    active = False
    level = 1
    section = ""
    for i, block in enumerate(blocks):
        if isinstance(block, dict) and block.get("kind") == "h":
            title = _heading_text(block)
            level_i = int(block.get("level") or 1)
            if active and level_i <= level and not heading_excluded(title):
                active = False
            if heading_excluded(title):
                active = True
                level = level_i
            section = title
        sections[i] = section
        excluded[i] = active
    return excluded, sections


def _paragraph_text(block):
    return plain(block.get("inlines") or [])


def _inline_latex(nodes):
    return " ".join(_math_bits(nodes))


def row_id(corpusid, block_index, sent_index=None):
    base = f"{int(corpusid)}:{int(block_index)}"
    if sent_index is None:
        return base
    return f"{base}:{int(sent_index)}"


def _nearest_paragraph(blocks, start, step, banned):
    i = start + step
    n = len(blocks)
    while 0 <= i < n:
        block = blocks[i]
        if i not in banned and isinstance(block, dict) and block.get("kind") == "p":
            return i
        i += step
    return None


def _base_row(corpusid, block_index, sent_index, kind, section, text, latex, arxiv_id, license_url, url):
    return {
        "id": row_id(corpusid, block_index, sent_index),
        "corpusid": int(corpusid),
        "arxiv_id": arxiv_id or "",
        "kind": kind,
        "section": section or "",
        "text": text or "",
        "latex": latex or "",
        "license": license_url or "",
        "url": url or "",
    }


def extract_rows(paper, *, arxiv_id="", license="", url=""):
    """Filas en orden del documento. El texto es el del bloque, no una paráfrasis."""
    blocks = list((paper or {}).get("blocks") or [])
    corpusid = (paper or {}).get("corpusid")
    if corpusid is None:
        raise ValueError("paper sin corpusid")
    arxiv_id = arxiv_id or (paper or {}).get("arxivId") or ""
    if not url and arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    excluded, sections = _section_state(blocks)
    banned = {i for i, flag in enumerate(excluded) if flag} | _table_only_appendix(blocks)

    context = set()
    eq_at = {}
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("kind") != "eq" or index in banned:
            continue
        before = _nearest_paragraph(blocks, index, -1, banned)
        after = _nearest_paragraph(blocks, index, 1, banned)
        if before is not None:
            context.add(before)
        if after is not None:
            context.add(after)
        eq_at[index] = (before, after)

    rows = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or index in banned:
            continue
        kind = block.get("kind")
        if kind == "eq":
            before, after = eq_at[index]
            parts = []
            if before is not None:
                parts.append(_paragraph_text(blocks[before]))
            if after is not None:
                parts.append(_paragraph_text(blocks[after]))
            rows.append(_base_row(
                corpusid, index, None, "eq", sections[index],
                "\n".join(part for part in parts if part),
                (block.get("tex") or "").strip(),
                arxiv_id, license, url,
            ))
            continue
        if kind != "p":
            continue
        text = _paragraph_text(block)
        if not text:
            continue
        rows.append(_base_row(
            corpusid, index, None, "p", sections[index], text,
            _inline_latex(block.get("inlines") or []),
            arxiv_id, license, url,
        ))
        if index in context:
            continue
        sents = block.get("sents") or [block.get("inlines") or []]
        for sent_i, sent in enumerate(sents):
            bits = _math_bits(sent)
            if not bits:
                continue
            sent_text = plain(sent)
            if not sent_text:
                continue
            rows.append(_base_row(
                corpusid, index, sent_i, "def", sections[index], sent_text,
                " ".join(bits),
                arxiv_id, license, url,
            ))
    return rows
