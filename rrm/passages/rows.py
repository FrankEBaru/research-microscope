"""Filas `eq`, `p` y `def` desde los bloques que ya parsea el lector.

Un pasaje `eq` es la ecuación en bloque más el párrafo de inmediatamente
antes y el de inmediatamente después. Un encabezado en medio no corta la
búsqueda del párrafo. Dos ecuaciones seguidas pueden compartir párrafo.

Cada bloque `p` del cuerpo tiene su propia fila, aunque ya esté dentro de
un pasaje de ecuación. Una fila `def` es una oración con símbolo matemático
(el mismo `_math_bits` de phrases.py) que no está dentro de ese pasaje.

No se guardan párrafos bajo referencias, bibliografía o agradecimientos, ni
un apéndice cuyo contenido (fuera de encabezados) son solo tablas.

Cada fila trae `title` (del paper) y `head`: la sección más específica de
la ruta de encabezados que no sea genérica (`GENERIC_HEADINGS`). Una fila
`eq` trae además `ctx_before`, `ctx_after` y `ctx_refs`: ids de las filas
`p` que la rodean y de hasta dos párrafos que la citan (`\\ref`, `\\eqref`,
`\\autoref`, `\\cref` o "Eq. (n)" con el número impreso). Solo ids, sin
copiar texto: el texto embebido se arma en embed.py.
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


# Lista cerrada de encabezados genéricos. No van en el encabezado embebido.
# Se comparan con heading_key (sin acentos, sin número de sección).
GENERIC_HEADINGS = (
    "introduction", "related work", "related works", "background", "preliminaries",
    "preliminary", "method", "methods", "methodology", "approach", "our approach",
    "model", "models", "experiments", "experiment", "experimental setup",
    "experimental settings", "experimental results", "results", "evaluation",
    "discussion", "conclusion", "conclusions", "conclusion and future work",
    "conclusions and future work", "future work", "limitations", "appendix",
    "appendices", "supplementary material", "supplementary materials", "analysis",
    "overview", "setup",
    "introduccion", "trabajo relacionado", "trabajos relacionados", "antecedentes",
    "preliminares", "metodo", "metodos", "metodologia", "enfoque", "modelo",
    "modelos", "experimentos", "configuracion experimental", "resultados",
    "evaluacion", "discusion", "conclusion", "conclusiones", "trabajo futuro",
    "limitaciones", "apendice", "apendices", "material suplementario", "analisis",
    "panorama", "vision general",
)

_SECTION_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[A-Z](?:\.\d+)+\.?|[A-Z]\.|[IVX]+\.)\s+")


def excluded_headings():
    return list(EXCLUDED_HEADINGS)


def generic_headings():
    return list(GENERIC_HEADINGS)


def heading_generic(text):
    key = heading_key(_SECTION_NUMBER.sub("", text or ""))
    return not key or key in GENERIC_HEADINGS


def specific_heading(path):
    """La sección más específica que no es genérica. "" si todas lo son."""
    for title in reversed(list(path or [])):
        if not heading_generic(title):
            return _SECTION_NUMBER.sub("", title).strip()
    return ""


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
    paths = [()] * len(blocks)
    stack = []
    active = False
    level = 1
    section = ""
    for i, block in enumerate(blocks):
        if isinstance(block, dict) and block.get("kind") == "h":
            title = _heading_text(block)
            level_i = int(block.get("level") or 1)
            while stack and stack[-1][0] >= level_i:
                stack.pop()
            stack.append((level_i, title))
            if active and level_i <= level and not heading_excluded(title):
                active = False
            if heading_excluded(title):
                active = True
                level = level_i
            section = title
        sections[i] = section
        paths[i] = tuple(title for _lvl, title in stack)
        excluded[i] = active
    return excluded, sections, paths


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


def _base_row(corpusid, block_index, sent_index, kind, section, text, latex, arxiv_id, license_url, url,
              title="", head=""):
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
        "title": title or "",
        "head": head or "",
        "ctx_before": "",
        "ctx_after": "",
        "ctx_refs": [],
    }


MAX_REFS = 2
_EQ_WORD = re.compile(r"\b(?:Eqs?|Equations?|eqs?)\.?\s*\(?\s*(\d+)\s*\)?", re.I)


def _ref_labels(inlines):
    """Etiquetas y targets de los `ref` de un párrafo, también anidados."""
    labels, targets = set(), set()

    def walk(nodes):
        for x in nodes or []:
            if not isinstance(x, dict):
                continue
            if x.get("t") == "ref":
                for part in str(x.get("label") or "").split(","):
                    if part.strip():
                        labels.add(part.strip())
                if x.get("target"):
                    targets.add(str(x["target"]))
            if isinstance(x.get("c"), list):
                walk(x["c"])

    walk(inlines)
    return labels, targets


def _eq_keys(block):
    labs = set()
    if block.get("label"):
        labs.add(str(block["label"]).strip())
    labs.update(str(lab).strip() for lab in block.get("labels") or [] if lab)
    number = block.get("number")
    return labs, (None if number is None else str(number)), str(block.get("id") or "")


def _referencing_paragraphs(blocks, eq_index, banned, skip):
    """Hasta MAX_REFS párrafos que citan la ecuación, los más cercanos primero."""
    labs, number, bid = _eq_keys(blocks[eq_index])
    if not labs and number is None and not bid:
        return []
    found = []
    for i, block in enumerate(blocks):
        if i in banned or i in skip or not isinstance(block, dict) or block.get("kind") != "p":
            continue
        refs, targets = _ref_labels(block.get("inlines") or [])
        hit = bool(labs & refs) or (bid and bid in targets)
        if not hit and number is not None:
            hit = any(m.group(1) == number for m in _EQ_WORD.finditer(_paragraph_text(block)))
        if hit:
            found.append(i)
    found.sort(key=lambda i: (abs(i - eq_index), i))
    return found[:MAX_REFS]


def extract_rows(paper, *, arxiv_id="", license="", url="", title=""):
    """Filas en orden del documento. El texto es el del bloque, no una paráfrasis."""
    blocks = list((paper or {}).get("blocks") or [])
    corpusid = (paper or {}).get("corpusid")
    if corpusid is None:
        raise ValueError("paper sin corpusid")
    arxiv_id = arxiv_id or (paper or {}).get("arxivId") or ""
    if not url and arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    title = title or (paper or {}).get("title") or ""
    excluded, sections, paths = _section_state(blocks)
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
            row = _base_row(
                corpusid, index, None, "eq", sections[index],
                "\n".join(part for part in parts if part),
                (block.get("tex") or "").strip(),
                arxiv_id, license, url, title, specific_heading(paths[index]),
            )
            if before is not None:
                row["ctx_before"] = row_id(corpusid, before)
            if after is not None:
                row["ctx_after"] = row_id(corpusid, after)
            skip = {i for i in (before, after) if i is not None}
            row["ctx_refs"] = [
                row_id(corpusid, i) for i in _referencing_paragraphs(blocks, index, banned, skip)
            ]
            rows.append(row)
            continue
        if kind != "p":
            continue
        text = _paragraph_text(block)
        if not text:
            continue
        rows.append(_base_row(
            corpusid, index, None, "p", sections[index], text,
            _inline_latex(block.get("inlines") or []),
            arxiv_id, license, url, title, specific_heading(paths[index]),
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
                arxiv_id, license, url, title, specific_heading(paths[index]),
            ))
    return rows
