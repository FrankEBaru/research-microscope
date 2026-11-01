"""Una llamada batch a Semantic Scholar, luego Crossref por DOI. Caché y timeout corto."""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rrm.search.labelhttp import fetch_crossref, fetch_openalex, fetch_s2, parse_s2
from rrm.search.labels import _cid, cosine, retraction_fields

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _path(cache_dir, kind, key):
    safe = _SAFE.sub("_", str(key))[:180]
    return Path(cache_dir) / kind / f"{safe}.json"


def _load(path):
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(path, body):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return


def lookup_meta(ids, cache_dir, *, s2_fetch=fetch_s2, crossref_fetch=fetch_crossref, openalex_fetch=fetch_openalex, timeout=2.5):
    """None si Semantic Scholar no responde y no hay caché. Si no, un dict por corpus id."""
    ids = [int(cid) for cid in ids or []]
    found = {}
    missing = []
    for cid in ids:
        cached = _load(_path(cache_dir, "s2", cid)) if cache_dir else None
        if isinstance(cached, dict) and "publication_types" in cached:
            found[cid] = cached
        else:
            missing.append(cid)
    if missing:
        try:
            rows = s2_fetch(missing, timeout)
        except Exception:
            rows = None
        if rows is None and not found:
            return None
        for cid, data in zip(missing, rows or []):
            parsed = parse_s2(data) or {
                "abstract": "", "publication_types": [], "doi": "", "title": "", "tldr": "",
            }
            found[cid] = parsed
            if cache_dir:
                _save(_path(cache_dir, "s2", cid), parsed)
    _retraction(found, cache_dir, crossref_fetch, openalex_fetch, timeout)
    return found


def _retraction(found, cache_dir, crossref_fetch, openalex_fetch, timeout):
    pairs = [(cid, (row.get("doi") or "").strip()) for cid, row in found.items() if (row.get("doi") or "").strip()]
    oa = {}
    if pairs and openalex_fetch is not None:
        try:
            oa = openalex_fetch([doi for _cid, doi in pairs], timeout) or {}
        except Exception:
            oa = {}
    pending = []
    for cid, doi in pairs:
        hit = _load(_path(cache_dir, "crossref", doi)) if cache_dir else None
        if isinstance(hit, dict) and "message" in hit:
            found[cid]["crossref"] = hit["message"]
        else:
            pending.append((cid, doi))
    if pending and crossref_fetch is not None:
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            futs = [pool.submit(_one, crossref_fetch, cid, doi, timeout) for cid, doi in pending]
            try:
                for fut in as_completed(futs, timeout=timeout):
                    cid, doi, message = fut.result()
                    found[cid]["crossref"] = message
                    if cache_dir and isinstance(message, dict):
                        _save(_path(cache_dir, "crossref", doi), {"message": message})
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


def _one(fetch, cid, doi, timeout):
    try:
        return cid, doi, fetch(doi, timeout)
    except Exception:
        return cid, doi, None


def review_ids(meta):
    from rrm.search.labels import is_review

    out = []
    for cid, row in (meta or {}).items():
        if is_review(row.get("publication_types"), row.get("openalex_type")):
            out.append(int(cid))
    return out


def cosines_for(ids, encode, vector_of, query):
    if encode is None or vector_of is None:
        return {}
    try:
        import numpy as np
        query_vec = np.asarray(encode([query]), dtype=np.float32)[0]
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
    ids = []
    seen = set()
    for key in ("papers", "similar"):
        for row in payload.get(key) or []:
            cid = _cid(row)
            if cid is None or cid in seen:
                continue
            seen.add(cid)
            ids.append(cid)
            if len(ids) >= int(cap):
                return ids
    return ids
