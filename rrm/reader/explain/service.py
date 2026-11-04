"""Explain en el servidor: precálculo al abrir el paper y `/ask` por sección.

- `kick(cid, ...)`: al abrir un paper, en un hilo: vectores de todas sus oraciones
  y la hoja de respuestas de cada sección con botón. Se guarda en
  `papers/<id>/explain/` y se hace commit del volumen.
- `ask(...)`: revisa con la hoja si ya está (E2) y, si no, con la ventana (E1),
  sin esperar al precálculo. El cuerpo es el de `/ask` de siempre, más
  `diverge`, `why`, `cites` y `others` por parte.

`RRM_EXPLAIN=0` vuelve a la caja anterior (feedback.py). `RRM_EXPLAIN_PASSAGES=0`
arma la hoja sin pasajes de otros papers.
"""

import os
import re
import threading
import time

from rrm.reader.explain import llm
from rrm.reader.explain.review import PARTS, Context, review_e1, review_e2, sentences
from rrm.reader.explain.section import headings, section_units
from rrm.reader.explain.sheet import build_sheet, load_sheet, save_sheet

_SKIP = re.compile(r"acknowledg|author contributions|references|bibliography|model card|list of trained", re.I)
_MAX_SECTIONS = 30
_jobs = set()
_guard = threading.Lock()
_ctx = {}


def store_dir(folder):
    """Dónde viven hojas y vectores. `RRM_EXPLAIN_DIR` los saca del volumen (lector de solo lectura)."""
    from pathlib import Path

    raw = os.environ.get("RRM_EXPLAIN_DIR", "").strip()
    return Path(raw) / Path(folder).name if raw else Path(folder)


def explain_on():
    return os.environ.get("RRM_EXPLAIN", "1").strip().lower() not in ("0", "off", "false", "no")


def passages_on():
    return os.environ.get("RRM_EXPLAIN_PASSAGES", "1").strip().lower() not in ("0", "off", "false", "no")


def _effort():
    return os.environ.get("RRM_EXPLAIN_EFFORT", "").strip() or "minimal"


def _sheet_effort():
    return os.environ.get("RRM_EXPLAIN_SHEET_EFFORT", "").strip() or "low"


def sections_to_prepare(paper):
    out = []
    for sid, _level, title in headings(paper):
        if _SKIP.search(title or ""):
            continue
        if len(section_units(paper, sid)) < 2:
            continue
        out.append(sid)
    return out[:_MAX_SECTIONS]


def _base():
    if not passages_on():
        return None
    try:
        from rrm.reader.explain.retrieve import passage_base

        return passage_base()
    except Exception:
        return None


def context(folder, paper, section_id, encode=None):
    key = (str(folder), str(paper.get("corpusid")), str(section_id), len(paper.get("blocks") or []))
    with _guard:
        hit = _ctx.get(key)
    if hit is None:
        hit = Context(paper, section_id, folder=folder, encode=encode)
        with _guard:
            _ctx[key] = hit
    return hit


def prepare(folder, paper, *, encode=None, lock=None, commit=None, base=None, sections=None, log=None):
    """Vectores del paper y hojas que falten. Devuelve un resumen con costo y tiempo."""
    started = time.perf_counter()
    lock = lock or threading.Lock()
    folder = store_dir(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("RRM_EXPLAIN_DIR", "").strip():
        commit = None
    todo = sections if sections is not None else sections_to_prepare(paper)
    done, built, cost = [], [], llm.add(None, None)
    if not todo:
        return {"sections": 0, "built": 0, "seconds": 0.0, "cost": cost}
    ctx = context(folder, paper, todo[0], encode)
    _ = ctx.vecs  # explain-units-*.npy: la revisión ya no encodea el paper
    base = base if base is not None else _base()
    pending = [sid for sid in todo if not load_sheet(folder, sid)]
    done = [sid for sid in todo if sid not in pending]
    if not os.environ.get("MODEL_API_KEY"):
        pending = []

    def one(sid):
        try:
            return sid, build_sheet(paper, sid, base=base, encode=encode, effort=_sheet_effort(), passages=base is not None)
        except Exception as err:
            if log:
                log(f"explain sheet {sid}: {type(err).__name__}")
            return sid, None

    # Meta espera red, no CPU: 4 secciones a la vez bajan ~9 min a ~2–3 min por paper.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=int(os.environ.get("RRM_EXPLAIN_THREADS", "4") or 4)) as pool:
        for sid, sheet in pool.map(one, pending):
            if sheet is None:
                continue
            cost = llm.add(cost, sheet.get("cost"))
            with lock:
                save_sheet(folder, sheet)
                if commit:
                    try:
                        commit()
                    except Exception:
                        pass
            built.append(sid)
    return {"sections": len(todo), "ready": len(done) + len(built), "built": len(built),
            "seconds": round(time.perf_counter() - started, 3), "cost": cost}


def kick(cid, folder, load_paper, *, encode=None, lock=None, commit=None, log=None):
    """Una vez por paper y proceso, en un hilo."""
    if not explain_on():
        return False
    with _guard:
        if cid in _jobs:
            return False
        _jobs.add(cid)

    def work():
        try:
            paper = load_paper(folder)
            if not isinstance(paper, dict) or not paper.get("blocks"):
                with _guard:
                    _jobs.discard(cid)  # todavía es un stub: el próximo /paper lo intenta otra vez
                return
            out = prepare(folder, paper, encode=encode, lock=lock, commit=commit, log=log)
            if log:
                log(f"explain prep {cid}: {out}")
        except Exception as err:
            with _guard:
                _jobs.discard(cid)
            if log:
                log(f"explain prep {cid} failed: {type(err).__name__}")

    threading.Thread(target=work, name=f"rrm-explain-{cid}", daemon=True).start()
    return True


def status(folder, paper):
    folder = store_dir(folder)
    todo = sections_to_prepare(paper)
    ready = [sid for sid in todo if load_sheet(folder, sid)]
    return {"sections": len(todo), "ready": len(ready), "ids": ready}


def _extracts(parts):
    rows, seen = [], set()
    for part in PARTS:
        for item in parts.get(part) or []:
            for cite in item.get("cites") or []:
                key = cite.get("ptr")
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"paper": cite.get("paper_id"), "section": cite.get("section") or "", "text": cite.get("text") or "", "ptr": key})
    return rows


def ask(folder, paper, section_id, text, *, stage="revisar", encode=None, store=None):
    """El cuerpo de `/ask` para una sección. stage=frases no llama a Meta."""
    from rrm.reader.metacall import meta_status, note_for

    started = time.perf_counter()
    folder = store_dir(folder)
    empty = {part: [] for part in PARTS}
    base_body = {"papers": 1, "line": "", "matched": 0, "store": store or {"ready": 1, "total": 1}, "engine": ""}
    ctx = context(folder, paper, section_id, encode)
    if not ctx.section:
        return {**base_body, "extracts": [], "empty": True, "parts": empty, "note": "No hay frases guardadas de estos papers."}
    sents = sentences(text)
    if stage == "frases":
        near = []
        seen = set()
        for row in ctx.near(sents, k=2) if sents else []:
            for unit in row:
                if unit["id"] not in seen:
                    seen.add(unit["id"])
                    near.append({"paper": str(paper.get("corpusid")), "section": unit.get("section") or "", "text": unit["text"], "ptr": unit["id"]})
        return {**base_body, "extracts": near[:6], "empty": False, "matched": len(near), "parts": empty, "note": "", "engine": "frases"}
    status_ = meta_status()
    if status_:
        return {**base_body, "extracts": [], "empty": False, "parts": empty, "note": note_for(status_)}
    sheet = load_sheet(folder, section_id)
    try:
        if sheet and sheet.get("points"):
            parts, cost, info = review_e2(ctx, text, sheet, effort=_effort())
            engine = "sheet"
        else:
            parts, cost, info = review_e1(ctx, text, effort=_effort())
            engine = "window"
    except Exception:
        return {**base_body, "extracts": [], "empty": False, "parts": empty, "note": note_for("red")}
    if not info.get("parsed"):
        return {**base_body, "extracts": [], "empty": False, "parts": empty, "note": note_for("parse"), "meta": cost}
    extracts = _extracts(parts)
    return {
        **base_body, "extracts": extracts, "empty": False, "matched": len(extracts), "parts": parts, "note": "",
        "meta": cost, "engine": engine,
        "timing": {"total_s": round(time.perf_counter() - started, 3), "llm_s": info.get("llm_s")},
        "key_points": [{"id": p["id"], "point": p["point"], "core": p.get("core")} for p in (sheet or {}).get("points") or []],
    }
