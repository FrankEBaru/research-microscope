"""Filas de preámbulo (título, autores, afiliación, keywords, abstract vacío).

Precisión sobre recall: un párrafo, una ecuación o una definición se quedan.
Una fila se descarta solo si, fuera de esas macros, casi no queda prosa.
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
}

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
_WORDS = re.compile(r"[A-Za-z]{2,}")

# Prosa fuera de las macros. Por debajo de esto, la fila es la portada.
_KEEP_WORDS = 6
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
    while True:
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == "[":
            i = _consume_until(s, i, "[", "]")
            continue
        if i < len(s) and s[i] == "{":
            i = _consume_until(s, i, "{", "}")
            continue
        return i


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
