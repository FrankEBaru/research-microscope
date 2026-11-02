"""Puntaje de un vecindario sobre el CSR de salida.

score(c) suma 1 por cada semilla distinta que cita a c. Una arista que no
sale de una semilla no entra. El ancla entra solo si otra semilla la cita.
Orden: puntaje descendente, citationcount descendente, corpusid ascendente.
"""

import numpy as np

from rrm.search.burst import gather_out, order_candidates
from rrm.search.graph import locate


def dedupe_ids(ids):
    out = []
    seen = set()
    for raw in ids or []:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def seed_locals(graph, seed_ids):
    """Índices locales de semillas que están en graph.ids. Esos ids van ordenados."""
    ids = np.asarray(dedupe_ids(seed_ids), dtype=np.int64)
    if ids.size == 0:
        return np.zeros(0, dtype=np.int64)
    hit, pos = locate(graph.ids, ids)
    chosen = []
    seen = set()
    for ok, local in zip(hit.tolist(), pos.tolist()):
        if not ok:
            continue
        local = int(local)
        if local in seen:
            continue
        seen.add(local)
        chosen.append(local)
    return np.asarray(chosen, dtype=np.int64)


def score_cited(graph, seed_local):
    """Cuenta semillas distintas por nodo citado. Devuelve (locales, puntajes)."""
    seed_local = np.asarray(seed_local, dtype=np.int64).reshape(-1)
    empty_i = np.zeros(0, dtype=np.int64)
    empty_s = np.zeros(0, dtype=np.float64)
    if seed_local.size == 0:
        return empty_i, empty_s
    cited, owner = gather_out(graph.out_indptr, graph.out_indices, seed_local)
    if cited.size == 0:
        return empty_i, empty_s
    pair = np.unique(np.stack([np.asarray(cited), np.asarray(owner)], axis=1), axis=0)
    cited = pair[:, 0]
    uniq, inv = np.unique(cited, return_inverse=True)
    scores = np.bincount(inv).astype(np.float64)
    return uniq, scores


def rank_neighborhood(graph, seed_ids, citation_counts, n=None):
    """Papers con puntaje > 0, el mejor primero.

    `citation_counts` va alineado con `graph.ids` (la columna `cc` de node_meta).
    """
    cc = np.asarray(citation_counts)
    local = seed_locals(graph, seed_ids)
    uniq, scores = score_cited(graph, local)
    if uniq.size == 0:
        return []
    keep = scores > 0
    uniq = uniq[keep]
    scores = scores[keep]
    if uniq.size == 0:
        return []
    ordered, ordered_scores = order_candidates(uniq, scores, graph.ids, cc, n)
    rows = []
    for local_i, score in zip(ordered.tolist(), ordered_scores.tolist()):
        local_i = int(local_i)
        rows.append({
            "local": local_i,
            "corpusid": int(graph.ids[local_i]),
            "score": int(round(float(score))),
            "citationcount": int(cc[local_i]),
        })
    return rows


def rank_by_citations(rows):
    """Los mismos candidatos, por citationcount descendente y corpusid ascendente."""
    return sorted(
        list(rows or []),
        key=lambda row: (-int(row.get("citationcount") or 0), int(row["corpusid"])),
    )


def assemble_seeds(anchor, neighbor_ids, k=200):
    """El ancla primero y hasta k vecinos distintos. Un id repetido cuenta una vez."""
    out = []
    seen = set()
    if anchor is not None and str(anchor).strip() != "":
        cid = int(anchor)
        out.append(cid)
        seen.add(cid)
    room = int(k)
    for raw in neighbor_ids or []:
        if room <= 0:
            break
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        room -= 1
    return out
