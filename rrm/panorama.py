"""POST /panorama: the Panorama selection step, SIMULATED. No model, no network, no Meta.

Port of apps/reader/src/lib/musesim.js. Same contract the real model would have:

    in   {"question": str, "ids": [corpusid, ...]}
    out  [{"id": "t0", "statement": str,
           "selections": [{"paper": "<corpusid>", "quote": str}]}]

A quote is a sentence copied from the paper's own `blocks[].sents`. This module
never writes new text, and it is not a gate: the UI (`validateSelections`)
rejects every quote that does not occur exactly once in its paper.

`RRM_PANORAMA_MODE=sim` (default) picks sentences by term overlap. `meta` is
the future model call and raises NotImplementedError; see `meta_panorama`.
"""

import os
import re
import unicodedata

MODES = ("sim", "meta")
MAX_IDS = 20
MAX_QUESTION = 500

_STOP = set(
    "funciona funcionan sirve sirven afecta afectan significa como cual cuales cuando donde porque para pero "
    "esta este esto estos estas sobre entre desde hasta cada todo toda todos todas puede pueden hace hacen "
    "tiene tienen segun sino mucho muchos which what when where does that this with from their there about "
    "between into than then them they have been were will would could should also more most such only over "
    "other what how why the and for are but not you your can".split()
)
_DOMAIN = set(
    "transformer model models modelo modelos language lenguaje network networks learning training paper papers "
    "method methods using used show shows results data large work approach self long handle replace replaces "
    "does make makes better best new use handles transformers sequences sequence neural deep system systems "
    "task tasks performance improve improves improvement mejora mejores usar usan".split()
)
_GLOSS = {
    "atencion": "attention", "escalado": "scaling", "escala": "scaling", "leyes": "laws", "ley": "law",
    "modelos": "models", "modelo": "model", "lenguaje": "language", "entrenamiento": "training",
    "datos": "data", "computo": "compute", "parametros": "parameters", "traduccion": "translation",
    "imagenes": "image", "imagen": "image", "vision": "vision", "redes": "network", "neuronales": "neural",
    "transformadores": "transformer", "perdida": "loss", "rendimiento": "performance", "memoria": "memory",
    "recuperacion": "retrieval", "razonamiento": "reasoning", "preentrenamiento": "pretraining",
    "aprendizaje": "learning", "secuencia": "sequence", "costo": "cost", "eficiencia": "efficiency",
    "secuencias": "sequence", "mejora": "improve", "mejores": "better", "tamano": "size",
}
_MARKS = re.compile("[̀-ͯ]")
_NOT_WORD = re.compile(r"[^a-z0-9]+")


def plain(s: str) -> str:
    return _MARKS.sub("", unicodedata.normalize("NFD", s.lower()))


def inline_text(inls) -> str:
    """Same reading as `text()` in apps/reader/src/lib/muse.js, which `validateSelections` uses."""
    out = []
    for x in inls or []:
        t = x.get("t")
        if t == "text":
            out.append(x.get("v") or "")
        elif t == "math":
            out.append(f"${x.get('v') or ''}$")
        elif t in ("cite", "note"):
            continue
        elif isinstance(x.get("c"), list):
            out.append(inline_text(x["c"]))
        else:
            out.append(str(x.get("v") or ""))
    return "".join(out)


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def themes_of(question: str, strict: bool = True) -> list[dict]:
    """Up to 4 content terms of the question. `stems` are prefixes matched against paper words."""
    q = str(question or "")
    seen, out = set(), []
    for w in re.split(r"[^a-z0-9-]+", plain(q)):
        if "-" in w:
            w = sorted(w.split("-"), key=len, reverse=True)[0]
        if len(w) < 4 or w in _STOP or (strict and w in _DOMAIN) or w in seen:
            continue
        seen.add(w)
        pat = "[̀-ͯ]*".join(re.escape(c) for c in w)
        m = re.search(pat, unicodedata.normalize("NFD", q), flags=re.I)
        orig = unicodedata.normalize("NFC", m.group(0)) if m else w
        stems = list(dict.fromkeys(x[: min(len(x), 6)] for x in (w, _GLOSS.get(w)) if x))
        out.append({"id": f"t{len(out)}", "term": orig, "stems": stems})
        if len(out) == 4:
            break
    return out if out or not strict else themes_of(question, False)


def _sentences(doc: dict) -> list[dict]:
    out = []
    for b in (doc or {}).get("blocks") or []:
        if b.get("kind") != "p":
            continue
        parts = b.get("sents") or [b.get("inlines")]
        for s in parts:
            t = _squash(inline_text(s))
            if 50 <= len(t) <= 420 and t.count("$") <= 4:
                out.append({"t": t, "abs": bool(b.get("abs"))})
    count: dict[str, int] = {}
    for s in out:
        count[s["t"]] = count.get(s["t"], 0) + 1
    return [s for s in out if count[s["t"]] == 1]


def _words(t: str) -> list[str]:
    return _NOT_WORD.split(plain(t))


def _hits(t: str, th: dict) -> bool:
    ws = _words(t)
    return any(w.startswith(st) for st in th["stems"] for w in ws)


def simulate_paper(themes: list[dict], paper_id: str, doc: dict) -> list[dict]:
    """The best sentence per theme. A sentence is not shared between themes."""
    sents, sel, used = _sentences(doc), [], set()

    def tf(t, th):
        return sum(1 for w in _words(t) if w and any(w.startswith(st) for st in th["stems"]))

    for th in themes:
        best, bs = None, 0.0
        for s in sents:
            if s["t"] in used:
                continue
            own = tf(s["t"], th)
            if not own:
                continue
            sc = (
                own
                + 0.4 * sum(1 for o in themes if o is not th and _hits(s["t"], o))
                + (0.6 if s["abs"] else 0)
                + (0.3 if 70 <= len(s["t"]) <= 260 else 0)
            )
            if sc > bs:
                bs, best = sc, s
        if best:
            used.add(best["t"])
            sel.append({"theme": th["id"], "paper": paper_id, "quote": best["t"]})
    return sel


def assemble(themes: list[dict], per_paper: dict) -> list[dict]:
    allsel = [s for sels in per_paper.values() for s in sels]
    return [
        {
            "id": th["id"],
            "statement": f"Lo que dicen los papers sobre «{th['term']}»",
            "selections": [
                {"paper": s["paper"], "quote": s["quote"]} for s in allsel if s["theme"] == th["id"]
            ],
        }
        for th in themes
    ]


def sim_panorama(question: str, docs: dict) -> list[dict]:
    """`docs` maps paper id (str) -> paper bundle, in the order the papers should be read. Ids with no doc add nothing."""
    themes = themes_of(question)
    return assemble(themes, {pid: simulate_paper(themes, pid, doc) for pid, doc in docs.items() if doc})


def meta_panorama(question: str, docs: dict) -> list[dict]:
    """Contract for the real model call (needs Franklin's explicit permission; not implemented).

    The model receives the question and the full text of each paper, and must
    return only selections: `[{id, statement, selections: [{paper, quote}]}]`,
    where every `quote` is copied from that paper. The statement may be written
    by the model. The UI gate rejects any quote that is not found exactly once.
    """
    raise NotImplementedError("RRM_PANORAMA_MODE=meta is not implemented; it needs explicit permission to call Meta")


def mode() -> str:
    m = (os.environ.get("RRM_PANORAMA_MODE") or "sim").strip().lower()
    if m not in MODES:
        raise ValueError(f"RRM_PANORAMA_MODE must be one of {MODES}, got {m!r}")
    return m


def parse_request(item) -> tuple[str, list[str]]:
    """Validate the POST body. Ids come back as digit strings, deduplicated, in request order."""
    if not isinstance(item, dict):
        raise ValueError("body must be a JSON object")
    question = item.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if len(question) > MAX_QUESTION:
        raise ValueError(f"question is longer than {MAX_QUESTION} characters")
    raw = item.get("ids")
    if not isinstance(raw, list) or not raw:
        raise ValueError("ids must be a non-empty list")
    if len(raw) > MAX_IDS:
        raise ValueError(f"at most {MAX_IDS} ids")
    ids = []
    for x in raw:
        s = str(x)
        if isinstance(x, bool) or not s.isdigit():
            raise ValueError("ids must be corpus ids (digits)")
        s = str(int(s))
        if s not in ids:
            ids.append(s)
    return question.strip(), ids


READABLE = ("done", "abstract_only")


def docs_for(papers_root, ids, load_meta, load_paper) -> dict:
    """Bundles already on the volume. Reads only: a paper not yet done or abstract_only maps to None and is never spawned."""
    from pathlib import Path

    docs = {}
    for pid in ids:
        folder = Path(papers_root) / pid
        meta = load_meta(folder)
        docs[pid] = load_paper(folder) if meta and meta.get("status") in READABLE else None
    return docs


def run(question: str, docs: dict) -> list[dict]:
    return meta_panorama(question, docs) if mode() == "meta" else sim_panorama(question, docs)
