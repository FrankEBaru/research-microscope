"""Survey y retractación sobre metadatos ya bajados. Sin red y sin FAISS."""

from rrm.search.layout import NEIGHBOR_MIN

SURVEY_COSINE = NEIGHBOR_MIN
NO_RETRACTION = "No encontré retractación en Crossref"
OFFLINE_NOTE = "Sin red: solo el título, sin survey."


def is_review(publication_types, openalex_type=None):
    """Review en Semantic Scholar u OpenAlex. El título no vuelve review a un preprint."""
    for item in publication_types or []:
        if str(item).strip().lower() == "review":
            return True
    return str(openalex_type or "").strip().lower() == "review"


def crossref_retracted(message):
    """True si hay retractación. False si el cuerpo vino y no hay. None sin cuerpo."""
    if not isinstance(message, dict):
        return None
    updates = message.get("update-to") or message.get("update_to") or []
    if not isinstance(updates, list):
        return None
    for row in updates:
        if not isinstance(row, dict):
            continue
        blob = " ".join(str(row.get(key) or "") for key in ("type", "label", "source")).lower()
        if "retract" in blob:
            return True
    return False


def retraction_fields(message, openalex_flag):
    if crossref_retracted(message) is True or openalex_flag is True:
        return True, "retractado"
    return False, NO_RETRACTION


def cosine(left, right):
    import numpy as np

    a = np.asarray(left, dtype=np.float64).reshape(-1)
    b = np.asarray(right, dtype=np.float64).reshape(-1)
    if a.size == 0 or a.shape != b.shape:
        return None
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-9 or nb < 1e-9:
        return None
    return float(a @ b / (na * nb))


def _cid(row):
    if not isinstance(row, dict):
        return None
    raw = row.get("corpusid")
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


def _flags(info):
    retracted = info.get("retracted") is True
    note = info.get("retraction") or ("retractado" if retracted else NO_RETRACTION)
    return retracted, note


def apply_survey(papers, meta, cosines, threshold=SURVEY_COSINE):
    """Un review con coseno suficiente ocupa un lugar. Si ya está, no se duplica."""
    annotated = {}
    for raw, row in (meta or {}).items():
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        info = dict(row or {})
        info["review"] = is_review(info.get("publication_types"), info.get("openalex_type"))
        info["cosine"] = (cosines or {}).get(cid)
        annotated[cid] = info

    def qualifies(cid):
        row = annotated.get(cid) or {}
        score = row.get("cosine")
        return bool(row.get("review")) and isinstance(score, (int, float)) and float(score) >= float(threshold)

    out = []
    for paper in papers or []:
        cid = _cid(paper)
        if cid is None:
            continue
        row = dict(paper)
        extra = annotated.get(cid) or {}
        if extra.get("abstract"):
            row["abstract"] = extra["abstract"]
        row["survey"] = qualifies(cid)
        row["retracted"], row["retraction"] = _flags(extra)
        out.append(row)
    if any(row.get("survey") for row in out):
        return out, None
    best = None
    best_score = None
    have = {row["corpusid"] for row in out}
    for cid, info in annotated.items():
        if cid in have or not qualifies(cid):
            continue
        score = float(info["cosine"])
        if best is None or score > best_score:
            best, best_score = cid, score
    if best is None:
        return out, None
    info = annotated[best]
    extra = dict(info.get("paper") or {"corpusid": best, "title": info.get("title") or ""})
    extra.update({
        "corpusid": best,
        "survey": True,
        "abstract": info.get("abstract") or extra.get("abstract") or "",
        "retracted": info.get("retracted") is True,
        "retraction": info.get("retraction") or NO_RETRACTION,
    })
    return out + [extra], extra


def label_payload(papers, similar, meta, scores):
    if meta is None:
        return {"ok": False, "note": OFFLINE_NOTE, "by_id": {}, "survey_paper": None, "papers": list(papers or [])}
    pool = {}
    for row in list(papers or []) + list(similar or []):
        cid = _cid(row)
        if cid is not None:
            pool.setdefault(cid, row)
    merged = {}
    for cid, info in meta.items():
        merged[int(cid)] = dict(info)
        if pool.get(int(cid)):
            merged[int(cid)]["paper"] = pool[int(cid)]
    ranked, extra = apply_survey(papers, merged, scores)
    by_id = {}
    for row in ranked:
        src = merged.get(row["corpusid"]) or {}
        by_id[str(row["corpusid"])] = {
            "abstract": row.get("abstract") or "",
            "survey": bool(row.get("survey")),
            "retracted": bool(row.get("retracted")),
            "retraction": row.get("retraction") or NO_RETRACTION,
            "tldr": src.get("tldr") or row.get("tldr") or "",
        }
    return {"ok": True, "note": "", "by_id": by_id, "survey_paper": extra, "papers": ranked}
