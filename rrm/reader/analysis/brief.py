"""Brief del paper: programático, al abrir, $0 de Meta.

`build_brief(paper)` recibe el `paper.json` del lector y devuelve un dict
(esquema en compass `notas/RRM-99-brief.md`, versión `BRIEF_VERSION`). No llama
a la red. Los vecinos en la base de pasajes van aparte (`retrieve.py`), porque
cargan SPECTER2 y el índice FAISS.

Punteros:
- oración: `"<block>#<sent>"` (p. ej. `b25#2`), mismo corte que la UI (`block.sents`).
- ecuación, figura, tabla: el id del bloque (`b26`).
"""

from __future__ import annotations

import hashlib
import json
import re
import time

BRIEF_VERSION = "rrm99-brief/1"

# ---------------------------------------------------------------- texto


def _text(nodes, math=True):
    """Texto de una lista de inlines. Math como `$…$`; citas como `[n]`; notas fuera."""
    out = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        t = node.get("t")
        if t in ("text", "code"):
            out.append(str(node.get("v") or ""))
        elif t == "math":
            v = str(node.get("v") or "")
            if v:
                out.append(f"${v}$" if math else v)
        elif t in ("em", "strong", "span", "link"):
            out.append(_text(node.get("c"), math))
        elif t == "cite":
            out.append("[" + ",".join(node.get("keys") or []) + "]")
        elif t == "ref":
            out.append(str(node.get("number") or node.get("label") or ""))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _walk(nodes):
    for node in nodes or []:
        if isinstance(node, dict):
            yield node
            yield from _walk(node.get("c"))


def _notes_text(nodes):
    bits = []
    for node in _walk(nodes):
        if node.get("t") == "note":
            for sub in node.get("blocks") or []:
                bits.append(_text(sub.get("inlines")))
    return " ".join(b for b in bits if b)


def _sents_of(block):
    sents = block.get("sents")
    if sents:
        return sents
    if block.get("inlines"):
        return [block["inlines"]]
    return []


# ---------------------------------------------------------------- secciones

_ROLES = (
    ("abstract", ("abstract",)),
    ("intro", ("introduc",)),
    ("related", ("related", "background", "prior work", "preliminar")),
    ("conclusion", ("conclusion", "discussion", "limitation", "future work", "summary")),
    ("results", ("result", "experiment", "evaluation", "ablation", "analysis", "benchmark")),
    ("method", ("method", "approach", "model", "architecture", "algorithm", "training", "theor", "derivation", "objective", "framework")),
    ("appendix", ("appendix", "supplement", "proof")),
)
_REFS = re.compile(r"^\s*(references?|bibliography|acknowledg\w*)\b", re.I)


def _role(title, appendix):
    low = (title or "").lower()
    if _REFS.search(low):
        return "refs"
    if appendix:
        return "appendix"
    for role, keys in _ROLES:
        if any(k in low for k in keys):
            return role
    return "other"


# ---------------------------------------------------------------- símbolos

_SKIP_CMDS = {
    "\\frac", "\\tfrac", "\\dfrac", "\\sqrt", "\\left", "\\right", "\\mathrm", "\\text", "\\mathbf", "\\mathcal",
    "\\mathbb", "\\operatorname", "\\mathit", "\\boldsymbol", "\\bm", "\\cdot", "\\cdots", "\\ldots", "\\dots",
    "\\in", "\\le", "\\leq", "\\ge", "\\geq", "\\approx", "\\sim", "\\times", "\\top", "\\quad", "\\qquad",
    "\\begin", "\\end", "\\label", "\\nonumber", "\\big", "\\Big", "\\bigg", "\\Bigg", "\\hat", "\\tilde", "\\bar",
    "\\overline", "\\underline", "\\mid", "\\to", "\\rightarrow", "\\leftarrow", "\\infty", "\\partial", "\\nabla",
    "\\sum", "\\prod", "\\int", "\\log", "\\exp", "\\max", "\\min", "\\arg", "\\sin", "\\cos", "\\lim", "\\sup",
    "\\inf", "\\det", "\\tag", "\\displaystyle", "\\limits", "\\left(", "\\right)", "\\mathsf", "\\textrm", "\\textbf",
    "\\emph", "\\textit", "\\vec", "\\langle", "\\rangle", "\\lVert", "\\rVert", "\\|", "\\prime", "\\neq", "\\ne",
    "\\pm", "\\mp", "\\equiv", "\\propto", "\\forall", "\\exists", "\\cup", "\\cap", "\\subset", "\\subseteq",
    "\\mathds", "\\notag", "\\hspace", "\\vspace", "\\nolimits", "\\ell", "\\circ", "\\odot", "\\otimes", "\\oplus",
    "\\cdotp", "\\colon", "\\triangleq", "\\coloneqq", "\\defeq", "\\leftarrow", "\\Rightarrow", "\\iff", "\\implies",
    "\\lfloor", "\\rfloor", "\\lceil", "\\rceil", "\\mathop", "\\stackrel", "\\overset", "\\underset", "\\substack",
    "\\textsc", "\\texttt", "\\mathtt", "\\scriptstyle", "\\scriptscriptstyle", "\\textstyle", "\\phantom",
}
_GREEK = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega",
}


def _norm(tex):
    text = tex or ""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\\(?:text|mathrm|mathit|operatorname|mathbf|boldsymbol|bm|textrm|mathsf)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:mathbb|mathds|mathcal)\{[A-Za-z]\}", "", text)  # \mathbb{E}, \mathbb{R}: operadores
    text = re.sub(r"_\{([^{}]+)\}", lambda m: "_" + re.sub(r"\s+", "", m.group(1)), text)
    text = re.sub(r"\^\{([^{}]+)\}", lambda m: "^" + re.sub(r"\s+", "", m.group(1)), text)
    return text


_SYM = re.compile(
    r"\\([A-Za-z]+)(?:_(?:[A-Za-z0-9]+|\\[A-Za-z]+))?"  # \beta, \pi_\theta, \pi_{ref}
    r"|(?<![A-Za-z\\])([A-Za-z])_([A-Za-z0-9]+|\\[A-Za-z]+)"  # d_k, W_i, x_{t}
    r"|(?<![A-Za-z\\^_])([A-Za-z])(?![A-Za-z_])"  # Q, K, V, N, D (no W^O ni K^T)
)


def symbols_in(tex):
    """Símbolos de una expresión: griegas, letras con subíndice y letras sueltas."""
    found = []
    flat = _norm(tex)
    for m in _SYM.finditer(flat):
        whole = m.group(0)
        if m.group(1):
            name = m.group(1)
            if name not in _GREEK:
                continue
        elif m.group(4):
            # Letra suelta: sólo mayúsculas o letras griegas cuentan; x, i, j son índices.
            if not m.group(4).isupper():
                continue
        found.append(re.sub(r"\s+", "", whole))
    out = []
    for sym in found:
        if sym not in out:
            out.append(sym)
    return out


_DEF_CUE = re.compile(
    r"\b(denot\w*|where|let|we (?:call|refer to|define|use)|is (?:the|a|an|defined)|are (?:the|defined)|represent\w*|"
    r"stands? for|of dimension|dimension(?:ality)?|refers? to|is called|called|is given by|correspond\w*)\b",
    re.I,
)


def _sym_hit(sym, sent):
    needle = sym.replace(" ", "")
    for blob in sent["math_norm"]:
        if needle == blob:
            return True
        if len(needle) > 1 and re.search(rf"(?<![A-Za-z]){re.escape(needle)}(?![A-Za-z0-9_])", blob):
            # d_k dentro de d_k^2: sí. \\pi dentro de \\pi_ref: no.
            return True
        if len(needle) == 1 and re.search(rf"(?<![A-Za-z\\_]){re.escape(needle)}(?![A-Za-z_])", blob):
            return True
    return False


def _explains(sent, sym):
    rest = sent["text"].replace(f"${sym}$", "")
    rest = re.sub(r"\$[^$]*\$", "", rest)
    return len(re.sub(r"[^A-Za-z]+", "", rest)) > 12


# ---------------------------------------------------------------- frases clave

CUES = {
    "claim": re.compile(
        r"\b(we (?:show|demonstrate|prove|find|observe|establish|achieve|obtain)|outperform\w*|state[- ]of[- ]the[- ]art|"
        r"surpass\w*|significantly (?:better|improv\w*|reduc\w*|faster)|new (?:state|record)|improv\w+ (?:by|over|upon)|"
        r"(?:\d+(?:\.\d+)?)\s?(?:%|×|x faster|times faster|BLEU))",
        re.I,
    ),
    "assumption": re.compile(r"\b(we assume|assum\w+ that|suppose|under the assumption|we hypothesi[sz]e|we suspect|we conjecture|we posit)\b", re.I),
    "easy": re.compile(
        r"\b(it is easy to see|easy to (?:show|verify|check)|clearly|obviously|trivially|it follows|straightforward\w*|"
        r"it can be shown|one can (?:show|verify|see)|is well[- ]known|well[- ]known|standard (?:result|technique|trick)|"
        r"note that|recall that|it is known|by definition|immediately)\b",
        re.I,
    ),
    "intuition": re.compile(
        r"\b(intuitively|in other words|the reason|this is because|because of this|to counteract|which allows|this allows|"
        r"the key (?:idea|insight)|the intuition|in effect|effectively|crucially|importantly)\b",
        re.I,
    ),
    "define": re.compile(r"\b(we (?:call|refer to|define|denote)|is defined as|denoted by|let \$|we use \$)", re.I),
    "contrast": re.compile(r"\b(unlike|in contrast|as opposed to|rather than|instead of|whereas)\b", re.I),
}


def _cue_hits(text):
    hits = []
    for kind, rx in CUES.items():
        m = rx.search(text)
        if m:
            hits.append((kind, m.group(0)))
    return hits


# ---------------------------------------------------------------- brief


def _hash(paper):
    blob = json.dumps(paper.get("blocks") or [], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_brief(paper, base_cids=None):
    """paper: el paper.json del lector. base_cids: corpusids presentes en la base de pasajes."""
    t0 = time.perf_counter()
    blocks = [b for b in (paper.get("blocks") or []) if isinstance(b, dict)]
    base_cids = set(int(c) for c in (base_cids or []))
    refs = paper.get("refs") or {}
    cite_map = paper.get("citeMap") or {}

    sections, sents, equations, figures = [], [], [], []
    by_block = {}
    sec_idx = -1
    appendix = False
    order = {}
    # Sección 0 implícita: abstract (bloques `abs`) o lo que va antes del primer encabezado.
    sections.append({"i": 0, "id": "", "title": "Abstract", "level": 1, "number": "", "role": "abstract", "blocks": []})
    sec_idx = 0
    for pos, block in enumerate(blocks):
        bid = str(block.get("id") or f"x{pos}")
        order[bid] = pos
        kind = block.get("kind")
        if kind == "h":
            title = _text(block.get("inlines"), math=False)
            low = title.lower()
            if "appendix" in low or (block.get("level") == 1 and re.match(r"^[A-Z]\b", str(block.get("number") or ""))):
                appendix = True
            level = int(block.get("level") or 1)
            role = _role(title, appendix)
            if level > 1 and role not in ("refs", "appendix"):
                # Una subsección hereda el papel de su sección (5.1 de «Theoretical Analysis» es método).
                parent = next((sec for sec in reversed(sections) if sec["level"] < level), None)
                if parent and parent["role"] not in ("other", "abstract"):
                    role = parent["role"]
            sec_idx = len(sections)
            sections.append({
                "i": sec_idx, "id": bid, "title": title, "level": level,
                "number": str(block.get("number") or ""), "role": role, "blocks": [],
            })
            continue
        sections[sec_idx]["blocks"].append(bid)
        by_block[bid] = block
        if kind == "p" and not block.get("raw"):
            for si, sent in enumerate(_sents_of(block)):
                text = _text(sent)
                if not text:
                    continue
                maths = [str(n.get("v") or "") for n in _walk(sent) if n.get("t") == "math" and n.get("v")]
                row = {
                    "id": f"{bid}#{si}", "block": bid, "sent": si, "sec": sec_idx, "text": text,
                    "math": maths, "math_norm": [re.sub(r"\s+", "", _norm(m)) for m in maths],
                    "cites": [k for n in _walk(sent) if n.get("t") == "cite" for k in (n.get("keys") or [])],
                    "refs": [str(n.get("target")) for n in _walk(sent) if n.get("t") == "ref" and n.get("target")],
                    "note": _notes_text(sent),
                    "em": [t for t in (_text(n.get("c"), math=False) for n in sent if isinstance(n, dict) and n.get("t") in ("em", "strong")) if 2 < len(t) < 60],
                }
                sents.append(row)
        elif kind == "eq":
            tex = str(block.get("tex") or "")
            equations.append({
                "id": bid, "number": block.get("number"), "label": block.get("label") or "", "tex": tex,
                "sec": sec_idx, "katex_ok": bool(block.get("katex_ok", True)), "symbols": symbols_in(tex),
                "math_norm": [re.sub(r"\s+", "", _norm(tex))],
            })
        elif kind in ("fig", "table"):
            figures.append({
                "id": bid, "kind": kind, "label": block.get("label") or "",
                "caption": _text(block.get("caption")), "sec": sec_idx, "cited_at": [],
            })
        elif kind == "list":
            for ii, item in enumerate(block.get("items") or []):
                inl = item if isinstance(item, list) else (item.get("inlines") if isinstance(item, dict) else [])
                text = _text(inl)
                if text:
                    maths = [str(n.get("v") or "") for n in _walk(inl) if n.get("t") == "math" and n.get("v")]
                    sents.append({
                        "id": f"{bid}#{ii}", "block": bid, "sent": ii, "sec": sec_idx, "text": text, "math": maths,
                        "math_norm": [re.sub(r"\s+", "", _norm(m)) for m in maths], "cites": [], "refs": [], "note": "",
                        "list": True,
                    })
    if not sections[0]["blocks"]:
        sections[0]["title"] = "Front"
    sid_index = {s["id"]: i for i, s in enumerate(sents)}

    # Ecuaciones: oración anterior/siguiente y quién las cita.
    first_sent_of_block = {}
    for i, s in enumerate(sents):
        first_sent_of_block.setdefault(s["block"], i)
    for eq in equations:
        pos = order[eq["id"]]
        prev = next((sents[sid_index[s["id"]]] for s in reversed(sents) if order[s["block"]] < pos), None)
        nxt = next((s for s in sents if order[s["block"]] > pos), None)
        eq["prev"] = prev["id"] if prev else ""
        eq["next"] = nxt["id"] if nxt else ""
        num = str(eq.get("number") or "")
        cited = []
        for s in sents:
            if eq["id"] in s["refs"] or (num and re.search(rf"\b(?:Eqs?\.?|Equations?|eq\.?)\s*\(?{re.escape(num)}\)?", s["text"])):
                cited.append(s["id"])
        eq["cited_at"] = cited[:6]

    # Figuras y tablas: dónde se citan.
    fig_by_id = {f["id"]: f for f in figures}
    for s in sents:
        for target in s["refs"]:
            if target in fig_by_id:
                fig_by_id[target]["cited_at"].append(s["id"])

    # Símbolos.
    counts = {}
    first = {}
    for s in sents:
        for blob in s["math"]:
            for sym in symbols_in(blob):
                counts[sym] = counts.get(sym, 0) + 1
                first.setdefault(sym, s["id"])
    for eq in equations:
        for sym in eq["symbols"]:
            counts[sym] = counts.get(sym, 0) + 1
            first.setdefault(sym, eq["id"])
    symbols = []
    for sym, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        hits = [s for s in sents if _sym_hit(sym, s)]
        eq_ids = [eq["id"] for eq in equations if sym in eq["symbols"]]
        defn, score = None, 0
        for s in hits:
            if not _explains(s, sym):
                continue
            sc = 1 + (2 if _DEF_CUE.search(s["text"]) else 0)
            # "where $d_k$ is…" justo después de la ecuación: definición fuerte.
            if re.search(rf"where\b[^.]*\${re.escape(sym)}\$", s["text"]) or re.search(rf"\${re.escape(sym)}\$\s*(?:is|are|denotes)\b", s["text"]):
                sc += 2
            if sc > score:
                defn, score = s["id"], sc
            if score >= 5:
                break
        symbols.append({
            "sym": sym, "uses": n, "first": first.get(sym, ""), "def": defn or "", "def_score": score,
            "defined": bool(defn) and score >= 3, "eqs": eq_ids[:8], "sents": [s["id"] for s in hits[:8]],
        })

    # Frases clave.
    cues = []
    for s in sents:
        for kind, match in _cue_hits(s["text"]):
            cues.append({"kind": kind, "sid": s["id"], "match": match})
        if any(t in fig_by_id for t in s["refs"]) or re.search(r"\b(Figure|Fig\.|Table)\s*\d", s["text"]):
            kinds = {fig_by_id[t]["kind"] for t in s["refs"] if t in fig_by_id}
            if not kinds:
                kinds = {"table" if "Table" in s["text"] else "fig"}
            for k in sorted(kinds):
                cues.append({"kind": "tabref" if k == "table" else "figref", "sid": s["id"], "match": ""})

    # Citas.
    cites = {}
    for s in sents:
        for key in s["cites"]:
            row = cites.setdefault(key, {"key": key, "corpusid": None, "ref": str(refs.get(key) or "")[:240], "in_base": False, "cited_at": []})
            if len(row["cited_at"]) < 8:
                row["cited_at"].append(s["id"])
    for key, row in cites.items():
        target = str(cite_map.get(key) or "")
        if target.startswith("s2:"):
            try:
                row["corpusid"] = int(target[3:])
            except ValueError:
                pass
        row["in_base"] = bool(row["corpusid"] and row["corpusid"] in base_cids)

    # Prerrequisitos (C3): símbolos sin definición y términos con cita que no se explican.
    prereqs = []
    for sym in symbols:
        if not sym["defined"] and sym["uses"] >= 2:
            prereqs.append({"kind": "symbol", "term": sym["sym"], "sid": sym["first"], "uses": sym["uses"]})
    for key, row in cites.items():
        # Término citado como algo sabido: "X [key]" en método o intro.
        for sid in row["cited_at"][:2]:
            s = sents[sid_index[sid]]
            m = re.search(r"([A-Za-z][\w\- ]{3,40}?)\s*\[" + re.escape(key), s["text"])
            if m and sections[s["sec"]]["role"] in ("method", "intro", "other", "related"):
                prereqs.append({"kind": "cited_term", "term": m.group(1).strip(), "sid": sid, "cite": key, "corpusid": row["corpusid"], "in_base": row["in_base"]})
                break

    def _public_sent(s):
        out = {k: s[k] for k in ("id", "block", "sent", "sec", "text") }
        if s["math"]:
            out["math"] = s["math"]
        if s["cites"]:
            out["cites"] = s["cites"]
        if s["refs"]:
            out["refs"] = s["refs"]
        if s.get("note"):
            out["note"] = s["note"]
        if s.get("list"):
            out["list"] = True
        if s.get("em"):
            out["em"] = s["em"]
        return out

    brief = {
        "v": BRIEF_VERSION,
        "paper": {
            "corpusid": paper.get("corpusid"), "arxiv": paper.get("arxivId") or "", "title": paper.get("title") or "",
            "license": paper.get("license") or "", "hash": _hash(paper), "n_blocks": len(blocks), "n_sents": len(sents),
            "abstract": str(paper.get("abstract") or "")[:2000],
        },
        "sections": [{k: v for k, v in sec.items() if k != "blocks"} | {"n_blocks": len(sec["blocks"]), "start": sec["blocks"][0] if sec["blocks"] else ""} for sec in sections],
        "sents": [_public_sent(s) for s in sents],
        "equations": [{k: v for k, v in eq.items() if k != "math_norm"} for eq in equations],
        "symbols": symbols,
        "cues": cues,
        "figures": figures,
        "cites": sorted(cites.values(), key=lambda r: -len(r["cited_at"])),
        "prereqs": prereqs,
        "neighbors": {},
        "timing": {"build_s": round(time.perf_counter() - t0, 3)},
    }
    return brief


# ---------------------------------------------------------------- utilidades para candidatos


class BriefIndex:
    """Acceso rápido por puntero. Lo usan candidatos y verificadores."""

    def __init__(self, brief):
        self.brief = brief
        self.sents = {s["id"]: s for s in brief["sents"]}
        self.order = [s["id"] for s in brief["sents"]]
        self.pos = {sid: i for i, sid in enumerate(self.order)}
        self.eqs = {e["id"]: e for e in brief["equations"]}
        self.figs = {f["id"]: f for f in brief["figures"]}
        self.secs = brief["sections"]

    def text(self, ptr):
        if ptr in self.sents:
            return self.sents[ptr]["text"]
        if ptr in self.eqs:
            return "$$" + self.eqs[ptr]["tex"] + "$$"
        if ptr in self.figs:
            return self.figs[ptr]["caption"]
        return ""

    def valid(self, ptr):
        return ptr in self.sents or ptr in self.eqs or ptr in self.figs

    def section_of(self, ptr):
        if ptr in self.sents:
            return self.sents[ptr]["sec"]
        if ptr in self.eqs:
            return self.eqs[ptr]["sec"]
        if ptr in self.figs:
            return self.figs[ptr]["sec"]
        return -1

    def window(self, sid, before=2, after=2):
        i = self.pos.get(sid)
        if i is None:
            return []
        return self.order[max(0, i - before): i + after + 1]

    def section_sents(self, sec):
        return [s for s in self.brief["sents"] if s["sec"] == sec]

    def render_section(self, sec, eqs=True, limit=None):
        """Sección con sus punteros, para el prompt. Ecuaciones intercaladas por orden de bloque."""
        lines = []
        rows = self.section_sents(sec)
        eq_rows = [e for e in self.brief["equations"] if e["sec"] == sec] if eqs else []
        # Orden por número de bloque.
        def key(ptr):
            m = re.match(r"b(\d+)(?:#(\d+))?", ptr)
            return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)
        items = [(key(s["id"]), f"[{s['id']}] {s['text']}") for s in rows]
        items += [(key(e["id"]), f"[{e['id']}] $${e['tex']}$$" + (f" ({e['number']})" if e.get("number") else "")) for e in eq_rows]
        items.sort()
        for _, line in items:
            lines.append(line)
        if limit:
            lines = lines[:limit]
        return "\n".join(lines)
