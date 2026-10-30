"""POST /panorama. `sim` picks sentences by term overlap. `meta` asks Muse.

Same contract either way:

    in   {"question": str, "ids": [corpusid, ...]}
    out  [{"id": "t0", "statement": str,
           "selections": [{"paper": "<corpusid>", "quote": str}]}]

A quote is a sentence copied from the paper's own `blocks[].sents`. This module
never writes a quote. The UI (`validateSelections`) still rejects every quote
that does not occur exactly once in its paper. `meta` checks that before
returning, and rebuilds each quote from a numbered candidate so the string is
the sentence itself.

`RRM_PANORAMA_MODE=sim` is the default (no model, no network). `meta` calls
Muse Spark through `rrm.search.split` (`muse-spark-1.3-contributor`). On
timeout, transport error, or invalid JSON it returns the `sim` selection and
sets `fallback` true. Each claim then also carries `mode` (`sim` or `meta`)
and `fallback` (bool). Those fields are how a caller tells the two apart.

`sim` stays the default. A demo that flipped to `meta` would spend Meta tokens
on every question. The browser waits `NEXT_PUBLIC_RRM_PANORAMA_TIMEOUT_MS`
(default 45s, `apps/reader/src/lib/backend.js`). The server timeout
(`RRM_PANORAMA_TIMEOUT`, default 40s, cap 45s) sits under that so a slow Muse
call still returns the sim fallback instead of a browser error.
"""

import json
import logging
import os
import re
import time
import unicodedata

MODES = ("sim", "meta")
MAX_IDS = 20
MAX_QUESTION = 500
# Numbered sentences sent to Muse. Round-robin across papers, then cut by chars.
MAX_CANDIDATES = 36
MAX_CANDIDATE_CHARS = 12000
# Developer text plus the candidate list. The HTTP body stays under this.
MAX_PROMPT_CHARS = 14000
# Under the UI's 45s /panorama timeout, so fallback still reaches the browser.
DEFAULT_TIMEOUT_S = 40.0
MAX_TIMEOUT_S = 45.0
MAX_THEMES = 4
MAX_PICKS = 8

log = logging.getLogger(__name__)

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


def block_text(b: dict) -> str:
    """Same reading as `blockText` in apps/reader/src/lib/muse.js."""
    if not isinstance(b, dict):
        return ""
    kind = b.get("kind")
    if kind in ("p", "h"):
        raw = inline_text(b.get("inlines"))
    elif kind == "eq":
        raw = f"${b.get('tex') or ''}$"
    elif kind == "list":
        raw = " ".join(inline_text(item) for item in (b.get("items") or []))
    else:
        raw = inline_text(b.get("caption"))
    return _squash(raw)


def quote_ok(doc: dict, quote: str) -> bool:
    """True when `quote` occurs in exactly one block, matching `validateSelections`.

    A sentence that also appears in the abstract is kept when the abstract is
    the only `abs` hit, which is the UI's rule for a repeated abstract sentence.
    """
    q = _squash(quote)
    if not q or not isinstance(doc, dict):
        return False
    hits = [b for b in (doc.get("blocks") or []) if isinstance(b, dict) and q in block_text(b)]
    if len(hits) > 1 and sum(1 for b in hits if b.get("abs")) == 1:
        hits = [b for b in hits if b.get("abs")]
    return len(hits) == 1


def _theme_score(text: str, themes: list[dict], abstract: bool) -> float:
    own = 0
    for th in themes:
        own += sum(1 for w in _words(text) if w and any(w.startswith(st) for st in th["stems"]))
    if themes and not own:
        return 0.0
    return own + (0.6 if abstract else 0.0) + (0.3 if 70 <= len(text) <= 260 else 0.0)


def candidate_sentences(question: str, docs: dict) -> tuple[list[dict], list[dict]]:
    """Themes plus numbered sentences, best-first within each paper, round-robin.

    A sentence must pass `_sentences` and hit `themes_of` when the question has
    themes. The quote text is the sentence; the caller does not ask the model
    to copy it.
    """
    themes = themes_of(question)
    per = []
    for pid, doc in docs.items():
        if not doc:
            continue
        ranked = []
        for sent in _sentences(doc):
            score = _theme_score(sent["t"], themes, sent["abs"])
            if themes and score <= 0:
                continue
            ranked.append((score, sent["t"]))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        per.append((str(pid), ranked))
    picked, chars = [], 0
    while len(picked) < MAX_CANDIDATES:
        moved = False
        for pid, ranked in per:
            if not ranked:
                continue
            score, text = ranked.pop(0)
            if picked and chars + len(text) > MAX_CANDIDATE_CHARS:
                return themes, picked
            picked.append({"paper": pid, "quote": text, "score": score})
            chars += len(text)
            moved = True
            if len(picked) >= MAX_CANDIDATES:
                break
        if not moved:
            break
    return themes, picked


_DEV = (
    "You group evidence for a research question. You receive numbered sentences "
    "copied from papers. You do not write, translate, or edit quotations. "
    'Reply as JSON {"themes":[{"statement":"...","picks":[0]}]}. '
    "Use 2 to 4 themes. Each statement is one sentence in the same language as "
    "the question and states a claim the chosen sentences support. "
    "Each pick is the index as a decimal string, such as \"0\". Use a sentence in only one theme."
)


def _prompt(question: str, candidates: list[dict]) -> str:
    lines = [f"Question: {_squash(question)}", "", "Sentences:"]
    for i, cand in enumerate(candidates):
        lines.append(f"{i}\t{cand['paper']}\t{cand['quote'].replace(chr(9), ' ')}")
    text = "\n".join(lines)
    if len(text) <= MAX_PROMPT_CHARS:
        return text
    kept = ["Question: " + _squash(question), "", "Sentences:"]
    for i, cand in enumerate(candidates):
        line = f"{i}\t{cand['paper']}\t{cand['quote'].replace(chr(9), ' ')}"
        trial = "\n".join(kept + [line])
        if len(trial) > MAX_PROMPT_CHARS and len(kept) > 3:
            break
        kept.append(line)
    return "\n".join(kept)


def _timeout_s() -> float:
    raw = (os.environ.get("RRM_PANORAMA_TIMEOUT") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    if value != value:  # NaN
        return DEFAULT_TIMEOUT_S
    return min(MAX_TIMEOUT_S, max(1.0, value))


def _ensure_log() -> None:
    """INFO goes to stderr even when the root logger is left at WARNING."""
    log.setLevel(logging.INFO)
    if any(getattr(handler, "rrm_panorama", False) for handler in log.handlers):
        return
    handler = logging.StreamHandler()
    handler.rrm_panorama = True
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    log.addHandler(handler)


def _redact(text: str) -> str:
    for name in ("MODEL_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "S2_API_KEY", "RRM_DEMO_TOKEN"):
        secret = os.environ.get(name) or ""
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    return text[:240]


def _log_usage(outcome: str, *, prompt_chars: int, candidates: int, usage, elapsed_s: float, kept: int, dropped: dict):
    usage = usage or {}

    def _num(key):
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value

    cost = _num("cost")
    if cost is None:
        cost = _num("cost_usd")
    log.info(
        "panorama_meta outcome=%s candidates=%s prompt_chars=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s cost=%s elapsed_s=%.3f kept=%s dropped_range=%s dropped_repeat=%s dropped_unmatched=%s",
        outcome,
        candidates,
        prompt_chars,
        _num("prompt_tokens"),
        _num("completion_tokens"),
        _num("total_tokens"),
        cost,
        elapsed_s,
        kept,
        dropped.get("range", 0),
        dropped.get("repeat", 0),
        dropped.get("unmatched", 0),
    )


def _tag(claims: list[dict], mode_name: str, fallback: bool, reason: str = "") -> list[dict]:
    out = []
    for claim in claims:
        row = {
            "id": claim["id"],
            "statement": claim["statement"],
            "selections": [{"paper": str(s["paper"]), "quote": s["quote"]} for s in claim.get("selections") or []],
            "mode": mode_name,
            "fallback": fallback,
        }
        if fallback and reason:
            row["fallback_reason"] = reason
        out.append(row)
    return out


def _fallback(question: str, docs: dict, reason: str, **log_kw) -> list[dict]:
    _log_usage(reason, **log_kw)
    return _tag(sim_panorama(question, docs), "sim", True, reason)


def _parse_themes(text: str) -> list:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict) or not isinstance(data.get("themes"), list):
        raise ValueError("themes")
    return data["themes"]


def _as_index(value):
    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _claims_from_picks(docs: dict, candidates: list[dict], themes: list) -> tuple[list[dict], dict]:
    """Rebuild quotes from indexes. Drop out-of-range, repeats, and quotes that are not unique."""
    dropped = {"range": 0, "repeat": 0, "unmatched": 0}
    used = set()
    claims = []
    for theme in themes:
        if len(claims) >= MAX_THEMES:
            break
        if not isinstance(theme, dict):
            continue
        statement = theme.get("statement")
        if not isinstance(statement, str) or not _squash(statement):
            continue
        picks = theme.get("picks")
        if not isinstance(picks, list):
            picks = []
        selections = []
        for pick in picks[:MAX_PICKS]:
            idx = _as_index(pick)
            if idx is None or idx < 0 or idx >= len(candidates):
                dropped["range"] += 1
                continue
            cand = candidates[idx]
            key = (cand["paper"], cand["quote"])
            if key in used:
                dropped["repeat"] += 1
                continue
            doc = docs.get(cand["paper"])
            if doc is None or not quote_ok(doc, cand["quote"]):
                dropped["unmatched"] += 1
                continue
            used.add(key)
            selections.append({"paper": cand["paper"], "quote": cand["quote"]})
        claims.append({
            "id": f"t{len(claims)}",
            "statement": _squash(statement)[:500],
            "selections": selections,
        })
    return claims, dropped


def _muse(prompt: str, timeout: float):
    from rrm.search.split import MODEL, message_text, post_chat

    # Reasoning tokens count against this cap. Subtopic splits use 1024; a panorama
    # writes up to four statements, so the cap is higher and still bounded.
    payload = post_chat(
        {
            "model": MODEL,
            "messages": [
                {"role": "developer", "content": _DEV},
                {"role": "user", "content": prompt},
            ],
            "reasoning_effort": "low",
            "max_completion_tokens": 2048,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "panorama_themes",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "themes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "statement": {"type": "string"},
                                        "picks": {"type": "array", "items": {"type": "string"}},
                                    },
                                    "required": ["statement", "picks"],
                                },
                            }
                        },
                        "required": ["themes"],
                    },
                },
            },
        },
        timeout=timeout,
    )
    usage = payload.get("usage") if isinstance(payload, dict) else None
    return message_text(payload), usage if isinstance(usage, dict) else None


def _timed_out(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    return isinstance(getattr(exc, "reason", None), TimeoutError)


def meta_panorama(question: str, docs: dict, complete=None) -> list[dict]:
    """Muse writes 2–4 statements and points at candidate sentences by index.

    `complete`, when passed, is `fn(prompt) -> str` or `(str, usage)` and does
    not touch the network. The real call uses `rrm.search.split.post_chat`.
    """
    _ensure_log()
    themes, candidates = candidate_sentences(question, docs)
    prompt = _prompt(question, candidates) if candidates else ""
    base = dict(prompt_chars=len(prompt), candidates=len(candidates), usage=None, elapsed_s=0.0, kept=0, dropped={"range": 0, "repeat": 0, "unmatched": 0})
    if not themes or not candidates:
        return _fallback(question, docs, "no_candidates", **base)

    timeout = _timeout_s()
    started = time.perf_counter()
    try:
        if complete is None:
            text, usage = _muse(prompt, timeout)
        else:
            out = complete(prompt)
            if isinstance(out, tuple):
                text, usage = out[0], out[1]
            else:
                text, usage = out, None
    except Exception as exc:
        base["elapsed_s"] = time.perf_counter() - started
        reason = "timeout" if _timed_out(exc) else "muse_error"
        log.info("panorama_meta error=%s detail=%s", reason, _redact(f"{type(exc).__name__}: {exc}"))
        return _fallback(question, docs, reason, **base)

    base["elapsed_s"] = time.perf_counter() - started
    base["usage"] = usage if isinstance(usage, dict) else None
    try:
        raw = _parse_themes(text)
    except (json.JSONDecodeError, ValueError, TypeError, RecursionError):
        return _fallback(question, docs, "invalid_json", **base)
    claims, dropped = _claims_from_picks(docs, candidates, raw)
    base["dropped"] = dropped
    base["kept"] = sum(len(c["selections"]) for c in claims)
    if not claims:
        return _fallback(question, docs, "no_themes", **base)
    _log_usage("meta", **base)
    return _tag(claims, "meta", False)


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
