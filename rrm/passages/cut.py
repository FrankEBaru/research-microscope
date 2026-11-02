"""Primer corte: tres vecindarios, solo el listado.

13756489 es el corpus del Transformer citado en
docs/notas/RRM-28-meta-panorama-2026-10-30.md. Los otros dos anclas se
resuelven al correr: título en display, o el primer hit del FAISS. Este
módulo no baja e-prints ni abre Modal.
"""

from rrm.passages.score import assemble_seeds, rank_by_citations, rank_neighborhood
from rrm.passages.union import quotas_for, title_notes, union_papers

# k=200 es el de la config long ya medida. No es un k nuevo.
NEIGHBOR_K = 200

THEMES = (
    {"name": "attention", "anchor": 13756489, "title": None, "question": None},
    {
        "name": "gcn",
        "anchor": None,
        "title": "Semi-Supervised Classification with Graph Convolutional Networks",
        "question": None,
    },
    {
        "name": "icl-linear",
        "anchor": None,
        "title": None,
        "question": "in-context learning linear models",
    },
)


def apply_anchor_overrides(themes, raw):
    """`attention=1,gcn=2` fija el ancla. Un nombre ausente se queda como está."""
    found = {}
    for part in str(raw or "").split(","):
        if "=" not in part:
            continue
        name, val = part.split("=", 1)
        val = val.strip()
        if not name.strip() or not val:
            continue
        found[name.strip()] = int(val)
    out = []
    for theme in themes:
        item = dict(theme)
        if item["name"] in found:
            item["anchor"] = found[item["name"]]
            item["title"] = None
            item["question"] = None
        out.append(item)
    return out


def resolve_seeds(spec, *, neighbors_of, first_hit, title_hit, k=NEIGHBOR_K, text_neighbors=None, text_of=None):
    """Arma las semillas. `neighbors_of` son los vecinos del vector ya guardado.

    Un ancla sin vector en FAISS (p. ej. GCN, 3144218, que no está en
    faiss_ids.npy) no tiene vecinos. Entonces se embebe su título con el
    adapter de proximidad (`text_neighbors(texto)`) y se buscan vecinos con
    ese vector. Si tampoco hay, la semilla queda con error "ancla sin vecinos"
    y la unión se niega a seguir (ver cut_flags).
    """
    anchor = spec.get("anchor")
    how = "given"
    if anchor is None and spec.get("title"):
        anchor = title_hit(spec["title"]) if title_hit else None
        how = "title"
    if anchor is None and spec.get("question"):
        anchor = first_hit(spec["question"]) if first_hit else None
        how = "faiss"
    if anchor is None:
        return {
            "name": spec.get("name"),
            "anchor": None,
            "seeds": [],
            "neighbors": 0,
            "how": how,
            "error": "sin ancla",
        }
    neighbors = list(neighbors_of(int(anchor)) or []) if neighbors_of else []
    via = "vector"
    if not neighbors and text_neighbors is not None:
        text = (text_of(int(anchor)) if text_of else None) or spec.get("title") or spec.get("question") or ""
        if text:
            neighbors = [cid for cid in (text_neighbors(text) or []) if int(cid) != int(anchor)][: int(k)]
            via = "text"
    if not neighbors:
        return {
            "name": spec.get("name"),
            "anchor": int(anchor),
            "seeds": [],
            "neighbors": 0,
            "how": how,
            "via": "none",
            "error": "ancla sin vecinos",
        }
    seeds = assemble_seeds(anchor, neighbors, k=k)
    return {
        "name": spec.get("name"),
        "anchor": int(anchor),
        "seeds": seeds,
        "neighbors": max(0, len(seeds) - 1),
        "how": how,
        "via": via,
        "error": None,
    }


def _field_name(field, names, local):
    if field is None or local is None:
        return None
    code = int(field[int(local)])
    if names is None or code < 0 or code >= len(names):
        return None
    return str(names[code])


def theme_report(graph, citation_counts, seed_ids, meta_of, field=None, field_names=None, top_n=10):
    """Top del vecindario y, al lado, el top por citas globales de esos candidatos."""
    ranked = rank_neighborhood(graph, seed_ids, citation_counts)
    by_cc = rank_by_citations(ranked)

    def pack(rows):
        out = []
        for row in rows[: int(top_n)]:
            meta = meta_of(row["corpusid"]) if meta_of else {}
            meta = meta or {}
            out.append({
                "corpusid": row["corpusid"],
                "score": row["score"],
                "citationcount": row["citationcount"],
                "title": meta.get("title"),
                "year": meta.get("year"),
                "venue": meta.get("venue"),
                "field": _field_name(field, field_names, row.get("local")),
                "title_notes": title_notes(meta.get("title")),
                "has_emb": meta.get("has_emb"),
            })
        return out

    top = pack(ranked)
    cited = pack(by_cc)
    return {
        "ranked_ids": [row["corpusid"] for row in ranked],
        "top": top,
        "by_citations": cited,
        "same_order": bool(top) and [row["corpusid"] for row in top] == [row["corpusid"] for row in cited],
        "overlap": len({row["corpusid"] for row in top} & {row["corpusid"] for row in cited}),
    }


def cut_flags(themes):
    """`stop` si el top ordenado es el de las citas globales (al menos 5).

    `close` si 8 de 10 coinciden. Es un corte [I] para no seguir solos;
    no es un umbral medido. `RRM_PASSAGES_IGNORE_STOP=1` lo puede saltar.
    """
    stop = any(item.get("same_order") and len(item.get("top") or []) >= 5 for item in themes or [])
    close = any(len(item.get("top") or []) >= 10 and int(item.get("overlap") or 0) >= 8 for item in themes or [])
    errors = [item.get("name") for item in themes or [] if item.get("error")]
    return {"stop": bool(stop), "close": bool(close), "errors": errors}


def union_from_reports(reports, burst_counts=None, limit=2000, ignore_stop=False):
    """Arma la lista de ids. No baja nada. Rechaza el corte si `stop` o `close`."""
    flags = cut_flags(reports)
    if flags["errors"] and not ignore_stop:
        raise RuntimeError(
            f"E0 dejó temas sin semillas: {', '.join(map(str, flags['errors']))}. "
            "No se arma la unión. Corrige el ancla (RRM_PASSAGES_ANCHORS) o RRM_PASSAGES_IGNORE_STOP=1."
        )
    if (flags["stop"] or flags["close"]) and not ignore_stop:
        raise RuntimeError(
            "E0 marcó el top parecido al de citas globales "
            f"(stop={flags['stop']} close={flags['close']}). "
            "No se arma la unión. RRM_PASSAGES_IGNORE_STOP=1 la permite si Franklin parte el tema."
        )
    counts = list(burst_counts) if burst_counts is not None else [None] * len(reports or [])
    quotas, source = quotas_for(counts, limit)
    ranked = [list(item.get("ranked_ids") or []) for item in reports or []]
    ids, took = union_papers(ranked, quotas, limit)
    return {
        "ids": ids,
        "quotas": quotas,
        "took": took,
        "quota_source": source,
        "flags": flags,
    }
