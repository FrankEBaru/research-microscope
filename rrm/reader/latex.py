"""LaTeX e-print -> the block JSON the reader UI already consumes.

Schema (one paper object):

    {
      "arxivId": str, "corpusid": int | null, "title": str, "authors": [str],
      "date": str, "abstract": str, "tldr": str, "license": str | null, "authorNotes": [str],
      "full": true, "source": "latex" | "ocr" | "abstract",
      "refs": {citekey: str}, "blocks": [Block],
      "status": str, "stage": str, "stages": {name: str}
    }

Block is `{id, kind, ...}`. kind is one of:

    h     level, unnumbered, number, inlines, label?
    p     inlines, sents, abs?, raw?
    eq    tex, env, label?, labels?, number?, katex_ok, source ("latex"|"ocr")
    list  items: [inlines]
    fig   label?, images: [relative path], caption: inlines
    table label?, head: [row of inlines], body: [row of inlines], caption: inlines

Inlines are `{t: text|math|em|strong|span|cite|link|code|note|ref, ...}`.
`ref` carries label, and after linking also target (block id) and number.
`sents` is a partition of that paragraph's inlines. `raw: true` means the
region was not understood; the TeX is kept as text and nothing is dropped.
Display math is macro-expanded (`\\\\newcommand`, `\\\\def`, `\\\\DeclareMathOperator`,
including local `.sty`). `\\\\input` / `\\\\include` are inlined. `figure*` is a figure.
"""

import re
from pathlib import Path

from rrm.reader.katex import check_tex, katex_available
from rrm.reader.source import (
    _ABBREV, _LAYOUT, _body, _grab, _labels, _skip_ws, _sty_macros,
    collect_macros, expand_math, find_main_tex, inline_tree, is_pdfpages_wrapper,
    read_braced, read_bracket, read_env, read_name, strip_comments, _grab_all,
)

_MATH = {
    "equation", "align", "alignat", "eqnarray", "gather", "multline", "flalign", "dmath", "displaymath",
}
_MATRIX = {
    "bmatrix", "pmatrix", "matrix", "vmatrix", "Vmatrix", "Bmatrix", "smallmatrix",
    "cases", "aligned", "split", "gathered", "array", "subarray",
}
_UNNUMBERED_MATH = {"displaymath"}
_PROSE = {
    "theorem", "lemma", "proof", "definition", "proposition", "corollary", "remark",
    "example", "assumption", "conjecture", "claim", "observation", "fact", "hypothesis",
    "property", "note", "lem", "thm", "defn", "prop", "cor", "ex",
}
# Packages that are not in the e-print. Applied only when the paper does not define them.
_FALLBACK_MACROS = {
    "bm": {"n": 1, "opt": None, "body": r"\boldsymbol{#1}"},
    "mathlarger": {"n": 1, "opt": None, "body": "#1"},
    "xspace": {"n": 0, "opt": None, "body": ""},
}
_HEADS = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}



def text_tokens(text: str) -> list:
    out = []
    for w in re.split(r"(\s+)", text):
        if w:
            out.append({"t": "text", "v": " " if w.isspace() else w})
    return out


def plain(inls) -> str:
    s = []
    for x in inls:
        t = x["t"]
        if t == "text":
            s.append(x["v"])
        elif t == "math":
            s.append("$" + x["v"] + "$")
        elif t in ("em", "strong", "span", "link"):
            s.append(plain(x["c"]))
        elif t == "code":
            s.append(x["v"])
        elif t == "cite":
            s.append("[cite]")
        elif t == "ref":
            s.append(x.get("label") or "")
        elif t == "note":
            s.append("")
    return re.sub(r"\s+", " ", "".join(s)).strip()


def split_sentences(inls):
    """Same sentence cut the UI uses: punctuation, then a capital, abbreviations kept."""
    sents, cur = [], []
    n = len(inls)
    i = 0
    while i < n:
        x = inls[i]
        cur.append(x)
        i += 1
        if x["t"] == "text" and re.search(r"[.!?][”’\")\]]*$", x["v"]) and x["v"] not in _ABBREV and not re.fullmatch(r"[A-Z]\.", x["v"]):
            while i < n and inls[i]["t"] == "note":
                cur.append(inls[i])
                i += 1
            j = i
            while j < n and inls[j]["t"] == "text" and inls[j]["v"].strip() == "":
                j += 1
            if j >= n:
                continue
            nx = inls[j]
            if nx["t"] == "text" and re.match(r"[A-Z“‘]", nx["v"]):
                cur += inls[i:j]
                sents.append(cur)
                cur = []
                i = j
    if cur:
        sents.append(cur)
    return sents



def parse_inlines(s: str, macros: dict) -> list:
    out = []
    buf = []

    def flush():
        if buf:
            out.extend(text_tokens("".join(buf)))
            buf.clear()

    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\":
            name, j = read_name(s, i)
            if name in ("emph", "textit", "textbf", "texttt", "textsc"):
                j = _skip_ws(s, j)
                if j < n and s[j] == "{":
                    inner, j = read_braced(s, j)
                    flush()
                    kind = {"textbf": "strong", "texttt": "code"}.get(name, "em")
                    if kind == "code":
                        out.append({"t": "code", "v": plain(parse_inlines(inner, macros))})
                    else:
                        out.append({"t": kind, "c": parse_inlines(inner, macros)})
                    i = j
                    continue
            if name in ("footnote", "thanks"):
                j = _skip_ws(s, j)
                if j < n and s[j] == "{":
                    inner, j = read_braced(s, j)
                    flush()
                    note_inls = parse_inlines(inner, macros)
                    out.append({"t": "note", "blocks": [{"kind": "p", "inlines": note_inls}]})
                    i = j
                    continue
            if name in ("cite", "citep", "citet", "citealp", "citeauthor"):
                j = _skip_ws(s, j)
                if j < n and s[j] == "[":
                    _, j = read_bracket(s, j)
                    j = _skip_ws(s, j)
                if j < n and s[j] == "{":
                    keys, j = read_braced(s, j)
                    flush()
                    out.append({"t": "cite", "keys": [k.strip() for k in keys.split(",") if k.strip()]})
                    i = j
                    continue
            if name in ("ref", "eqref", "autoref", "cref", "Cref"):
                j = _skip_ws(s, j)
                if j < n and s[j] == "{":
                    lab, j = read_braced(s, j)
                    flush()
                    out.append({"t": "ref", "label": lab.strip()})
                    i = j
                    continue
            if name == "href":
                j = _skip_ws(s, j)
                if j < n and s[j] == "{":
                    href, j = read_braced(s, j)
                    j = _skip_ws(s, j)
                    if j < n and s[j] == "{":
                        inner, j = read_braced(s, j)
                        flush()
                        out.append({"t": "link", "href": href, "c": parse_inlines(inner, macros)})
                        i = j
                        continue
            if name == "url":
                j = _skip_ws(s, j)
                if j < n and s[j] == "{":
                    href, j = read_braced(s, j)
                    flush()
                    out.append({"t": "link", "href": href, "c": text_tokens(href)})
                    i = j
                    continue
            if name in _LAYOUT or name in ("caption",):
                j = _skip_ws(s, j)
                if name in ("vspace", "hspace", "thispagestyle", "pagestyle") and j < n and s[j] == "{":
                    _, j = read_braced(s, j)
                elif name == "label" and j < n and s[j] == "{":
                    _, j = read_braced(s, j)
                elif j < n and s[j] == "{":
                    _, j = read_braced(s, j)
                i = j
                continue
            if name in macros and macros[name]["n"] == 0 and macros[name]["opt"] is None:
                # expand zero-arg text macros so author shorthand is not dropped
                flush()
                repl = expand_math("\\" + name, macros)
                if repl != "\\" + name:
                    out.extend(parse_inlines(repl, {}))
                    i = j
                    continue
            buf.append(s[i:j])
            i = j
            continue
        if s[i] == "$" and not (i and s[i - 1] == "\\"):
            if s.startswith("$$", i):
                end = s.find("$$", i + 2)
                if end < 0:
                    buf.append(s[i:])
                    break
                flush()
                inner = expand_math(s[i + 2:end], macros)
                out.append({"t": "math", "v": inner.strip(), "display": True})
                i = end + 2
                continue
            end = i + 1
            while end < n:
                if s[end] == "\\":
                    end += 2
                    continue
                if s[end] == "$":
                    break
                end += 1
            if end >= n:
                buf.append(s[i:])
                break
            flush()
            inner = expand_math(s[i + 1:end], macros)
            out.append({"t": "math", "v": inner.strip(), "display": False})
            i = end + 1
            continue
        if s.startswith("\\(", i):
            end = s.find("\\)", i + 2)
            if end < 0:
                buf.append(s[i:])
                break
            flush()
            out.append({"t": "math", "v": expand_math(s[i + 2:end], macros).strip(), "display": False})
            i = end + 2
            continue
        buf.append(s[i])
        i += 1
    flush()
    return out


def _eq_block(inner: str, env: str, macros: dict, numbered: bool, number: int | None):
    cleaned, labs = _labels(inner)
    cleaned = expand_math(cleaned.strip(), macros)
    block = {
        "kind": "eq",
        "tex": cleaned,
        "env": env,
        "katex_ok": None,
        "source": "latex",
        "raw": False,
    }
    if labs:
        block["label"] = labs[0]
        block["labels"] = labs
    if numbered and number is not None:
        block["number"] = number
    return block


def _raw_block(tex: str):
    return {"kind": "p", "raw": True, "inlines": text_tokens(tex.strip())}


def _fig_block(inner: str, macros: dict):
    images = re.findall(r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}", inner)
    images += re.findall(r"\\epsfig\s*\{[^}]*file\s*=\s*([^,}\s]+)", inner)
    cap = ""
    m = re.search(r"\\caption\s*(\[[^\]]*\])?\s*\{", inner)
    if m:
        cap, _ = read_braced(inner, m.end() - 1)
    labs = re.findall(r"\\label\{([^}]+)\}", inner)
    if not images and not cap.strip():
        return _raw_block("\\begin{figure}" + inner + "\\end{figure}")
    block = {"kind": "fig", "images": images, "caption": parse_inlines(cap, macros), "raw_paths": images}
    if labs:
        block["label"] = labs[0]
    return block


def _split_top(s: str, sep: str) -> list[str]:
    parts, buf = [], []
    depth_c = depth_b = 0
    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\":
            if sep == "\\\\" and s.startswith("\\\\", i) and depth_c == 0:
                parts.append("".join(buf))
                buf = []
                i += 2
                continue
            buf.append(s[i:i + 2])
            i += 2
            continue
        if s[i] == "{":
            depth_c += 1
        elif s[i] == "}":
            depth_c = max(0, depth_c - 1)
        elif s[i] == "&" and sep == "&" and depth_c == 0 and depth_b == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(s[i])
        i += 1
    parts.append("".join(buf))
    return parts


def _tabular_rows(inner: str, macros: dict):
    text = re.sub(r"\\(toprule|midrule|bottomrule|hline)\b", "", inner)
    # drop the column spec if the caller passed only the body; rows are \\-separated
    rows = []
    for line in _split_top(text, "\\\\"):
        if not line.strip() or line.strip() in {r"\hline"}:
            continue
        cells = [parse_inlines(c.strip(), macros) for c in _split_top(line, "&")]
        if any(plain(c) or c for c in cells):
            rows.append(cells)
    return rows


def _table_block(inner: str, macros: dict):
    cap = ""
    m = re.search(r"\\caption\s*(\[[^\]]*\])?\s*\{", inner)
    if m:
        cap, _ = read_braced(inner, m.end() - 1)
    labs = re.findall(r"\\label\{([^}]+)\}", inner)
    tab = ""
    tm = re.search(r"\\begin\{tabular\*?\}", inner)
    if tm:
        _, tab, _ = read_env(inner, tm.start())
        # drop column preamble {lcr}
        tab_s = tab.lstrip()
        if tab_s.startswith("{"):
            _, after = read_braced(tab, tab.find("{"))
            # read_braced index is relative to tab
            brace_at = tab.find("{")
            _, end = read_braced(tab, brace_at)
            tab = tab[end:]
    rows = _tabular_rows(tab or inner, macros)
    block = {
        "kind": "table",
        "head": rows[:1],
        "body": rows[1:],
        "caption": parse_inlines(cap, macros),
    }
    if labs:
        block["label"] = labs[0]
    if not rows and not cap.strip():
        return _raw_block(inner)
    return block



def _unwrap_prose(inner: str, macros: dict, prose: set) -> list:
    """Theorem-like environments stay in the block stream, including the equations inside them."""
    blocks = parse_body(inner, macros, prose)
    m = re.match(r"\s*\\label\{([^}]+)\}", inner)
    if m and blocks and not blocks[0].get("label"):
        blocks[0]["label"] = m.group(1)
    return blocks or [_raw_block(inner)]


def _list_blocks(inner: str, macros: dict, prose: set) -> list:
    """List items are inlines. An equation inside an item becomes its own block, so it is not dropped."""
    parts = re.split(r"\\item\b", inner)
    chunks = parts[1:] if len(parts) > 1 else parts
    out, items = [], []

    def flush():
        if items:
            out.append({"kind": "list", "items": list(items)})
            items.clear()

    for part in chunks:
        part = re.sub(r"^\s*\[[^\]]*\]", "", part, count=1)
        if not part.strip():
            continue
        for b in parse_body(part, macros, prose):
            if b.get("kind") == "p" and not b.get("raw"):
                items.append(b.get("inlines") or [])
            elif b.get("kind") == "list":
                flush()
                out.append(b)
            else:
                flush()
                out.append(b)
    flush()
    return out or [_raw_block(inner)]


def _bibliography(tex: str) -> dict:
    refs = {}
    for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        start = m.end()
        nxt = re.search(r"\\bibitem|\\end\{thebibliography\}", tex[start:])
        chunk = tex[start:start + nxt.start()] if nxt else tex[start:start + 800]
        chunk = re.sub(r"\\newblock", " ", chunk)
        chunk = re.sub(r"\\(?:emph|textit|textbf|url|href)\{([^{}]*)\}", r"\1", chunk)
        chunk = chunk.replace("~", " ").replace("{", "").replace("}", "")
        chunk = re.sub(r"\\[A-Za-z]+", "", chunk)
        refs[m.group(1)] = re.sub(r"\s+", " ", chunk).strip()
    return refs


def _thanks(tex: str) -> list:
    out = []
    for m in re.finditer(r"\\thanks\s*\{", tex):
        inner, _ = read_braced(tex, m.end() - 1)
        out.append(re.sub(r"\s+", " ", inner).strip())
    return out


def _prose_names(tex: str) -> set:
    names = set(_PROSE)
    names.update(re.findall(r"\\newtheorem\*?\s*\{([^}]+)\}", tex))
    return names


def parse_body(body: str, macros: dict, prose: set | None = None) -> list:
    blocks = []
    counters = [0, 0, 0, 0]
    appendix = False
    eq_n = 0
    i, n = 0, len(body)
    stop_display = "[" not in macros
    prose = _PROSE if prose is None else prose
    while i < n:
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if body.startswith("\\begin{", i):
            name, inner, i2 = read_env(body, i)
            if not name:
                blocks.append(_raw_block(body[i:]))
                break
            base = name[:-1] if name.endswith("*") else name
            star = name.endswith("*")
            i = i2
            if base in _MATH or base in _MATRIX:
                numbered = base in _MATH and (not star) and base not in _UNNUMBERED_MATH
                number = None
                if numbered:
                    eq_n += 1
                    number = eq_n
                blocks.append(_eq_block(inner, base, macros, numbered, number))
            elif base in ("figure", "wrapfigure"):
                blocks.append(_fig_block(inner, macros))
            elif base in ("table",):
                blocks.append(_table_block(inner, macros))
            elif base in ("itemize", "enumerate", "description"):
                blocks.extend(_list_blocks(inner, macros, prose))
            elif base in ("abstract", "center", "quote", "quotation", "subequations") or base in prose:
                blocks.extend(_unwrap_prose(inner, macros, prose))
            elif base == "thebibliography":
                continue
            elif base in ("tabular", "tabularx", "longtable"):
                blocks.append(_table_block(inner, macros))
            elif base in ("verbatim", "lstlisting", "minted", "algorithm", "algorithmic"):
                blocks.append(_raw_block("\\begin{" + name + "}" + inner + "\\end{" + name + "}"))
            else:
                blocks.append(_raw_block("\\begin{" + name + "}" + inner + "\\end{" + name + "}"))
            continue
        if stop_display and body.startswith("\\[", i):
            end = body.find("\\]", i + 2)
            if end < 0:
                blocks.append(_raw_block(body[i:]))
                break
            blocks.append(_eq_block(body[i + 2:end], "display", macros, False, None))
            i = end + 2
            continue
        if body.startswith("$$", i):
            end = body.find("$$", i + 2)
            if end < 0:
                blocks.append(_raw_block(body[i:]))
                break
            blocks.append(_eq_block(body[i + 2:end], "display", macros, False, None))
            i = end + 2
            continue
        if body[i] == "\\":
            name, j = read_name(body, i)
            if name in _HEADS:
                level, star, title, i = _read_section(body, i)
                number = None
                if not star:
                    if appendix and level == 1:
                        counters[0] += 1
                        for k in range(1, 4):
                            counters[k] = 0
                        number = chr(ord("A") + counters[0] - 1)
                    else:
                        counters[level - 1] += 1
                        for k in range(level, 4):
                            counters[k] = 0
                        number = ".".join(str(c) for c in counters[:level] if not (appendix and False))
                        if appendix and level > 1 and counters[0]:
                            number = chr(ord("A") + counters[0] - 1) + "." + ".".join(str(c) for c in counters[1:level])
                lab, i = _read_following_label(body, i)
                block = {
                    "kind": "h",
                    "level": level,
                    "unnumbered": star,
                    "number": number,
                    "inlines": parse_inlines(title, macros),
                }
                if lab:
                    block["label"] = lab.strip()
                blocks.append(block)
                continue
            if name == "appendix":
                appendix = True
                counters[:] = [0, 0, 0, 0]
                i = j
                continue
            if name in ("maketitle", "tableofcontents", "clearpage", "newpage", "cleardoublepage"):
                i = j
                continue
            if name in ("bibliography", "bibliographystyle"):
                i = j
                i = _skip_ws(body, i)
                if i < n and body[i] == "{":
                    _, i = read_braced(body, i)
                continue
        para, nxt = _read_paragraph(body, i, stop_display)
        if nxt <= i:
            i += 1
            continue
        i = nxt
        if para.strip():
            ins = parse_inlines(para, macros)
            if ins and plain(ins):
                blocks.append({"kind": "p", "inlines": ins})
    return blocks


def _read_following_label(body, i):
    k = _skip_ws(body, i)
    if not body.startswith("\\label{", k):
        return None, i
    lab, end = read_braced(body, k + len("\\label"))
    return lab.strip(), end


def _read_section(s, i):
    name, j = read_name(s, i)
    star = j < len(s) and s[j] == "*"
    if star:
        j += 1
    j = _skip_ws(s, j)
    if j < len(s) and s[j] == "[":
        _, j = read_bracket(s, j)
        j = _skip_ws(s, j)
    title = ""
    if j < len(s) and s[j] == "{":
        title, j = read_braced(s, j)
    return _HEADS.get(name, 1), star, title, j


def _read_paragraph(s, i, stop_display=True):
    n = len(s)
    start = i
    depth = 0
    while i < n:
        if s[i] == "\\":
            if depth == 0 and (
                s.startswith("\\begin{", i)
                or (stop_display and s.startswith("\\[", i))
                or s.startswith("\\section", i)
                or s.startswith("\\subsection", i)
                or s.startswith("\\subsubsection", i)
                or s.startswith("\\paragraph", i)
                or s.startswith("\\appendix", i)
                or s.startswith("\\bibliography", i)
            ):
                break
            i += 2
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth = max(0, depth - 1)
        elif s[i] == "$" and i + 1 < n and s[i + 1] == "$" and depth == 0:
            break
        elif s[i] == "\n" and depth == 0 and i + 1 < n and s[i + 1] == "\n":
            return s[start:i], i
        i += 1
    return s[start:i], i


def _link(blocks):
    by_label = {}
    numbers = {}
    for b in blocks:
        labs = []
        if b.get("label"):
            labs.append(b["label"])
        labs.extend(b.get("labels") or [])
        for lab in labs:
            by_label[lab] = b["id"]
            if b.get("number") is not None:
                numbers[lab] = b["number"]

    def walk(inls):
        for x in inls:
            if x.get("t") == "ref" and x.get("label") in by_label:
                x["target"] = by_label[x["label"]]
                if x["label"] in numbers:
                    x["number"] = numbers[x["label"]]
            elif "c" in x and isinstance(x["c"], list):
                walk(x["c"])
            elif x.get("t") == "note":
                for nb in x.get("blocks") or []:
                    walk(nb.get("inlines") or [])

    for b in blocks:
        if "inlines" in b:
            walk(b["inlines"])
        if b.get("kind") == "list":
            for item in b.get("items") or []:
                walk(item)
        if "caption" in b:
            walk(b["caption"])
        if b.get("kind") == "table":
            for row in (b.get("head") or []) + (b.get("body") or []):
                for cell in row:
                    walk(cell)


def finalize(blocks: list) -> list:
    kept = []
    for b in blocks:
        if b.get("kind") == "p" and not b.get("raw") and not plain(b.get("inlines") or []):
            continue
        kept.append(b)
    for i, b in enumerate(kept):
        b["id"] = f"b{i}"
        if b["kind"] == "p":
            b["sents"] = split_sentences(b.get("inlines") or [])
    _link(kept)
    return kept


def inline_math(blocks: list) -> list:
    """Inline math tokens in reading order. `sents` repeats `inlines`, so it is skipped."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            if x.get("t") == "math":
                found.append(x)
            for k, v in x.items():
                if k != "sents":
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for b in blocks:
        if b.get("kind") != "eq":
            walk(b)
    return found


def attach_katex(blocks: list) -> int:
    eqs = [b for b in blocks if b.get("kind") == "eq"]
    inl = inline_math(blocks)
    if not eqs and not inl:
        return 0
    if not katex_available():
        for b in eqs:
            b["katex_ok"] = None
        return 0
    flags = check_tex([b.get("tex") or "" for b in eqs] + [m.get("v") or "" for m in inl])
    ok = 0
    for b, flag in zip(eqs, flags[:len(eqs)]):
        b["katex_ok"] = bool(flag)
        ok += int(bool(flag))
    for m, flag in zip(inl, flags[len(eqs):]):
        m["katex_ok"] = bool(flag)
    return ok


def _drop_cmd_args(text: str, names: tuple) -> str:
    """Remove \\name{...} including its balanced argument (thanks, footnote, texttt...)."""
    out = text
    for name in names:
        pat = re.compile(r"\\" + name + r"\*?\s*(?:\[[^\]]*\])?\s*\{")
        while True:
            m = pat.search(out)
            if not m:
                break
            depth, j = 1, m.end()
            while j < len(out) and depth:
                depth += {"{": 1, "}": -1}.get(out[j], 0)
                j += 1
            out = out[:m.start()] + " " + out[j:]
    return out


_AFFIL_WORDS = {
    "university", "universite", "dept", "department", "google", "stanford", "institute", "openai",
    "research", "mit", "laboratory", "lab", "labs", "college", "school", "inc", "deepmind",
    "microsoft", "meta", "facebook", "amazon", "nvidia", "eth", "cmu", "berkeley", "cambridge",
    "oxford", "faculty", "academy", "corp", "corporation", "ltd", "gmbh", "center", "centre",
}
_AFFIL_PHRASES = ("equal contribution", "work done", "work performed", "computer science")
_PARTICLES = {"van", "von", "de", "da", "di", "del", "der", "den", "la", "le", "st"}
_DROP_AUTHOR_CMDS = (
    "thanks", "footnote", "footnotetext", "footnotemark", "texttt", "url", "href", "email",
    "textsuperscript", "affil", "affiliation", "institute", "address", "inst",
    "IEEEauthorblockA", "hspace", "vspace", "color", "textcolor",
)


_ACCENTS = (("{\\L}", "Ł"), ("\\L ", "Ł"), ("\\L{}", "Ł"), ("{\\l}", "ł"),
            ('\\"u', "ü"), ('\\"o', "ö"), ('\\"a', "ä"), ('\\"{u}', "ü"), ('\\"{o}', "ö"),
            ("\\'e", "é"), ("\\'a", "á"), ("\\'i", "í"), ("\\'o", "ó"), ("\\~n", "ñ"))


def _is_affiliation(line: str) -> bool:
    low = line.lower()
    words = set(re.findall(r"[a-z]+", low))
    if words & _AFFIL_WORDS:
        return True
    return any(phrase in low for phrase in _AFFIL_PHRASES)


def _looks_like_person(name: str) -> bool:
    name = re.sub(r"\s+", " ", name).strip(" ,;.*")
    if not name or len(name) < 3 or len(name) > 80 or _is_affiliation(name):
        return False
    if "@" in name or any(ch.isdigit() for ch in name):
        return False
    words = name.split()
    if not words or len(words) > 6:
        return False
    if not words[0][:1].isupper():
        return False
    for word in words:
        bare = word.strip(".").lower()
        if bare in _PARTICLES:
            continue
        if not word[:1].isupper():
            return False
    return True


def _clean_name_line(line: str) -> str:
    line = re.sub(r"\\(?:emph|textit|textbf|textsc|textrm|textmd|mbox)\{([^{}]*)\}", r"\1", line)
    line = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", line)
    line = line.replace("{", " ").replace("}", " ").replace("~", " ")
    line = re.sub(r"\([^)]*\)", " ", line)
    line = re.sub(r"\S+@\S+", " ", line)
    line = re.sub(r"[\d*†‡§¶]+", "", line)
    return re.sub(r"\s+", " ", line).strip(" ,;.*")


def _prepare_author_text(raw: str) -> str:
    text = _drop_cmd_args(raw, _DROP_AUTHOR_CMDS)
    text = re.sub(r"~~+|\\quad|\\qquad", "\n", text)
    text = re.sub(r"\$[^$]*\$", " ", text)
    for src, dst in _ACCENTS:
        text = text.replace(src, dst)
    return text


def _split_name_line(line: str) -> list:
    line = line.strip(" ,;.*")
    if not line:
        return []
    and_parts = re.split(r"\s+\band\b\s+", line)
    if len(and_parts) > 1:
        names = []
        for part in and_parts:
            names.extend(_split_name_line(part))
        return names
    comma_parts = [part.strip() for part in line.split(",") if part.strip()]
    if len(comma_parts) >= 2 and all(_looks_like_person(part) and len(part.split()) >= 2 for part in comma_parts):
        return comma_parts
    return [line] if _looks_like_person(line) else []


def _names_from_author_body(raw: str) -> list:
    """One \\author / \\icmlauthor / \\IEEEauthorblockN body. The first real line is the name."""
    text = _prepare_author_text(raw)
    people = re.split(r"\\and\b", text, flags=re.I)
    names = []
    for person in people:
        chosen = ""
        for line in re.split(r"\\\\|\n", person):
            cleaned = _clean_name_line(line)
            if not cleaned or _is_affiliation(cleaned):
                continue
            chosen = cleaned
            break
        names.extend(_split_name_line(chosen))
    return names


def _dedupe_names(names: list) -> list:
    out = []
    for name in names:
        name = re.sub(r"\s+", " ", name).strip()
        if name and name not in out:
            out.append(name)
    return out[:40]


def _authors_in(tex: str) -> list:
    names = []
    for body in _grab_all(tex, "author"):
        if "\\IEEEauthorblockN" in body or "\\icmlauthor" in body:
            for cmd in ("IEEEauthorblockN", "icmlauthor"):
                for inner in _grab_all(body, cmd):
                    names.extend(_names_from_author_body(inner))
        else:
            names.extend(_names_from_author_body(body))
    if not names:
        for cmd in ("IEEEauthorblockN", "icmlauthor"):
            for inner in _grab_all(tex, cmd):
                names.extend(_names_from_author_body(inner))
    return _dedupe_names(names)


def extract_authors(tex: str) -> list:
    """Authors from \\author, \\icmlauthor, and \\IEEEauthorblockN.

    Handles \\and / \\And, \\thanks, and the name-then-affiliation lines used by
    NeurIPS, ICML, ICLR, arXiv, and IEEE. Semantic Scholar names win later when present.
    """
    cut = tex.find("\\begin{document}")
    scope = tex if cut < 0 else tex[:cut]
    names = _authors_in(scope)
    if not names and cut >= 0:
        names = _authors_in(tex)
    return names


def materialize_figures(blocks: list, root: Path, dest: Path) -> int:
    """Copy or render figure files into dest. Paths on the block become relative file names."""
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for b in blocks:
        if b.get("kind") != "fig":
            continue
        files = []
        for im in b.get("raw_paths") or b.get("images") or []:
            src = _find_graphic(root, im)
            if src is None:
                files.append(im)
                continue
            out = _render_graphic(src, dest)
            files.append(out.name if out else im)
            n += int(out is not None)
        b["images"] = files
        b.pop("raw_paths", None)
    return n


def _find_graphic(root: Path, name: str) -> Path | None:
    name = name.strip()
    cands = [root / name]
    for ext in ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps"):
        cands.append(root / (name + ext))
    for c in cands:
        if c.is_file():
            return c
    stem = Path(name).name
    hits = list(root.rglob(stem))
    if not hits and Path(name).suffix == "":
        for ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps"):
            hits = list(root.rglob(stem + ext))
            if hits:
                break
    return hits[0] if hits else None


def _render_graphic(src: Path, dest: Path) -> Path | None:
    ext = src.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        target = dest / src.name
        target.write_bytes(src.read_bytes())
        return target
    if ext == ".pdf":
        target = dest / (src.stem + ".png")
        try:
            import pymupdf
            doc = pymupdf.open(src)
            page = doc[0]
            page.get_pixmap(dpi=110).save(target)
            doc.close()
            return target
        except Exception:
            return None
    if ext in {".eps", ".ps"}:
        target = dest / (src.stem + ".png")
        import shutil
        import subprocess
        if not shutil.which("gs"):
            return None
        proc = subprocess.run(
            ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-r110", f"-sOutputFile={target}", str(src)],
            capture_output=True,
        )
        return target if proc.returncode == 0 and target.exists() else None
    return None


def parse_tex(tex: str, macros: dict | None = None, arxiv_id: str = "") -> dict:
    # Keep the caller's macros (.sty / .def). Rebinding `macros` first used to drop them.
    defined = dict(_FALLBACK_MACROS)
    defined.update(macros or {})
    defined.update(collect_macros(tex))
    macros = defined
    prose = _prose_names(tex)
    abstract = ""
    m = re.search(r"\\begin\{abstract\}", tex)
    if m:
        name, inner, _ = read_env(tex, m.start())
        if name == "abstract":
            abstract = plain(parse_inlines(inner, macros))
    body = _body(tex)
    # abstract env is re-parsed into the body; pull it out once via dispatch which unwraps it.
    # Remove the environment so it is not duplicated below the inserted abstract block.
    body_wo = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", "", body, count=1, flags=re.S)
    blocks = parse_body(body_wo, macros, prose)
    if abstract:
        blocks.insert(0, {"kind": "p", "abs": True, "inlines": parse_inlines(abstract, {})})
    license_note = None
    if blocks and blocks[0]["kind"] == "p" and "Provided proper attribution" in plain(blocks[0].get("inlines") or []):
        license_note = plain(blocks[0]["inlines"])
        blocks = blocks[1:]
    blocks = finalize(blocks)
    title = plain(parse_inlines(_grab(tex, "title"), macros))
    return {
        "arxivId": arxiv_id,
        "corpusid": None,
        "title": title,
        "authors": extract_authors(tex),
        "date": plain(parse_inlines(_grab(tex, "date"), macros)),
        "abstract": abstract,
        "license": license_note,
        "authorNotes": _thanks(tex),
        "full": True,
        "source": "latex",
        "refs": _bibliography(tex),
        "blocks": blocks,
    }


def parse_tree(root: Path, arxiv_id: str = "") -> dict:
    """Parse an unpacked e-print. route is 'pdf' for a pdfpages wrapper, else 'latex'."""
    main = find_main_tex(root)
    if main is None:
        return {"route": "pdf", "reason": "no tex in e-print", "paper": None}
    tex = inline_tree(main, root)
    # .bbl sits beside the main file and is what \\bibliography expands to after bibtex
    for bbl in list(root.rglob("*.bbl"))[:3]:
        try:
            tex += "\n" + strip_comments(bbl.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    if is_pdfpages_wrapper(tex):
        return {"route": "pdf", "reason": "pdfpages wrapper", "paper": None}
    macros = _sty_macros(root)
    paper = parse_tex(tex, macros, arxiv_id=arxiv_id)
    return {"route": "latex", "reason": None, "paper": paper, "main": str(main)}


def stats(paper: dict) -> dict:
    blocks = paper.get("blocks") or []
    eqs = [b for b in blocks if b.get("kind") == "eq"]
    inl = inline_math(blocks)
    return {
        "equations": len(eqs),
        "katex_ok": sum(1 for b in eqs if b.get("katex_ok") is True),
        "katex_fail": sum(1 for b in eqs if b.get("katex_ok") is False),
        "raw_fallbacks": sum(1 for b in blocks if b.get("raw")),
        "figures": sum(1 for b in blocks if b.get("kind") == "fig"),
        "tables": sum(1 for b in blocks if b.get("kind") == "table"),
        "sections": sum(1 for b in blocks if b.get("kind") == "h"),
        "inline_math": len(inl),
        "inline_katex_ok": sum(1 for m in inl if m.get("katex_ok") is True),
    }
