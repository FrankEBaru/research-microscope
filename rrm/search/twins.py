"""Corpus ids that Semantic Scholar split in two (RRM-48). No Modal import.

NeRF (Mildenhall et al., ECCV 2020) is two S2 records:
- 282134003 holds the citations (7341 in node_meta) but has no year, venue,
  authors, DOI, arXiv id, or SPECTER2 vector, and is not in the CS display.
- 213175590 is the real record (2020, ECCV, arXiv 2003.08934, DOI, vector,
  CS) with 0 citations.
The link rank picks the stub, so the map showed it with no year and no label,
placed it from a title-only vector, and the reader had no PDF to open.
In the 31 cached questions on the volume (1 Nov 2026), this is the only
year-less paper in any top 10. Add a pair here only with that kind of evidence.
"""

TWINS = {282134003: 213175590}
STUB_OF = {canon: stub for stub, canon in TWINS.items()}


def canon(cid):
    cid = int(cid)
    return TWINS.get(cid, cid)


def has_stub(payload):
    """True when a stored burst payload still lists a split stub id."""
    for key in ("papers", "similar"):
        for row in (payload or {}).get(key) or []:
            if isinstance(row, dict) and row.get("corpusid") in TWINS:
                return True
    return False


def remap_result(result):
    """burst_query output with each stub id swapped for its real record.

    Ranks and scores stay where the stub was; a later duplicate is dropped."""
    out = dict(result)
    papers = dict(out.get("papers") or {})
    ids, scores, seen = [], [], set()
    for cid, score in zip(papers.get("corpusids") or [], papers.get("scores") or []):
        cid = canon(cid)
        if cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
        scores.append(score)
    papers["corpusids"], papers["scores"] = ids, scores
    out["papers"] = papers
    similar, seen = [], set()
    for row in out.get("similar") or []:
        cid = canon(row["corpusid"])
        if cid not in seen:
            seen.add(cid)
            similar.append({**row, "corpusid": cid})
    out["similar"] = similar
    edges, seen = [], set()
    for edge in out.get("edges") or []:
        pair = (canon(edge["citing"]), canon(edge["cited"]))
        if pair[0] != pair[1] and pair not in seen:
            seen.add(pair)
            edges.append({"citing": pair[0], "cited": pair[1]})
    out["edges"] = edges
    if out.get("first_id") is not None:
        out["first_id"] = canon(out["first_id"])
    return out
