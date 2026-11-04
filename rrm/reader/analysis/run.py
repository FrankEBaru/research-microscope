"""Análisis v2 para `/notes` (bandera `RRM_ANALYSIS=v2`).

`analyze_paper(paper)` arma el brief, corre el candidato ganador y devuelve el
mismo formato que `notes.answer_notes` (notes, artifacts, usage) más campos v2:
cada nota trae `v2` con las tres capas etiquetadas (AI-generated, citas del
paper, citas de otros papers) ya copiadas por código, y `widgets` trae las
especificaciones para el pipeline de RRM-96.

Caché: `<RRM_DATA>/analysis/v2/<corpusid>-<hash>.json`. Si existe, responde al
instante (los papers del demo se precalculan).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from rrm.reader.analysis import llm
from rrm.reader.analysis.brief import BriefIndex, build_brief
from rrm.reader.analysis.contract import materialize

WINNER = os.environ.get("RRM_ANALYSIS_CAND", "C1")


def enabled():
    return os.environ.get("RRM_ANALYSIS", "").strip().lower() == "v2"


def _data():
    return Path(os.environ.get("RRM_DATA", "/data").strip() or "/data")


def cache_path(cid, phash):
    return _data() / "analysis" / "v2" / f"{cid}-{phash}.json"


_BASE = {}


def base_cids():
    if "c" not in _BASE:
        try:
            import pyarrow.parquet as pq
            from rrm.reader.passage_db import passages_dir

            col = pq.read_table(passages_dir() / "rows.parquet", columns=["corpusid"]).column("corpusid").to_pylist()
            _BASE["c"] = sorted({int(c) for c in col if c is not None})
        except Exception:
            _BASE["c"] = []
    return _BASE["c"]


def local_retr():
    """Búsqueda en el mismo contenedor (lector en Modal: volumen montado)."""
    from rrm.reader.analysis import retrieve
    from rrm.reader.analysis.candidates import Retr

    def fn(jobs):
        out = []
        for job in jobs:
            out.append(retrieve.search([job["q"]], k=job.get("k", 10), exclude=job.get("exclude") or (),
                                       only=job.get("only"), kinds=job.get("kinds"))[0])
        return out

    return Retr(fn, None)


def to_response(res, brief, paper):
    ix = BriefIndex(brief)
    rows = res.get("rows") or {}
    notes = []
    for it in res["items"]:
        m = materialize(it, ix, rows)
        anchor = it["anchor"]
        if "#" in anchor:
            bid, sent = anchor.split("#", 1)
            sent = int(sent)
        else:
            bid, sent = anchor, 0
        sec = ix.secs[ix.section_of(anchor)] if ix.section_of(anchor) >= 0 else {"title": ""}
        cite = m["paper_quotes_text"][0]["text"] if m["paper_quotes_text"] else ""
        notes.append({
            "block_id": bid, "sent_index": sent, "note": it["ai_text"], "cite": cite, "passage_id": "",
            "generated": True, "paper": str(brief["paper"]["corpusid"]), "section": sec.get("title", ""),
            "occupy": [bid], "kind": it["kind"],
            "v2": {"anchor": anchor, "why": it.get("why", ""), "ai": {"label": "AI-generated", "text": it["ai_text"]},
                   "paper": {"label": "From this paper", "quotes": m["paper_quotes_text"]},
                   "others": {"label": "From other papers", "passages": m["passages_text"]},
                   "v1": it.get("v1", "show")},
        })
    # Dibujos locales de siempre (con_sin, matriz): salen de gaps.py, $0, el lector ya los pinta.
    from rrm.reader.gaps import find_gaps

    legacy = []
    for eq in find_gaps(paper.get("blocks") or []).get("equations") or []:
        if eq.get("hint") in ("matriz", "con_sin") and len(legacy) < 2:
            legacy.append({"block_id": eq.get("block_id"), "type": eq.get("hint"), "why_look": "", "tex": eq.get("tex") or "", "drop": eq.get("drop") or ""})
    widgets = [dict(a, paper_quotes_text=[{"ptr": p, "text": ix.text(p)} for p in a.get("paper_quotes") or []]) for a in res.get("artifacts") or []]
    return {"notes": notes, "artifacts": legacy, "widgets": widgets,
            "usage": {"model": llm.CONTRIBUTOR, "license": paper.get("license") or "", "cost_usd": res.get("usd", 0.0)},
            "analysis": {"v": "rrm99-v2", "cand": WINNER, "brief": brief["v"], "hash": brief["paper"]["hash"],
                         "wall_s": res.get("wall_s"), "calls": res.get("calls")}}


def analyze_paper(paper, retr=None, cfg=None, cand=None, write_cache=True):
    from rrm.reader.analysis.candidates import CANDIDATES, v1, _cfg

    t0 = time.perf_counter()
    brief = build_brief(paper, base_cids())
    cid = brief["paper"]["corpusid"]
    path = cache_path(cid, brief["paper"]["hash"])
    if path.is_file():
        out = json.loads(path.read_text(encoding="utf-8"))
        out.setdefault("analysis", {})["cached"] = True
        return out
    # Integration (RRM-95): the same paper re-parsed can change its hash (stage, figures). A slightly stale
    # analysis of the same corpusid beats falling back to notes.py with zero notes; anchors are re-checked by the UI.
    try:
        older = sorted(path.parent.glob(f"{cid}-*.json"), key=lambda q: q.stat().st_mtime, reverse=True)
    except Exception:
        older = []
    if older:
        out = json.loads(older[0].read_text(encoding="utf-8"))
        info = out.setdefault("analysis", {})
        info["cached"] = True
        info["stale_hash"] = True
        return out
    retr = retr or local_retr()
    res = CANDIDATES[cand or WINNER](paper, brief, retr, cfg)
    res["items"], _rec = v1(BriefIndex(brief), res["items"], _cfg(cfg))
    res["rows"] = {pid: retr.rows[pid] for it in res["items"] for pid in it.get("passages") or [] if pid in retr.rows}
    out = to_response(res, brief, paper)
    out["analysis"]["total_s"] = round(time.perf_counter() - t0, 2)
    if write_cache:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


_RUNNING = set()


def cached_or_kick(paper, commit=None):
    """Caché → respuesta v2 al instante. Sin caché: lanza el análisis en un hilo y devuelve None
    (el caller responde con notes.py; la próxima apertura ya trae v2). RRM_ANALYSIS_SYNC=1 espera."""
    import threading

    brief = build_brief(paper, base_cids())
    cid = brief["paper"]["corpusid"]
    path = cache_path(cid, brief["paper"]["hash"])
    if path.is_file():
        out = json.loads(path.read_text(encoding="utf-8"))
        out.setdefault("analysis", {})["cached"] = True
        return out
    # Integration (RRM-95): the same paper re-parsed can change its hash (stage, figures). A slightly stale
    # analysis of the same corpusid beats falling back to notes.py with zero notes; anchors are re-checked by the UI.
    try:
        older = sorted(path.parent.glob(f"{cid}-*.json"), key=lambda q: q.stat().st_mtime, reverse=True)
    except Exception:
        older = []
    if older:
        out = json.loads(older[0].read_text(encoding="utf-8"))
        info = out.setdefault("analysis", {})
        info["cached"] = True
        info["stale_hash"] = True
        return out
    if os.environ.get("RRM_ANALYSIS_SYNC", "").strip() == "1":
        out = analyze_paper(paper)
        if commit:
            commit()
        return out
    if cid in _RUNNING:
        return None

    def work():
        try:
            analyze_paper(paper)
            if commit:
                commit()
        except Exception:
            pass
        finally:
            _RUNNING.discard(cid)

    _RUNNING.add(cid)
    threading.Thread(target=work, daemon=True).start()
    return None
