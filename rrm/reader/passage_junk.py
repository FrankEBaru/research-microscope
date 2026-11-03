"""Filas de preámbulo (título, autores, afiliación, keywords, abstract vacío).

Precisión sobre recall: un párrafo, una ecuación o una definición se quedan.
Una fila se descarta solo si, fuera de esas macros, casi no queda prosa.
`\\footnotetext`, `\\blfootnote` y `\\thanks` se quedan desde 5 palabras,
también en cirílico. `\\newcommand` sigue en 6. Un `\\begin{def}` es una
definición. Un `\\twocolumn` con `\\captionof` en prosa se queda. `\\titlepage`,
`\\titlenote`, `\\authorcontributions`, `\\newtheorem` y un `\\def` de preámbulo no.
`RRM_PASSAGES_FILTER_JUNK=0` (también `false`, `off`, `no`) lo apaga.
Sin variable, o vacía, el filtro queda prendido.
"""

import os
import re

_OFF = {"0", "false", "off", "no"}

# Comandos de portada. Un párrafo que solo los envuelve no es un pasaje.
_EXACT = {
    "title", "author", "authors", "date", "thanks", "maketitle",
    "affiliation", "affiliations", "institute", "institutes", "institution",
    "email", "keywords", "keyword", "homepage",
    "correspondingauthor", "equalcontribution", "equalcontrib",
    "documentclass", "usepackage", "hypersetup", "requirepackage",
    "newcommand", "renewcommand", "providecommand", "def",
    "declaremathoperator", "declarerobustcommand",
    "bibliography", "bibliographystyle", "thispagestyle", "pagestyle",
    "address", "footnotetext", "blfootnote",
    "titlerunning", "authorrunning", "affil", "frontmatter", "markboth",
    "runtitle", "authornote",
    "onecolumn", "twocolumn", "vskip",
    "printaffiliationsandnotice", "printaffiliations",
    "icmlcorrespondingauthor",
    "titlepage", "titlenote", "authorcontributions", "newtheorem",
}

# El cuerpo es prosa, no la portada. La nota al pie basta con 5 palabras;
# \newcommand corto (una macro) sigue siendo preámbulo y pide 6.
_BODY_KEEP = {"footnotetext", "blfootnote", "thanks", "newcommand"}
_FOOTNOTE = {"footnotetext", "blfootnote", "thanks"}

# Clases de conferencia: \icmlaffiliation, \icmlkeywords, \iclrfinalcopy, ...
_PREFIXES = (
    "icml", "neurips", "nips", "aaai", "ijcai", "emnlp", "naacl", "eacl",
    "colm", "tmlr", "cvpr", "iccv", "eccv", "iclr", "aistats", "uai", "kdd",
    "sigir", "wacv", "bmvc", "corl", "icra", "coling", "acml",
)

_KEYWORD_ENVS = {"keywords", "keyword", "ieeekeywords"}

_PLACE = frozenset({
    "yyy", "xxx", "zzz", "tbd", "todo", "fixme", "lorem", "ipsum",
    "placeholder", "redacted",
})

# Ecuación de verdad. Un `=` o un `_` sueltos no cuentan: salen en afiliaciones.
_MATH = re.compile(
    r"\\(?:frac|tfrac|dfrac|sum|prod|int|sqrt|left|right|mathrm|mathbf|mathbb|"
    r"boldsymbol|alpha|beta|gamma|delta|epsilon|theta|lambda|sigma|mu|pi|phi|"
    r"omega|cdot|times|leq|geq|neq|approx|infty|partial|nabla|"
    r"begin\{(?:equation|align|gather|multline|eqnarray|aligned|split)\*?)"
    r"|\\\(|\\\[|\$\$|(?<!\\)\$"
)

_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
# Letras de cualquier alfabeto. El cirílico del libro 2106.01946 también cuenta.
_WORDS = re.compile(r"[^\W\d_]{2,}")
_TITLE_CMD = re.compile(r"\\[A-Za-z]*title\b", re.I)

# Prosa fuera de las macros. Por debajo de esto, la fila es la portada.
_KEEP_WORDS = 6
_FOOTNOTE_WORDS = 5
# Un abstract con menos palabras y sin matemática es un stub, no el resumen.
_STUB_WORDS = 4


def junk_filter_enabled():
    raw = os.environ.get("RRM_PASSAGES_FILTER_JUNK")
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _OFF


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(bit) for bit in value)
    return str(value)


def _is_front(name):
    if name in _EXACT:
        return True
    return any(name.startswith(prefix) and len(name) > len(prefix) for prefix in _PREFIXES)


def _skip_ws(s, i):
    n = len(s)
    while i < n and s[i] in " \t\r\n":
        i += 1
    return i


def _consume_until(s, i, open_ch, close_ch):
    """Grupo delimitado. Los escapes no cambian la profundidad."""
    if i >= len(s) or s[i] != open_ch:
        return i
    depth = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            i += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _skip_args(s, i):
    """`[opt]` y grupos `{...}` pegados al comando. No se come el texto de después."""
    end, _groups = _read_groups(s, i)
    return end


def _read_groups(s, i):
    """Grupos `{...}` del comando. El `*` de `\\newcommand*` no es un grupo."""
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == "*":
        i += 1
    groups = []
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == "[":
            i = _consume_until(s, i, "[", "]")
            continue
        if i < len(s) and s[i] == "{":
            end = _consume_until(s, i, "{", "}")
            groups.append(s[i + 1:end - 1] if end > i else "")
            i = end
            continue
        return i, groups


def _find_end(s, start, env):
    pattern = re.compile(r"\\(begin|end)\s*\{([^}]*)\}", re.I)
    depth = 1
    for match in pattern.finditer(s, start):
        name = match.group(2).strip().lower()
        if name != env:
            continue
        if match.group(1).lower() == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.start(), match.end()
    return len(s), len(s)


def _real_words(text):
    return [word for word in _WORDS.findall(text or "") if word.lower() not in _PLACE]


def _looks_like_math(text):
    return bool(_MATH.search(text or ""))


def _stub(body):
    if _looks_like_math(body):
        return False
    return len(_real_words(body)) < _STUB_WORDS


def _read_env(s, i):
    """i está justo después de `\\begin`. Devuelve (siguiente, entorno, cuerpo)."""
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == "[":
        i = _consume_until(s, i, "[", "]")
        i = _skip_ws(s, i)
    if i >= len(s) or s[i] != "{":
        return i, "", ""
    end = _consume_until(s, i, "{", "}")
    env = s[i + 1:end - 1].strip().lower() if end > i else ""
    body_end, next_i = _find_end(s, end, env)
    return next_i, env, s[end:body_end]


def _optional_bracket(s, i):
    """Texto dentro del `[...]` pegado al comando. None si no hay."""
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == "*":
        i += 1
        i = _skip_ws(s, i)
    if i >= len(s) or s[i] != "[":
        return i, None
    end = _consume_until(s, i, "[", "]")
    return end, s[i + 1:end - 1]


def _caption_words(chunk):
    """Palabras del `\\caption` o `\\captionof{tipo}{...}`."""
    found = []
    i = 0
    n = len(chunk or "")
    while i < n:
        if chunk[i] == "\\" and i + 1 < n and chunk[i + 1].isalpha():
            j = i + 1
            while j < n and (chunk[j].isalpha() or chunk[j] == "@"):
                j += 1
            name = chunk[i + 1:j].lower()
            if name in {"caption", "captionof"}:
                end, groups = _read_groups(chunk, j)
                body = ""
                if name == "captionof" and len(groups) >= 2:
                    body = groups[-1]
                elif groups:
                    body = groups[0]
                found.extend(_real_words(body))
                i = end
                continue
            i = j
            continue
        i += 1
    return found


def _skip_tex_def(s, i):
    """Después de `\\def`: el nombre, el texto de parámetros y el `{cuerpo}`."""
    i = _skip_ws(s, i)
    if i >= len(s) or s[i] != "\\":
        return i
    i += 1
    if i < len(s) and (s[i].isalpha() or s[i] == "@"):
        while i < len(s) and (s[i].isalpha() or s[i] == "@"):
            i += 1
    elif i < len(s):
        i += 1
    guard = 0
    while i < len(s) and s[i] != "{" and guard < 40:
        if s[i] == "\\":
            return i
        if s[i] in "\n\r":
            nxt = _skip_ws(s, i)
            if nxt < len(s) and s[nxt] == "{":
                i = nxt
                break
            return i
        i += 1
        guard += 1
    if i < len(s) and s[i] == "{":
        i = _consume_until(s, i, "{", "}")
    return i


def _strip_front(text):
    """Quita macros de portada. Un abstract con prosa se deja; un stub no."""
    s = _COMMENT.sub(" ", text or "")
    out = []
    hits = 0
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n and s[i + 1].isalpha():
            j = i + 1
            while j < n and (s[j].isalpha() or s[j] == "@"):
                j += 1
            name = s[i + 1:j].lower()
            if name == "begin":
                nxt, env, body = _read_env(s, j)
                if env == "abstract":
                    if _stub(body):
                        hits += 1
                    else:
                        out.append(" ")
                        out.append(body)
                    i = nxt
                    continue
                if env == "def":
                    # Entorno de definición, no el \def del preámbulo.
                    out.append(" ")
                    out.append(body)
                    i = nxt
                    continue
                if env in _KEYWORD_ENVS or _is_front(env):
                    hits += 1
                    i = nxt
                    continue
                out.append(s[i:nxt] if nxt > i else s[i:j])
                i = nxt if nxt > i else j
                continue
            if name == "and":
                # Solo es separador de autores si ya hay otra macro de portada.
                if hits:
                    i = _skip_args(s, j)
                    continue
                out.append(s[i:j])
                i = j
                continue
            if name == "twocolumn":
                end, opt = _optional_bracket(s, j)
                if opt is not None and len(_caption_words(opt)) >= _FOOTNOTE_WORDS:
                    out.append(" ")
                    out.append(opt)
                else:
                    hits += 1
                i = end
                continue
            if name == "def":
                hits += 1
                i = _skip_tex_def(s, j)
                continue
            if name in _BODY_KEEP:
                i, groups = _read_groups(s, j)
                body = "\n".join(groups)
                # \title + \thanks es la portada, aunque el thanks sea largo.
                if name == "thanks" and _TITLE_CMD.search(s):
                    hits += 1
                    continue
                need = _FOOTNOTE_WORDS if name in _FOOTNOTE else _KEEP_WORDS
                if len(_real_words(body)) >= need:
                    out.append(" ")
                    out.append(body)
                else:
                    hits += 1
                continue
            if _is_front(name):
                hits += 1
                i = _skip_args(s, j)
                continue
            out.append(s[i:j])
            i = j
            continue
        out.append(s[i])
        i += 1
    return "".join(out), hits


def _placeholder_junk(text):
    words = _WORDS.findall(text or "")
    if not words or _looks_like_math(text):
        return False
    placeholders = [word for word in words if word.lower() in _PLACE]
    real = [word for word in words if word.lower() not in _PLACE]
    if not placeholders:
        return False
    return len(real) <= 2 and len(placeholders) >= len(real)


def is_junk_passage(text="", latex="", kind=""):
    """True si la fila es portada, no un pasaje.

    `kind=eq` con matemática en `latex` (o en `text`, si no hay latex) se queda,
    aunque el texto de alrededor sea una afiliación.
    """
    text = _as_text(text)
    latex = _as_text(latex)
    kind = str(kind or "").strip().lower()
    math_src = latex if latex.strip() else text
    if kind == "eq" and _looks_like_math(math_src):
        return False
    blob = text if not latex.strip() else f"{text}\n{latex}"
    if not blob.strip():
        return False
    leftover, hits = _strip_front(blob)
    if hits >= 1 and len(_real_words(leftover)) < _KEEP_WORDS:
        return True
    return _placeholder_junk(blob)


def filter_passage_rows(rows):
    """Las filas que no son portada, en el mismo orden. Con el flag apagado, todas."""
    if not junk_filter_enabled():
        return list(rows or [])
    kept = []
    for row in rows or []:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        if is_junk_passage(row.get("text"), row.get("latex"), row.get("kind")):
            continue
        kept.append(row)
    return kept
