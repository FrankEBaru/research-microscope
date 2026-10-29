"""Read an e-print: comments, macros, \\input, and the pdfpages check."""

import re
from pathlib import Path

_NEW = {"newcommand", "renewcommand", "providecommand", "DeclareRobustCommand"}
_LAYOUT = {
    "noindent", "vspace", "hspace", "centering", "raggedright", "raggedleft", "maketitle",
    "clearpage", "newpage", "cleardoublepage", "linebreak", "hfill", "vfill", "qquad", "quad",
    "smallskip", "medskip", "bigskip", "displaystyle", "textstyle", "normalsize", "small", "footnotesize",
    "scriptsize", "tiny", "large", "Large", "LARGE", "huge", "Huge", "centering", "raggedright",
    "thispagestyle", "pagestyle", "label", "index", "glossary",
}
_ABBREV = {"al.", "e.g.", "i.e.", "vs.", "Fig.", "Figs.", "Eq.", "Sec.", "approx.", "cf.", "No.", "etc."}
_SKIP_FILES = {".git", "__pycache__"}


def strip_comments(src: str) -> str:
    out = []
    i, n = 0, len(src)
    while i < n:
        if src[i] == "\\":
            out.append(src[i:i + 2])
            i += 2
            continue
        if src[i] == "%":
            while i < n and src[i] != "\n":
                i += 1
            if i < n and src[i] == "\n":
                i += 1
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def _skip_ws(s, i):
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def read_name(s, i):
    """i points at backslash. Return (name, index_after)."""
    i += 1
    if i >= len(s):
        return "", i
    if s[i] == "\\":
        return "\\\\", i + 1
    start = i
    if s[i].isalpha() or s[i] == "@":
        while i < len(s) and (s[i].isalpha() or s[i] == "@"):
            i += 1
        return s[start:i], i
    return s[i], i + 1


def read_braced(s, i):
    """i points at '{'. Return (inside, index_after_close). Unclosed: rest of string."""
    depth = 0
    start = i + 1
    j = i
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[start:j], j + 1
        j += 1
    return s[start:], len(s)


def read_bracket(s, i):
    """i points at '['. Bracket depth, braces respected."""
    depth_b, depth_c = 0, 0
    start = i + 1
    j = i
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "{":
            depth_c += 1
        elif s[j] == "}":
            depth_c = max(0, depth_c - 1)
        elif s[j] == "[" and depth_c == 0:
            depth_b += 1
        elif s[j] == "]" and depth_c == 0:
            depth_b -= 1
            if depth_b == 0:
                return s[start:j], j + 1
        j += 1
    return s[start:], len(s)


def read_env(s, i):
    """i at \\begin. Return (name, inner, index_after_end)."""
    m = re.match(r"\\begin\{([^}]+)\}", s[i:])
    if not m:
        return "", "", i + 6
    name = m.group(1)
    j = i + m.end()
    if j < len(s) and s[j] == "[":
        _, j = read_bracket(s, j)
    depth = 1
    pat = re.compile(r"\\(begin|end)\{" + re.escape(name) + r"\}")
    while True:
        m2 = pat.search(s, j)
        if not m2:
            return name, s[j:], len(s)
        if m2.group(1) == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return name, s[j:m2.start()], m2.end()
        j = m2.end()


def _grab(tex, command):
    token = "\\" + command
    i = 0
    while True:
        j = tex.find(token, i)
        if j < 0:
            return ""
        k = j + len(token)
        if k < len(tex) and (tex[k].isalpha() or tex[k] == "@"):
            i = k
            continue
        if k < len(tex) and tex[k] == "*":
            k += 1
        k = _skip_ws(tex, k)
        if k < len(tex) and tex[k] == "[":
            _, k = read_bracket(tex, k)
            k = _skip_ws(tex, k)
        if k < len(tex) and tex[k] == "{":
            body, _ = read_braced(tex, k)
            return body
        i = k


def _grab_all(tex, command) -> list:
    """Every balanced body of `\\command`, skipping optional [...] arguments."""
    token = "\\" + command
    out = []
    i = 0
    n = len(tex)
    while i < n:
        j = tex.find(token, i)
        if j < 0:
            break
        k = j + len(token)
        if k < n and (tex[k].isalpha() or tex[k] == "@"):
            i = k
            continue
        if k < n and tex[k] == "*":
            k += 1
        k = _skip_ws(tex, k)
        while k < n and tex[k] == "[":
            _, k = read_bracket(tex, k)
            k = _skip_ws(tex, k)
        if k < n and tex[k] == "{":
            body, k = read_braced(tex, k)
            out.append(body)
            i = k
            continue
        i = max(k, j + 1)
    return out


def collect_macros(tex: str) -> dict:
    """name -> {n: mandatory count, opt: default or None, body: str}. #1 is the optional arg when opt is set."""
    macros = {}
    i, n = 0, len(tex)
    while i < n:
        if tex[i] != "\\":
            i += 1
            continue
        name, j = read_name(tex, i)
        if name == "DeclareMathOperator":
            star = j < n and tex[j] == "*"
            if star:
                j += 1
            j = _skip_ws(tex, j)
            if j >= n or tex[j] != "{":
                i = j
                continue
            op, j = read_braced(tex, j)
            j = _skip_ws(tex, j)
            if j >= n or tex[j] != "{":
                i = j
                continue
            text, j = read_braced(tex, j)
            op = op.strip()
            if op.startswith("\\"):
                op = op[1:]
            wrap = "\\operatorname*{" if star else "\\operatorname{"
            if op:
                macros[op] = {"n": 0, "opt": None, "body": wrap + text + "}"}
            i = j
            continue
        if name == "let":
            j = _skip_ws(tex, j)
            if j >= n or tex[j] != "\\":
                i = max(j, i + 1)
                continue
            dest, j = read_name(tex, j)
            j = _skip_ws(tex, j)
            if j < n and tex[j] == "=":
                j += 1
                j = _skip_ws(tex, j)
            if not dest:
                i = j
                continue
            if j < n and tex[j] == "\\":
                src, j = read_name(tex, j)
                macros[dest] = {"n": 0, "opt": None, "body": "\\" + src, "let": src}
            elif j < n:
                macros[dest] = {"n": 0, "opt": None, "body": tex[j]}
                j += 1
            i = j
            continue
        if name in ("def", "gdef", "edef", "xdef"):
            j = _skip_ws(tex, j)
            if j >= n or tex[j] != "\\":
                i = max(j, i + 1)
                continue
            mname, j = read_name(tex, j)
            params = []
            delimited = False
            while j < n and tex[j] != "{":
                if tex[j] == "#":
                    j += 1
                    if j < n and tex[j].isdigit():
                        params.append(tex[j])
                        j += 1
                        continue
                if tex[j] not in " \t\r\n":
                    delimited = True
                    break
                j += 1
            brace = tex.find("{", j)
            if brace < 0:
                break
            body, j = read_braced(tex, brace)
            if mname and not delimited:
                macros[mname] = {"n": len(params), "opt": None, "body": body}
            i = j
            continue
        if name not in _NEW:
            i = j
            continue
        if j < n and tex[j] == "*":
            j += 1
        j = _skip_ws(tex, j)
        if j < n and tex[j] == "{":
            inner, j = read_braced(tex, j)
            inner = inner.strip()
            mname = inner[1:] if inner.startswith("\\") else inner
            if "\\" in mname:
                mname, _ = read_name(inner, 0) if inner.startswith("\\") else (mname, 0)
        elif j < n and tex[j] == "\\":
            mname, j = read_name(tex, j)
        else:
            i = j
            continue
        j = _skip_ws(tex, j)
        nargs, opt = 0, None
        if j < n and tex[j] == "[":
            num, j = read_bracket(tex, j)
            if num.strip().isdigit():
                nargs = int(num.strip())
            j = _skip_ws(tex, j)
            if j < n and tex[j] == "[":
                opt, j = read_bracket(tex, j)
        j = _skip_ws(tex, j)
        if j >= n or tex[j] != "{":
            i = max(j, i + 1)
            continue
        body, j = read_braced(tex, j)
        if mname:
            if opt is not None and nargs:
                macros[mname] = {"n": nargs - 1, "opt": opt, "body": body}
            else:
                macros[mname] = {"n": nargs, "opt": None, "body": body}
        i = j
    return macros


def _resolve_spec(spec, macros, seen):
    """Follow \\let aliases to the command that actually has arguments."""
    alias = spec.get("let")
    if not alias or alias in seen:
        return spec
    target = macros.get(alias)
    if not target:
        return spec
    return _resolve_spec(target, macros, seen | {alias})


def _take_arg(tex, k):
    """One undelimited argument. Braces, or a single token when the author omitted them.

    Returns (value, index, ok). Alignment tokens are left alone so a failed
    expansion keeps the original command.
    """
    k = _skip_ws(tex, k)
    if k >= len(tex):
        return None, k, False
    if tex[k] == "{":
        val, k = read_braced(tex, k)
        return val, k, True
    if tex.startswith("\\\\", k) or tex[k] in "&$":
        return None, k, False
    if tex[k] == "\\":
        _name, k2 = read_name(tex, k)
        return tex[k:k2], k2, True
    if tex[k] in " \t\r\n[]{}":
        return None, k, False
    return tex[k], k + 1, True


def _subst(body, args):
    out = []
    i = 0
    while i < len(body):
        if body[i] == "#" and i + 1 < len(body) and body[i + 1].isdigit():
            k = int(body[i + 1])
            out.append(args[k - 1] if 1 <= k <= len(args) else "")
            i += 2
            continue
        if body[i] == "#" and i + 1 < len(body) and body[i + 1] == "#":
            out.append("#")
            i += 2
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


_ACCENTS = {
    "hat", "bar", "tilde", "dot", "ddot", "vec", "breve", "check",
    "acute", "grave", "mathring", "widehat", "widetilde", "overline", "underline",
}


def _prev_command(tex: str, i: int) -> str:
    j = i - 1
    while j >= 0 and tex[j] in " \t\r\n":
        j -= 1
    if j < 0 or not tex[j].isalpha():
        return ""
    end = j + 1
    while j >= 0 and tex[j].isalpha():
        j -= 1
    if j >= 0 and tex[j] == "\\":
        return tex[j + 1:end]
    return ""


def _finish_repl(repl: str, nxt: str, accent: bool) -> str:
    """Brace a grouped replacement after an accent, and keep a control word from swallowing the next letter."""
    if accent and "{" in repl and not (repl.startswith("{") and repl.endswith("}")):
        repl = "{" + repl + "}"
    if nxt.isalpha() and repl:
        k = len(repl) - 1
        if repl[k].isalpha():
            while k >= 0 and repl[k].isalpha():
                k -= 1
            if k >= 0 and repl[k] == "\\":
                repl += " "
    return repl


def expand_math(tex: str, macros: dict, rounds: int = 12) -> str:
    """Expand author macros inside a math span. Unknown commands stay put."""
    if not macros or not tex:
        return tex
    for _ in range(rounds):
        out = []
        i, n = 0, len(tex)
        changed = False
        while i < n:
            if tex[i] != "\\":
                out.append(tex[i])
                i += 1
                continue
            name, j = read_name(tex, i)
            spec = macros.get(name)
            if not spec:
                out.append(tex[i:j])
                i = j
                continue
            spec = _resolve_spec(spec, macros, {name})
            k = _skip_ws(tex, j)
            args = []
            ok = True
            if spec["opt"] is not None:
                if k < n and tex[k] == "[":
                    val, k = read_bracket(tex, k)
                    args.append(val)
                else:
                    args.append(spec["opt"])
            for _a in range(spec["n"]):
                val, k, took = _take_arg(tex, k)
                if not took:
                    ok = False
                    break
                args.append(val)
            if not ok:
                out.append(tex[i:j])
                i = j
                continue
            repl = _subst(spec["body"], args)
            nxt = tex[k] if k < n else ""
            repl = _finish_repl(repl, nxt, _prev_command(tex, i) in _ACCENTS)
            out.append(repl)
            changed = True
            i = k
        tex = "".join(out)
        if not changed:
            break
    return tex


def _resolve_tex(root: Path, name: str) -> Path | None:
    name = name.strip().strip("{}")
    if not name or name.endswith((".pdf", ".png", ".jpg", ".jpeg", ".eps")):
        return None
    rel = Path(name)
    cands = [root / rel, root / (name + ".tex")]
    if rel.suffix != ".tex":
        cands.append(root / (name + ".tex"))
    for c in cands:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    matches = [p for p in root.rglob(rel.name if rel.suffix else rel.name + ".tex") if p.is_file()]
    if not rel.suffix:
        matches += [p for p in root.rglob(rel.name + ".tex") if p.is_file()]
    return matches[0].resolve() if matches else None



def inline_tree(main: Path, root: Path | None = None) -> str:
    """Inline \\input/\\include. Paths resolve against the including file and the e-print root."""
    root = root or main.parent
    tex = strip_comments(main.read_text(encoding="utf-8", errors="replace"))
    return _inline_from(tex, main.parent, root, {main.resolve()}, 0)


def _inline_from(tex, here: Path, root: Path, seen: set, depth: int) -> str:
    if depth > 40:
        return tex
    out = []
    i, n = 0, len(tex)
    pat = re.compile(r"\\(input|include|subfile)\b")
    while i < n:
        m = pat.search(tex, i)
        if not m:
            out.append(tex[i:])
            break
        out.append(tex[i:m.start()])
        j = m.end()
        if j < n and tex[j] == "*":
            j += 1
        j = _skip_ws(tex, j)
        if j < n and tex[j] == "{":
            arg, end = read_braced(tex, j)
        else:
            k = j
            while k < n and tex[k] not in " \t\r\n\\{}%":
                k += 1
            arg, end = tex[j:k], k
        path = _resolve_tex(here, arg) or _resolve_tex(root, arg)
        if path is None or path in seen:
            out.append(tex[m.start():end])
        else:
            seen.add(path)
            inner = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
            out.append(_inline_from(inner, path.parent, root, seen, depth + 1))
        i = end
    return "".join(out)


def _body(tex: str) -> str:
    a = tex.find("\\begin{document}")
    b = tex.rfind("\\end{document}")
    if a < 0:
        return tex
    a += len("\\begin{document}")
    return tex[a:b if b > a else len(tex)]


def is_pdfpages_wrapper(tex: str) -> bool:
    """True when the e-print only includes a PDF (Adam) and has no real TeX body."""
    if "\\includepdf" not in tex:
        return False
    body = _body(tex)
    if re.search(r"\\begin\{(equation|align|alignat|eqnarray|gather|multline|flalign|displaymath|dmath)\*?", body):
        return False
    if "$$" in body or "\\[" in body:
        return False
    stripped = re.sub(r"\\includepdf(\[[^\]]*\])?\{[^}]*\}", " ", body)
    stripped = re.sub(r"\\[A-Za-z@]+(\[[^\]]*\])?(\{[^{}]*\})*", " ", stripped)
    words = re.findall(r"[A-Za-z]{2,}", stripped)
    return len(words) < 40


def find_main_tex(root: Path) -> Path | None:
    tex = [p for p in root.rglob("*.tex") if p.is_file() and not any(s in p.parts for s in _SKIP_FILES)]
    if not tex:
        return None
    readme = None
    for name in ("00README.XXX", "00README.xxx"):
        hits = list(root.rglob(name))
        if hits:
            readme = hits[0]
            break
    if readme:
        text = readme.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line.endswith(".tex"):
                cand = _resolve_tex(root, line.split()[-1])
                if cand:
                    return cand
    docs = []
    for p in tex:
        t = p.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in t and "\\begin{document}" in t:
            docs.append((t.count("\\input") + t.count("\\include"), p.stat().st_size, p))
    if docs:
        docs.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return docs[0][2]
    tex.sort(key=lambda p: p.stat().st_size, reverse=True)
    return tex[0]


def _sty_macros(root: Path) -> dict:
    macros = {}
    files = list(root.rglob("*.sty"))[:40] + list(root.rglob("*.def"))[:40]
    for p in files:
        try:
            macros.update(collect_macros(strip_comments(p.read_text(encoding="utf-8", errors="replace"))))
        except OSError:
            continue
    return macros


def _labels(tex: str) -> tuple[str, list[str]]:
    labs = re.findall(r"\\label\{([^}]+)\}", tex)
    return re.sub(r"\\label\{[^}]+\}", "", tex), labs

