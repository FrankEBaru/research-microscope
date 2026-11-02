"""Grupos k-means sobre SPECTER2 y donación por capas.
El default de la base. Las anclas siguen en `cut.py` y solo corren con
`RRM_PASSAGES_SELECT=anchors`. Aquí no se baja ningún e-print.
Se entrena k-means en una muestra y se asignan todos los vectores. El
score de un candidato es local / log(2 + citationcount). Solo dona un
candidato con arxiv id. La unión es por capas (`layer_union`).
"""
import numpy as np
from rrm.passages.score import rank_group_arrays
from rrm.passages.union import LIMIT, layer_union, title_notes
N_GROUPS = 2000
TRAIN_N = 300_000
# Cuántos del ranking se miran al buscar arxiv id. Más allá no dona en esta pasada.
DONOR_DEPTH = 2048
DONORS_PER_GROUP = 8
PROBE_N = 10
PROBES = (
    {"name": "attention", "corpusid": 13756489, "title": None, "question": None},
    {
        "name": "gcn",
        "corpusid": 3144218,
        "title": "Semi-Supervised Classification with Graph Convolutional Networks",
        "question": None,
    },
    {
        "name": "icl-linear",
        "corpusid": None,
        "arxiv": "2211.15661",
        "title": "What learning algorithm is in-context learning? Investigations with linear models",
        "question": None,
    },
)

def select_mode(raw):
    """`anchors` conserva el corte viejo. Cualquier otro valor, o vacío, es grupos."""
    if str(raw or "").strip().lower() == "anchors":
        return "anchors"
    return "groups"

def reservoir_extend(buf_ids, buf_vecs, seen, ids, vecs, k, rng):
    """Mete un lote en un reservoir de tamaño k. `seen` es cuántos ya se vieron."""
    ids = np.asarray(ids, dtype=np.int64).reshape(-1)
    vecs = np.asarray(vecs)
    n = int(ids.shape[0])
    seen = int(seen)
    k = int(k)
    if n == 0:
        return buf_ids, buf_vecs, seen
    if vecs.shape[0] != n:
        raise ValueError("ids y vectores no miden lo mismo")
    if buf_ids is None:
        buf_ids = np.zeros(0, dtype=np.int64)
        buf_vecs = np.zeros((0, int(vecs.shape[1])), dtype=np.float32)
        seen = 0
    room = k - int(buf_ids.shape[0])
    if room > 0:
        take_n = min(room, n)
        chunk = np.ascontiguousarray(vecs[:take_n], dtype=np.float32)
        buf_ids = np.concatenate([buf_ids, ids[:take_n]])
        buf_vecs = np.concatenate([buf_vecs, chunk]) if buf_vecs.size else chunk
        ids = ids[take_n:]
        vecs = vecs[take_n:]
        seen += take_n
        n = int(ids.shape[0])
        if n == 0:
            return buf_ids, buf_vecs, seen
    idx = seen + 1 + np.arange(n)
    take = rng.random(n) < (k / idx)
    slots = np.flatnonzero(take)
    if slots.size:
        repl = rng.integers(0, k, size=int(slots.size))
        buf_ids[repl] = ids[slots]
        buf_vecs[repl] = np.ascontiguousarray(vecs[slots], dtype=np.float32)
    return buf_ids, buf_vecs, seen + n

def train_centroids(sample, k, seed=0, niter=12):
    """Centroides L2. faiss.Kmeans en CPU. La muestra tiene que alcanzar a k."""
    import faiss
    sample = np.ascontiguousarray(sample, dtype=np.float32)
    if sample.ndim != 2 or sample.shape[0] == 0:
        raise ValueError("muestra vacía")
    k = min(int(k), int(sample.shape[0]))
    if k < 1:
        raise ValueError("k < 1")
    km = faiss.Kmeans(int(sample.shape[1]), k, niter=int(niter), seed=int(seed), verbose=False, gpu=False)
    km.train(sample)
    return np.ascontiguousarray(km.centroids, dtype=np.float32)

def assign_vectors(centroids, vecs):
    """Índice del centroide más cercano (L2). Vacío si no hay vectores."""
    import faiss
    vecs = np.asarray(vecs)
    if vecs.size == 0:
        return np.zeros(0, dtype=np.int32)
    vecs = np.ascontiguousarray(vecs, dtype=np.float32)
    index = faiss.IndexFlatL2(int(centroids.shape[1]))
    index.add(np.ascontiguousarray(centroids, dtype=np.float32))
    labels = np.empty(vecs.shape[0], dtype=np.int32)
    step = 100_000
    for start in range(0, vecs.shape[0], step):
        _dist, lab = index.search(vecs[start:start + step], 1)
        labels[start:start + step] = lab.reshape(-1)
    return labels

def seed_document(title, abstract):
    """Texto del corpus SPECTER2: título, un salto de línea, abstract."""
    title = " ".join((title or "").split())
    abstract = " ".join((abstract or "").split())
    if title and abstract:
        return title + "\n" + abstract
    return title or abstract

def nearest_centroid(centroids, vector):
    lab = assign_vectors(centroids, np.asarray(vector, dtype=np.float32).reshape(1, -1))
    return int(lab[0])

def dedupe_labels(ids, labels):
    """Un corpusid, la primera etiqueta. Devuelve ids ordenados y sus labels."""
    ids = np.asarray(ids, dtype=np.int64).reshape(-1)
    labels = np.asarray(labels, dtype=np.int32).reshape(-1)
    if ids.size == 0:
        return ids, labels
    order = np.argsort(ids, kind="mergesort")
    ids = ids[order]
    labels = labels[order]
    _uniq, first = np.unique(ids, return_index=True)
    return ids[first], labels[first]

def group_slices(labels, k):
    """`ordered` de argsort, `starts` y `sizes` por grupo 0..k-1.
    El caller parte sus ids con el mismo argsort: ids[order][start:start+size].
    """
    labels = np.asarray(labels, dtype=np.int32).reshape(-1)
    k = int(k)
    order = np.argsort(labels, kind="mergesort")
    ordered = labels[order]
    sizes = np.bincount(ordered, minlength=k).astype(np.int64, copy=False)
    if sizes.size > k:
        sizes = sizes[:k]
    starts = np.zeros(k, dtype=np.int64)
    if k > 1:
        np.cumsum(sizes[:-1], out=starts[1:])
    return order, starts, sizes

def partition_stats(sizes):
    sizes = np.asarray(sizes, dtype=np.int64).reshape(-1)
    if sizes.size == 0:
        return {"k": 0, "min": 0, "median": 0, "max": 0, "empty": 0}
    return {
        "k": int(sizes.size),
        "min": int(sizes.min()),
        "median": float(np.median(sizes)),
        "max": int(sizes.max()),
        "empty": int((sizes == 0).sum()),
        "nonempty_min": int(sizes[sizes > 0].min()) if np.any(sizes > 0) else 0,
    }

def label_of(sorted_ids, labels, corpusid):
    """Etiqueta de un corpusid. None si no está en la partición."""
    sorted_ids = np.asarray(sorted_ids, dtype=np.int64)
    pos = int(np.searchsorted(sorted_ids, int(corpusid)))
    if pos >= sorted_ids.size or int(sorted_ids[pos]) != int(corpusid):
        return None
    return int(labels[pos])

def in_sorted(ids, sorted_ids):
    ids = np.asarray(ids, dtype=np.int64).reshape(-1)
    sorted_ids = np.asarray(sorted_ids, dtype=np.int64).reshape(-1)
    if ids.size == 0:
        return np.zeros(0, dtype=bool)
    if sorted_ids.size == 0:
        return np.zeros(ids.size, dtype=bool)
    pos = np.searchsorted(sorted_ids, ids)
    pos = np.minimum(pos, sorted_ids.size - 1)
    return sorted_ids[pos] == ids

def select_donors(corpus_ordered, display_sorted, extra, keep=DONORS_PER_GROUP, depth=DONOR_DEPTH, titled=None):
    """Mejores `keep` con arxiv id y con título, en el orden del ranking.
    Sin título no dona y no entra a `pending`: es ruido de metadata.
    `extra` son corpusid que el dataset papers confirmó con arxiv.
    """
    ids = np.asarray(corpus_ordered, dtype=np.int64).reshape(-1)[: int(depth)]
    extra = extra or set()
    donors = []
    pending = []
    if ids.size == 0:
        return donors, pending
    known = in_sorted(ids, display_sorted)
    has_title = in_sorted(ids, titled) if titled is not None else np.ones(ids.size, dtype=bool)
    for cid, is_known, titled_ok in zip(ids.tolist(), known.tolist(), has_title.tolist()):
        if not titled_ok:
            continue
        cid = int(cid)
        if is_known or cid in extra:
            donors.append(cid)
            if len(donors) >= int(keep):
                break
            continue
        pending.append(cid)
    return donors, pending

def keep_titled(corpus, *rest, titled):
    """Quita ids sin título. `rest` sigue el mismo orden que `corpus`."""
    corpus = np.asarray(corpus)
    if titled is None or corpus.size == 0:
        return (corpus, *rest)
    mask = in_sorted(corpus, titled)
    return (corpus[mask], *(np.asarray(col)[mask] for col in rest))

def citation_like(corpus, citations, n=PROBE_N):
    """¿El top por score es el top por citas? `corpus` ya viene ordenado por score."""
    corpus = np.asarray(corpus, dtype=np.int64).reshape(-1)
    citations = np.asarray(citations).reshape(-1)
    n_have = int(min(int(n), corpus.size))
    if n_have == 0:
        return False, 0, 0
    order = np.lexsort((corpus, -citations.astype(np.int64, copy=False)))
    top = corpus[:n_have]
    by_cc = corpus[order][:n_have]
    overlap = len(set(top.tolist()) & set(by_cc.tolist()))
    same = n_have >= 5 and np.array_equal(top, by_cc)
    return bool(same), int(overlap), n_have

def would_split_group(same, overlap, n_have):
    """La regla del ticket: el top parece el de citas globales."""
    return (bool(same) and int(n_have) >= 5) or (int(n_have) >= 10 and int(overlap) >= 8)

def seeds_of(ordered_ids, starts, sizes, group):
    group = int(group)
    if group < 0 or group >= len(starts):
        return np.zeros(0, dtype=np.int64)
    start = int(starts[group])
    size = int(sizes[group])
    return np.asarray(ordered_ids[start:start + size], dtype=np.int64)

def _finish_donors(ranked, display_sorted, extra, keep, depth, titled=None):
    lists = []
    pending = []
    seen_pending = set()
    with_donor = 0
    empty_local = 0
    for corpus in ranked:
        if corpus is None or len(corpus) == 0:
            lists.append([])
            empty_local += 1
            continue
        donors, need = select_donors(corpus, display_sorted, extra, keep=keep, depth=depth, titled=titled)
        lists.append(donors)
        if donors:
            with_donor += 1
        for cid in need:
            if cid not in seen_pending:
                seen_pending.add(cid)
                pending.append(cid)
    k = len(ranked)
    return {
        "lists": lists,
        "pending": pending,
        "ranked": ranked,
        "groups_with_donor": with_donor,
        "groups_without_donor": k - with_donor,
        "groups_without_local": empty_local,
    }

def donor_lists(graph, cc, ordered_ids, starts, sizes, display_sorted, extra, keep=DONORS_PER_GROUP, depth=DONOR_DEPTH, titled=None):
    """Una lista de corpusid por grupo, solo con arxiv y con título.
    `would_split` cuenta grupos cuyo top, ya sin nodos sin título, parece
    el top por citas globales. No parte la partición.
    """
    ranked = []
    would = 0
    k = int(len(starts))
    for group in range(k):
        if group and group % 250 == 0:
            print(f"donantes {group}/{k}", flush=True)
        seeds = seeds_of(ordered_ids, starts, sizes, group)
        if seeds.size == 0:
            ranked.append(np.zeros(0, dtype=np.int64))
            continue
        corpus, _counts, _scores, citations, _nodes = rank_group_arrays(graph, seeds, cc)
        corpus, citations = keep_titled(corpus, citations, titled=titled)
        same, overlap, n_have = citation_like(corpus, citations)
        if would_split_group(same, overlap, n_have):
            would += 1
        ranked.append(np.asarray(corpus[: int(depth)], dtype=np.int64))
    out = _finish_donors(ranked, display_sorted, extra, keep, depth, titled=titled)
    out["would_split"] = would
    return out

def donors_from_ranked(ranked, display_sorted, extra, keep=DONORS_PER_GROUP, depth=DONOR_DEPTH, titled=None):
    """Misma donación, sin tocar el grafo. Sirve tras el lookup de arxiv id."""
    return _finish_donors(ranked, display_sorted, extra, keep, depth, titled=titled)

def field_name(field, names, node):
    if field is None or node is None:
        return None
    node = int(node)
    if node < 0 or node >= len(field):
        return None
    code = int(field[node])
    if names is None or code < 0 or code >= len(names):
        return None
    return str(names[code])

def _pack(corpus, counts, scores, citations, nodes, n, meta_of, field, names):
    rows = []
    n = min(int(n), int(corpus.size))
    for i in range(n):
        cid = int(corpus[i])
        meta = meta_of(cid) if meta_of else {}
        meta = meta or {}
        rows.append({
            "corpusid": cid,
            "title": meta.get("title"),
            "year": meta.get("year"),
            "local": int(counts[i]),
            "citationcount": int(citations[i]),
            "score": round(float(scores[i]), 6),
            "field": field_name(field, names, nodes[i]),
            "title_notes": title_notes(meta.get("title")),
            "arxiv_id": meta.get("arxiv_id") or "",
        })
    return rows

def probe_group(graph, cc, seed_ids, meta_of, field=None, field_names=None, n=PROBE_N, titled=None):
    """Top n del grupo y, al lado, el top n por citas globales de esos candidatos.
    Un candidato sin título no entra en ninguno de los dos tops.
    """
    corpus, counts, scores, citations, nodes = rank_group_arrays(graph, seed_ids, cc)
    corpus, counts, scores, citations, nodes = keep_titled(
        corpus, counts, scores, citations, nodes, titled=titled,
    )
    top = _pack(corpus, counts, scores, citations, nodes, n, meta_of, field, field_names)
    if corpus.size == 0:
        by_cc = []
    else:
        order = np.lexsort((corpus, -citations.astype(np.int64, copy=False)))
        by_cc = _pack(
            corpus[order], counts[order], scores[order], citations[order], nodes[order],
            n, meta_of, field, field_names,
        )
    top_ids = [row["corpusid"] for row in top]
    cc_ids = [row["corpusid"] for row in by_cc]
    return {
        "top": top,
        "by_citations": by_cc,
        "same_order": bool(top_ids) and top_ids == cc_ids,
        "overlap": len(set(top_ids) & set(cc_ids)),
        "candidates": int(corpus.size),
    }

def ivf_labels(index):
    """Etiqueta de lista IVF por fila de `index`, en el orden en que se agregaron."""
    import faiss
    n = int(index.ntotal)
    labels = np.full(n, -1, dtype=np.int32)
    inv = index.invlists
    for i in range(int(index.nlist)):
        size = int(inv.list_size(i))
        if size <= 0:
            continue
        raw = np.array(faiss.rev_swig_ptr(inv.get_ids(i), size), copy=True)
        raw = raw[(raw >= 0) & (raw < n)]
        labels[raw] = i
    return labels

def rows_of_list(labels, list_id):
    return np.flatnonzero(np.asarray(labels) == int(list_id))

def union_from_lists(lists, limit=LIMIT):
    """Unión por capas más el conteo de grupos que donaron en cada capa."""
    body = layer_union(lists, limit=limit)
    body["groups"] = len(list(lists or []))
    body["groups_that_donate"] = sum(1 for ids in (lists or []) if ids)
    return body

def titled_ids_from_table(table):
    """corpusid ordenados con título no vacío. Sin fila o sin título no entran."""
    import pyarrow.compute as pc
    if table is None or "title" not in table.column_names:
        return None
    if table.num_rows == 0:
        return np.zeros(0, dtype=np.int64)
    filled = pc.fill_null(table.column("title"), "")
    mask = pc.not_equal(filled, "")
    ids = table.column("corpusid").filter(mask)
    if ids.length() == 0:
        return np.zeros(0, dtype=np.int64)
    return np.unique(np.asarray(ids.to_numpy(zero_copy_only=False), dtype=np.int64))

def corpus_by_arxiv(table, arxiv_id):
    """corpusid de un arXiv id en la columna `arxiv`. None si no está.
    Acepta el id con o sin versión (`2211.15661v2`).
    """
    import pyarrow.compute as pc
    from rrm.search.display import canon_arxiv
    want = canon_arxiv(arxiv_id)
    if not want or table is None or table.num_rows == 0 or "arxiv" not in table.column_names:
        return None
    filled = pc.fill_null(table.column("arxiv"), "")
    exact = table.column("corpusid").filter(pc.equal(filled, want))
    if exact.length():
        return int(exact[0].as_py())
    rough = pc.match_substring(filled, want)
    if not pc.any(rough).as_py():
        return None
    subset = table.filter(rough)
    for cid, raw in zip(subset.column("corpusid").to_pylist(), subset.column("arxiv").to_pylist()):
        if canon_arxiv(raw) == want:
            return int(cid)
    return None

def corpus_by_title(table, title):
    """Primer corpusid cuyo título contiene el texto, ya en minúsculas."""
    import pyarrow.compute as pc
    needle = " ".join((title or "").lower().split())
    if len(needle) < 12 or table is None or table.num_rows == 0 or "title" not in table.column_names:
        return None
    low = pc.utf8_lower(pc.fill_null(table.column("title"), ""))
    ids = table.column("corpusid").filter(pc.match_substring(low, needle))
    if ids.length() == 0:
        return None
    return int(ids[0].as_py())

def resolve_corpus(table, *, corpusid=None, arxiv=None, title=None):
    """Id dado, si no el arXiv, si no el título. No usa FAISS."""
    if corpusid:
        return int(corpusid), "given"
    found = corpus_by_arxiv(table, arxiv) if arxiv else None
    if found is not None:
        return found, "arxiv"
    found = corpus_by_title(table, title) if title else None
    if found is not None:
        return found, "title"
    return None, "none"

def corpus_from_s2(arxiv_id):
    """Un corpusId por arXiv en la API de Semantic Scholar. None si no hay llave o falla.
    Una petición. La llave va en el header y no se imprime.
    """
    import json
    import os
    import urllib.request
    from rrm.search.display import canon_arxiv
    want = canon_arxiv(arxiv_id)
    key = os.environ.get("S2_API_KEY", "").strip()
    if not want or not key:
        return None
    url = f"https://api.semanticscholar.org/graph/v1/paper/ARXIV:{want}?fields=corpusId"
    req = urllib.request.Request(url, headers={"x-api-key": key, "User-Agent": "research-microscope"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as err:
        status = getattr(err, "code", None)
        print(json.dumps({"s2": "fail", "status": status}), flush=True)
        return None
    cid = body.get("corpusId") if isinstance(body, dict) else None
    return int(cid) if cid else None

def arxiv_ids_from_table(table):
    """corpusid ordenados cuya columna `arxiv` no está vacía."""
    import pyarrow.compute as pc
    if table is None or table.num_rows == 0 or "arxiv" not in table.column_names:
        return np.zeros(0, dtype=np.int64)
    filled = pc.fill_null(table.column("arxiv"), "")
    mask = pc.not_equal(filled, "")
    ids = table.column("corpusid").filter(mask)
    if ids.length() == 0:
        return np.zeros(0, dtype=np.int64)
    out = np.asarray(ids.to_numpy(zero_copy_only=False), dtype=np.int64)
    return np.unique(out)

def arxiv_from_external(table, needed_sorted):
    """corpusid → arxiv id para filas cuyo externalids trae ArXiv y está en `needed`."""
    from rrm.search.display import _ext_strings, canon_arxiv
    needed_sorted = np.asarray(needed_sorted, dtype=np.int64).reshape(-1)
    found = {}
    if table is None or table.num_rows == 0 or needed_sorted.size == 0:
        return found
    if "externalids" not in table.column_names or "corpusid" not in table.column_names:
        return found
    ids = np.asarray(table.column("corpusid").to_numpy(zero_copy_only=False), dtype=np.int64)
    keep = np.flatnonzero(in_sorted(ids, needed_sorted))
    if keep.size == 0:
        return found
    values = _ext_strings(table, keep, ("ArXiv", "Arxiv", "arxiv"), canon_arxiv)
    for row, arxiv in zip(keep.tolist(), values):
        if not arxiv:
            continue
        found[int(ids[int(row)])] = arxiv
    return found
