"""Candidatos de hueco. No llama al modelo y no arma tarjetas."""

import re

from rrm.reader.latex import plain

_TOKEN = re.compile(r"\\[A-Za-z]+|[A-Za-z](?:_[A-Za-z0-9]+)+")
_KEEP = ("introduc", "method", "result", "conclusion", "approach", "model", "método", "resultado")
_DROP = ("reference", "acknowledgment", "acknowledgement", "appendix")
_EQ_WORD = re.compile(r"\b(?:Eqs?|Equations?|eqs?)\.?\s*\(?\s*(\d+)\s*\)?", re.I)
_FRAC = ("\\frac", "\\tfrac", "\\dfrac")


def normalize_math(tex):
    """d_{\\text{model}}, d_{\\mathrm{model}}, d_{model} y d_model son el mismo token."""
    text = tex or ""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\\(?:text|mathrm|mathit|operatorname)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"([A-Za-z])_\{([A-Za-z0-9]+)\}", r"\1_\2", text)
    return text


def tokens_of(tex):
    return _TOKEN.findall(normalize_math(tex))


def _flat(tex):
    return re.sub(r"\s+", "", tex or "")


def _brace(text, i):
    """text[i] es '{'. Devuelve (interior, índice siguiente) o None. Respeta \\{ y \\}."""
    if i >= len(text) or text[i] != "{":
        return None
    depth = 0
    j = i
    while j < len(text):
        if text[j] == "\\" and j + 1 < len(text):
            j += 2
            continue
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j], j + 1
        j += 1
    return None


def fracs(tex):
    """Pares (numerador, denominador) con llaves emparejadas. Si no cierran, ese frac no entra."""
    text = tex or ""
    found = []
    i = 0
    while i < len(text):
        cmd = next((name for name in _FRAC if text.startswith(name, i)), "")
        if not cmd:
            i += 1
            continue
        k = i + len(cmd)
        while k < len(text) and text[k] in " \t\n":
            k += 1
        left = _brace(text, k)
        if not left:
            i += 1
            continue
        k = left[1]
        while k < len(text) and text[k] in " \t\n":
            k += 1
        right = _brace(text, k)
        if not right:
            i += 1
            continue
        found.append((left[0], right[0]))
        i = right[1]
    return found


def sqrt_denominator(tex):
    """El denominador completo del primer frac cuyo B contiene \\sqrt. '' si no hay."""
    for _num, den in fracs(tex):
        if "\\sqrt" in den:
            return den
    return ""


def _has_sin(flat):
    return "\\sin" in flat or "sin(" in flat


def _has_cos(flat):
    return "\\cos" in flat or "cos(" in flat


def _blob(block):
    parts = [plain(block.get("inlines") or []), block.get("tex") or "", block.get("text") or ""]
    return "\n".join(parts)


def _heading(block):
    return plain(block.get("inlines") or []) or str(block.get("text") or "")


def _sents(block):
    raw = block.get("sents")
    if raw:
        return raw
    inlines = block.get("inlines")
    if inlines:
        return [inlines]
    text = str(block.get("text") or "").strip()
    return [[{"t": "text", "v": text}]] if text else []


def _sent_text(sent):
    if isinstance(sent, str):
        return " ".join(sent.split())
    return plain(sent)


def _words(text):
    return re.findall(r"\S+", text or "")


def _refs(block):
    labels, targets = set(), set()

    def walk(nodes):
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            if node.get("t") == "ref":
                for part in str(node.get("label") or "").split(","):
                    if part.strip():
                        labels.add(part.strip())
                if node.get("target"):
                    targets.add(str(node["target"]))
            if isinstance(node.get("c"), list):
                walk(node["c"])

    walk(block.get("inlines") or [])
    return labels, targets


def _eq_keys(block):
    labs = set()
    if block.get("label"):
        labs.add(str(block["label"]).strip())
    labs.update(str(lab).strip() for lab in block.get("labels") or [] if lab)
    number = block.get("number")
    return labs, (None if number is None else str(number)), str(block.get("id") or "")


def _nearest_p(blocks, start, step):
    i = start + step
    while 0 <= i < len(blocks):
        block = blocks[i]
        if isinstance(block, dict) and block.get("kind") == "p":
            return i
        i += step
    return None


def _citing(blocks, eq_index, skip):
    labs, number, bid = _eq_keys(blocks[eq_index])
    found = []
    for i, block in enumerate(blocks):
        if i in skip or not isinstance(block, dict) or block.get("kind") != "p":
            continue
        refs, targets = _refs(block)
        hit = bool(labs & refs) or (bid and bid in targets)
        if not hit and number is not None:
            hit = any(m.group(1) == number for m in _EQ_WORD.finditer(_blob(block)))
        if hit:
            found.append(i)
    found.sort(key=lambda i: (abs(i - eq_index), i))
    return found[:2]


def _same_subsection(blocks, eq_index, heading_at):
    start = heading_at + 1 if heading_at is not None else 0
    return [i for i in range(start, eq_index) if isinstance(blocks[i], dict) and blocks[i].get("kind") == "p"]


def _token_missing(token, blobs):
    needle = _flat(normalize_math(token))
    if not needle:
        return False
    return all(needle not in _flat(normalize_math(blob)) for blob in blobs)


def _runs(blocks):
    """Bloques eq seguidos. Un p corta la racha; un h no."""
    runs, cur = [], []
    for i, block in enumerate(blocks):
        if isinstance(block, dict) and block.get("kind") == "eq":
            cur.append(i)
            continue
        if isinstance(block, dict) and block.get("kind") == "p" and cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def _hint_for(tex):
    flat = _flat(tex)
    if _has_sin(flat) and _has_cos(flat) and "10000" in flat:
        return "matriz", ""
    den = sqrt_denominator(tex)
    if den:
        return "con_sin", den
    return "", ""


def find_gaps(blocks):
    blocks = [b for b in (blocks or []) if isinstance(b, dict)]
    section = ""
    heading_at = None
    sections = []
    for i, block in enumerate(blocks):
        if block.get("kind") == "h":
            section = _heading(block) or section
            heading_at = i
        sections.append((section, heading_at))

    equations = []
    for run in _runs(blocks):
        joined = " ".join(str(blocks[i].get("tex") or "") for i in run)
        hint, drop = _hint_for(joined)
        ids = [str(blocks[i].get("id") or "") for i in run]
        if hint == "matriz" and len(run) > 1:
            # La pista va en el primero y lista todos los ids.
            pass
        elif hint != "matriz":
            # con_sin y el hueco se miran por bloque; una racha solo agrupa la matriz.
            ids = None
        if hint == "matriz":
            first = run[0]
            sec, _h = sections[first]
            ctx = _context_blobs(blocks, first, sections)
            missing = [tok for tok in tokens_of(joined) if _token_missing(tok, ctx)]
            if missing or hint:
                equations.append({
                    "block_id": str(blocks[first].get("id") or ""),
                    "section": sec,
                    "tex": joined,
                    "missing": missing,
                    "hint": hint,
                    "drop": drop,
                    "blocks": ids or [str(blocks[first].get("id") or "")],
                    "para": _para_text(blocks, first),
                    "occupy": _occupy(blocks, first),
                })
            continue
        for index in run:
            tex = str(blocks[index].get("tex") or "")
            one_hint, one_drop = _hint_for(tex)
            sec, _h = sections[index]
            ctx = _context_blobs(blocks, index, sections)
            missing = [tok for tok in tokens_of(tex) if _token_missing(tok, ctx)]
            if not missing and not one_hint:
                continue
            equations.append({
                "block_id": str(blocks[index].get("id") or ""),
                "section": sec,
                "tex": tex,
                "missing": missing,
                "hint": one_hint,
                "drop": one_drop,
                "blocks": [str(blocks[index].get("id") or "")],
                "para": _para_text(blocks, index),
                "occupy": _occupy(blocks, index),
            })

    reminders = _reminders(blocks, sections)
    sentences = _sentences(blocks, sections)
    return {"equations": equations, "reminders": reminders, "sentences": sentences}


def _context_blobs(blocks, index, sections):
    _sec, heading_at = sections[index]
    idxs = set(_same_subsection(blocks, index, heading_at))
    prev = _nearest_p(blocks, index, -1)
    nxt = _nearest_p(blocks, index, 1)
    if prev is not None:
        idxs.add(prev)
    if nxt is not None:
        idxs.add(nxt)
    idxs.update(_citing(blocks, index, {i for i in (prev, nxt) if i is not None}))
    return [_blob(blocks[i]) for i in sorted(idxs)]


def _para_text(blocks, index):
    prev = _nearest_p(blocks, index, -1)
    nxt = _nearest_p(blocks, index, 1)
    parts = []
    if prev is not None:
        parts.append(_blob(blocks[prev]))
    parts.append(str(blocks[index].get("tex") or ""))
    if nxt is not None:
        parts.append(_blob(blocks[nxt]))
    return "\n".join(parts)


def _occupy(blocks, index):
    keys = [str(blocks[index].get("id") or "")]
    prev = _nearest_p(blocks, index, -1)
    if prev is not None:
        keys.append(str(blocks[prev].get("id") or ""))
    return keys


def _reminders(blocks, sections):
    first = {}
    out = []
    seen = set()
    for i, block in enumerate(blocks):
        if block.get("kind") != "p":
            continue
        sec = sections[i][0]
        for sent_i, sent in enumerate(_sents(block)):
            text = _sent_text(sent)
            for token in tokens_of(text):
                if "_" not in token and not token.startswith("\\"):
                    continue
                if token not in first:
                    first[token] = {
                        "block_id": str(block.get("id") or ""),
                        "sent_index": sent_i,
                        "section": sec,
                        "text": text[:400],
                        "token": token,
                        "generated": False,
                        "occupy": [str(block.get("id") or "")],
                    }
                    continue
                origin = first[token]
                if origin["section"] == sec or token in seen:
                    continue
                if token not in _flat(normalize_math(origin["text"])):
                    continue
                seen.add(token)
                out.append(dict(origin))
    return out


def _sentences(blocks, sections):
    rows = []
    for i, block in enumerate(blocks):
        if block.get("kind") != "p":
            continue
        sec = sections[i][0]
        low = sec.lower()
        for sent_i, sent in enumerate(_sents(block)):
            text = _sent_text(sent)
            if len(_words(text)) <= 25:
                continue
            rows.append({
                "block_id": str(block.get("id") or ""),
                "sent_index": sent_i,
                "section": sec,
                "text": text[:400],
                "keep": any(bit in low for bit in _KEEP),
                "drop": any(bit in low for bit in _DROP),
                "occupy": [str(block.get("id") or "")],
            })
    if any(row["keep"] for row in rows):
        picked = [row for row in rows if row["keep"]]
    else:
        picked = [row for row in rows if not row["drop"]]
    clean = []
    for row in picked[:12]:
        item = dict(row)
        item.pop("keep", None)
        item.pop("drop", None)
        clean.append(item)
    return clean
