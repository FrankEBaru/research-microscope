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
        return {
            "ok": False, "reason": "network", "note": OFFLINE_NOTE,
            "by_id": {}, "survey_paper": None, "papers": list(papers or []),
        }
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
            "authors": list(src.get("authors") or []),
        }
    return {"ok": True, "reason": "", "note": "", "by_id": by_id, "survey_paper": extra, "papers": ranked}


def pending_payload(papers):
    """La ráfaga todavía no está en el caché. No es falta de red."""
    return {
        "ok": False, "reason": "pending", "note": "",
        "by_id": {}, "survey_paper": None, "papers": list(papers or []),
    }


def parse_s2(data):
    if not isinstance(data, dict):
        return None
    ext = data.get("externalIds") or {}
    tldr = data.get("tldr") if isinstance(data.get("tldr"), dict) else {}
    from rrm.reader.fetch import _author_names

    return {
        "abstract": data.get("abstract") or "",
        "publication_types": list(data.get("publicationTypes") or []),
        "doi": (ext.get("DOI") or "") if isinstance(ext, dict) else "",
        "title": data.get("title") or "",
        "tldr": (tldr or {}).get("text") or "",
        "authors": _author_names(data.get("authors")),
    }


def fetch_s2(ids, timeout):
    import json
    import os
    import urllib.request

    from rrm.reader.fetch import S2, S2_LIMIT

    if not ids:
        return []
    S2_LIMIT.wait()
    headers = {"User-Agent": "research-microscope/0.1", "Content-Type": "application/json"}
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    body = json.dumps({"ids": [f"CorpusId:{int(cid)}" for cid in ids]}).encode()
    fields = "abstract,publicationTypes,externalIds,title,tldr,authors"
    req = urllib.request.Request(f"{S2}batch?fields={fields}", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def fetch_crossref(doi, timeout):
    import json
    import urllib.parse
    import urllib.request

    quoted = urllib.parse.quote(str(doi), safe="/")
    req = urllib.request.Request(
        f"https://api.crossref.org/works/{quoted}",
        headers={"User-Agent": "research-microscope/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    return (body or {}).get("message") or {}


def fetch_openalex(dois, timeout):
    import json
    import urllib.parse
    import urllib.request

    filt = "|".join(urllib.parse.quote(doi, safe="") for doi in dois)
    url = f"https://api.openalex.org/works?filter=doi:{filt}&select=doi,type,is_retracted&per-page=50"
    req = urllib.request.Request(url, headers={"User-Agent": "research-microscope/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    out = {}
    for row in (body or {}).get("results") or []:
        doi = str(row.get("doi") or "").rsplit("/", 1)[-1].lower()
        if doi:
            out[doi] = {"type": row.get("type") or "", "is_retracted": row.get("is_retracted")}
    return out


def _cache_path(cache_dir, kind, key):
    import re
    from pathlib import Path

    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(key))[:180]
    return Path(cache_dir) / kind / f"{safe}.json"


def _cache_load(path):
    import json

    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_save(path, body):
    import json

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return


def _crossref_one(fetch, cid, doi, timeout):
    try:
        return cid, doi, fetch(doi, timeout)
    except Exception:
        return cid, doi, None


def _retraction(found, cache_dir, crossref_fetch, openalex_fetch, timeout):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pairs = [(cid, (row.get("doi") or "").strip()) for cid, row in found.items() if (row.get("doi") or "").strip()]
    oa = {}
    if pairs and openalex_fetch is not None:
        try:
            oa = openalex_fetch([doi for _cid, doi in pairs], timeout) or {}
        except Exception:
            oa = {}
    pending = []
    for cid, doi in pairs:
        hit = _cache_load(_cache_path(cache_dir, "crossref", doi)) if cache_dir else None
        if isinstance(hit, dict) and "message" in hit:
            found[cid]["crossref"] = hit["message"]
        else:
            pending.append((cid, doi))
    if pending and crossref_fetch is not None:
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            futs = [pool.submit(_crossref_one, crossref_fetch, cid, doi, timeout) for cid, doi in pending]
            try:
                for fut in as_completed(futs, timeout=timeout):
                    cid, doi, message = fut.result()
                    found[cid]["crossref"] = message
                    if cache_dir and isinstance(message, dict):
                        _cache_save(_cache_path(cache_dir, "crossref", doi), {"message": message})
            except Exception:
                pass
    for row in found.values():
        alex = oa.get((row.get("doi") or "").lower()) or {}
        if alex.get("type"):
            row["openalex_type"] = alex["type"]
        flag = alex.get("is_retracted")
        row["retracted"], row["retraction"] = retraction_fields(
            row.get("crossref"), flag if isinstance(flag, bool) else None,
        )


def lookup_meta(ids, cache_dir, *, s2_fetch=fetch_s2, crossref_fetch=fetch_crossref, openalex_fetch=fetch_openalex, timeout=2.5):
    """None si Semantic Scholar no responde y no hay caché. Si no, un dict por corpus id."""
    ids = [int(cid) for cid in ids or []]
    found, missing, stale = {}, [], {}
    for cid in ids:
        cached = _cache_load(_cache_path(cache_dir, "s2", cid)) if cache_dir else None
        if isinstance(cached, dict) and "publication_types" in cached and "authors" in cached:
            found[cid] = cached
        else:
            if isinstance(cached, dict) and "publication_types" in cached:
                stale[cid] = cached
            missing.append(cid)
    if missing:
        try:
            rows = s2_fetch(missing, timeout)
        except Exception:
            rows = None
        if rows is None:
            if not found and not stale:
                return None
            for cid, row in stale.items():
                kept = dict(row)
                kept.setdefault("authors", [])
                found.setdefault(cid, kept)
        else:
            for cid, data in zip(missing, rows or []):
                parsed = parse_s2(data) or {"abstract": "", "publication_types": [], "doi": "", "title": "", "tldr": "", "authors": []}
                found[cid] = parsed
                if cache_dir:
                    _cache_save(_cache_path(cache_dir, "s2", cid), parsed)
    _retraction(found, cache_dir, crossref_fetch, openalex_fetch, timeout)
    return found


def review_ids(meta):
    return [int(cid) for cid, row in (meta or {}).items() if is_review(row.get("publication_types"), row.get("openalex_type"))]


def cosines_for(ids, encode, vector_of, query, query_vec=None):
    """Reusa el vector de la pregunta si la ráfaga ya lo calculó."""
    if vector_of is None or (query_vec is None and encode is None):
        return {}
    try:
        import numpy as np

        if query_vec is None:
            query_vec = np.asarray(encode([query]), dtype=np.float32)[0]
        else:
            query_vec = np.asarray(query_vec, dtype=np.float32).reshape(-1)
    except Exception:
        return {}
    out = {}
    for cid in ids or []:
        try:
            vec = vector_of(int(cid))
        except Exception:
            vec = None
        score = cosine(query_vec, vec) if vec is not None else None
        if score is not None:
            out[int(cid)] = score
    return out


def candidate_ids(payload, cap=40):
    ids, seen = [], set()
    for key in ("papers", "similar"):
        for row in (payload or {}).get(key) or []:
            cid = _cid(row)
            if cid is None or cid in seen:
                continue
            seen.add(cid)
            ids.append(cid)
            if len(ids) >= int(cap):
                return ids
    return ids
