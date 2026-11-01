"""Clientes gratis de Semantic Scholar, Crossref y OpenAlex. Un intento, timeout del llamador."""

import json
import os
import urllib.parse
import urllib.request


def parse_s2(data):
    if not isinstance(data, dict):
        return None
    ext = data.get("externalIds") or {}
    tldr = data.get("tldr") if isinstance(data.get("tldr"), dict) else {}
    return {
        "abstract": data.get("abstract") or "",
        "publication_types": list(data.get("publicationTypes") or []),
        "doi": (ext.get("DOI") or "") if isinstance(ext, dict) else "",
        "title": data.get("title") or "",
        "tldr": (tldr or {}).get("text") or "",
    }


def fetch_s2(ids, timeout):
    from rrm.reader.fetch import S2, S2_LIMIT

    if not ids:
        return []
    S2_LIMIT.wait()
    headers = {"User-Agent": "research-microscope/0.1", "Content-Type": "application/json"}
    key = os.environ.get("S2_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    body = json.dumps({"ids": [f"CorpusId:{int(cid)}" for cid in ids]}).encode()
    fields = "abstract,publicationTypes,externalIds,title,tldr"
    req = urllib.request.Request(f"{S2}batch?fields={fields}", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def fetch_crossref(doi, timeout):
    quoted = urllib.parse.quote(str(doi), safe="/")
    req = urllib.request.Request(
        f"https://api.crossref.org/works/{quoted}",
        headers={"User-Agent": "research-microscope/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    return (body or {}).get("message") or {}


def fetch_openalex(dois, timeout):
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
