"""Oraciones de una sección con puntero estable `<bloque>#<oración>` (el formato del brief de RRM-99).

La sección es la del botón de la app (`Paper.tsx`): un encabezado de nivel ≤ 2 y
todo lo que sigue hasta otro encabezado de nivel igual o menor. Las ecuaciones
entran como unidad propia (`b26`) con su TeX.
"""

import re

_NOISE = re.compile(r"\s+")


def _plain(nodes):
    from rrm.reader.latex import plain

    return _NOISE.sub(" ", plain(nodes or [])).strip()


def _sents(block):
    raw = block.get("sents")
    if raw:
        return raw
    return [block.get("inlines") or []]


def _math(nodes):
    from rrm.reader.phrases import _math_bits

    return _math_bits(nodes)


def headings(paper):
    """[(id, level, title)] de los encabezados con botón (nivel ≤ 2)."""
    out = []
    for block in paper.get("blocks") or []:
        if isinstance(block, dict) and block.get("kind") == "h" and int(block.get("level") or 9) <= 2:
            out.append((str(block.get("id")), int(block.get("level")), _plain(block.get("inlines"))))
    return out


def _units_of(block, section):
    kind = block.get("kind")
    bid = str(block.get("id") or "")
    if kind == "eq" and block.get("tex"):
        return [{"id": bid, "section": section, "text": "$$" + str(block["tex"]).strip() + "$$", "latex": [str(block["tex"])], "kind": "eq"}]
    if kind == "list":
        out = []
        for index, item in enumerate(block.get("items") or []):
            text = _plain(item)
            if len(text) >= 3:
                out.append({"id": f"{bid}#{index}", "section": section, "text": text, "latex": _math(item), "kind": "li"})
        return out
    if kind == "h":
        text = _plain(block.get("inlines"))
        return [{"id": bid, "section": section, "text": text, "latex": [], "kind": "h"}] if len(text) >= 3 else []
    if kind != "p" or block.get("raw"):
        return []
    units = []
    for index, sent in enumerate(_sents(block)):
        text = _plain(sent)
        if len(text) < 3:
            continue
        units.append({"id": f"{bid}#{index}", "section": section, "text": text, "latex": _math(sent), "kind": "p", "abs": bool(block.get("abs"))})
    return units


def section_units(paper, section_id):
    """Oraciones (y ecuaciones) de la sección `section_id`. Vacío si no existe."""
    blocks = paper.get("blocks") or []
    start = None
    for index, block in enumerate(blocks):
        if isinstance(block, dict) and str(block.get("id")) == str(section_id) and block.get("kind") == "h":
            start = index
            break
    if start is None:
        return []
    level = int(blocks[start].get("level") or 1)
    current = _plain(blocks[start].get("inlines"))
    units = []
    for block in blocks[start + 1:]:
        if not isinstance(block, dict):
            continue
        if block.get("kind") == "h":
            if int(block.get("level") or 9) <= level:
                break
            current = _plain(block.get("inlines")) or current
            if int(block.get("level") or 9) >= 4:
                # Los párrafos con título (LLaMA «English CommonCrawl [67%].») traen el dato en el título.
                units.extend(_units_of(block, current))
            continue
        units.extend(_units_of(block, current))
    return units


def paper_units(paper):
    """Todas las oraciones del paper (abstract incluido), cada una con su sección."""
    units, current = [], "Abstract"
    for block in paper.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if block.get("kind") == "h":
            current = _plain(block.get("inlines")) or current
            if int(block.get("level") or 9) >= 4:
                units.extend(_units_of(block, current))
            continue
        units.extend(_units_of(block, current))
    return units


def section_title(paper, section_id):
    for sid, _level, title in headings(paper):
        if sid == str(section_id):
            return title
    return ""


_PTR = re.compile(r"b\d+(?:#\d+)?")


def ptr_of(raw):
    """El id al inicio de lo que devolvió el modelo («[b22#0] texto…» → b22#0)."""
    hit = _PTR.search(str(raw or ""))
    return hit.group(0) if hit else ""


def numbered(units, limit=None):
    """Texto para el prompt: `[b26.0] …` por línea."""
    rows = units if limit is None else units[:limit]
    return "\n".join(f"[{unit['id']}] {unit['text']}" for unit in rows)
