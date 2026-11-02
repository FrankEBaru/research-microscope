"""Entrypoints de Modal para RRM-55. No se ejecutan desde los tests.

Cada etapa exige `RRM_PASSAGES_STAGE` igual al nombre de la etapa. Franklin
la da una por una. El tope en dólares, si lo fija, va en
`RRM_PASSAGES_BUDGET_USD`. Sin esa variable no hay un tope inventado.

Estimados [I], CPU y L4 solamente, tarifas del 2026-10-28 en
`rrm/passages/cost.py`. La memoria no está en esa tarifa.

    RRM_PASSAGES_STAGE=e0 RRM_PASSAGES_BUDGET_USD=1.8 modal run rrm/passages/app.py::e0
    RRM_PASSAGES_STAGE=e1 RRM_PASSAGES_BUDGET_USD=0.4 RRM_PASSAGES_SKIP_CACHED=1 modal run rrm/passages/app.py::e1
    RRM_PASSAGES_STAGE=e2 modal run rrm/passages/app.py::e2
    RRM_PASSAGES_STAGE=e3 modal run rrm/passages/app.py::e3
    RRM_PASSAGES=1 RRM_PASSAGES_STAGE=e4 modal run rrm/search/serve.py::passages_query --symbol '\\sqrt{d_k}'

E0 lee el grafo que ya está en el volumen. No baja e-prints.
E1 baja 5, E2 llega a 50 y mide el embed, E3 completa 2,000.
E4 consulta desde BurstSearch, que carga `passages/` solo con el flag.
Al terminar, Modal queda parado: estas funciones no dejan un contenedor caliente.
`RRM_PASSAGES_IGNORE_STOP=1` sigue después de un top parecido a las citas globales.
`RRM_PASSAGES_BREAK_LOCK=1` levanta un harvest.lock viejo. Una sola máquina.
`RRM_PASSAGES_RETRY=1` rehace las filas de los ids de la etapa aunque ya existan.
`RRM_PASSAGES_SKIP_CACHED=1` toma los primeros `n` de la unión que no están en
el caché del lector y tienen arxiv id (prueba de descarga real).
`RRM_PASSAGES_LICENSE=1` pide la licencia por OAI (apagado por defecto).
`RRM_PASSAGES_SELECT=anchors` usa el corte viejo. El default es k-means y capas.
`RRM_PASSAGES_REUSE_GROUPS=1` reusa group_ids.npy si ya se entrenó.
`RRM_PASSAGES_SPLIT=1` parte de verdad un grupo cuyo top parece el de citas. Sin eso solo se cuenta.
`RRM_PASSAGES_EXTRA_IDS=1,2` suma ids que ya están en el caché latex (sin e-print).
"""

import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 2:
    ROOT = _HERE.parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

import modal

from rrm.passages.cost import stage_estimate

MOUNT = "/s2"
RELEASE = "2026-10-20"
CPU_USD_PER_CORE_S = 0.0000131

cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "pyarrow")
    .add_local_python_source("rrm")
)
index_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cpu")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "sentencepiece")
    .add_local_python_source("rrm")
)
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch")
    .pip_install("numpy", "pyarrow", "faiss-cpu", "transformers", "adapters", "sentencepiece")
    .add_local_python_source("rrm")
)

app = modal.App("rrm-passages")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)

# Modal no pasa el entorno local al contenedor. Estas variables viajan como
# Secret.from_dict, tomadas del shell que lanza `modal run`.
# S2_API_KEY, si está, va solo en el header de una petición y no se imprime.
_STAGE_KEYS = (
    "RRM_PASSAGES_STAGE",
    "RRM_PASSAGES_BUDGET_USD",
    "RRM_PASSAGES_IGNORE_STOP",
    "RRM_PASSAGES_BREAK_LOCK",
    "RRM_PASSAGES_RETRY",
    "RRM_PASSAGES_LICENSE",
    "RRM_PASSAGES_SKIP_CACHED",
    "RRM_PASSAGES_EXTRA_IDS",
    "RRM_PASSAGES_ANCHORS",
    "RRM_PASSAGES_SELECT",
    "RRM_PASSAGES_REUSE_GROUPS",
    "RRM_PASSAGES_SPLIT",
    "RRM_PASSAGES_K",
    "RRM_PASSAGES_TRAIN_N",
    "RRM_ARXIV_CONTACT",
    "S2_API_KEY",
)
stage_env = modal.Secret.from_dict({key: os.environ[key] for key in _STAGE_KEYS if os.environ.get(key)})


def _require(stage):
    allowed = os.environ.get("RRM_PASSAGES_STAGE", "").strip()
    if allowed != stage:
        raise SystemExit(
            f"{stage} no corre sin RRM_PASSAGES_STAGE={stage}. Franklin da el permiso por etapa."
        )


def _budget():
    raw = os.environ.get("RRM_PASSAGES_BUDGET_USD", "").strip()
    if not raw:
        return None
    return float(raw)


def _root():
    return Path(MOUNT) / RELEASE


def _passages():
    return _root() / "passages"


def _report(stage, started, *, cpu, gpu_l4_seconds=0, extra=None):
    elapsed = round(time.time() - started, 3)
    body = {
        "stage": stage,
        "seconds": elapsed,
        "usd_cpu_est": elapsed * cpu * CPU_USD_PER_CORE_S,
        "usd_note": "[I] CPU de rrm/reader/serve.py; la memoria no entra. No es el costo medido de Modal.",
        "plan": stage_estimate(stage),
    }
    if gpu_l4_seconds:
        body["gpu_l4_seconds"] = gpu_l4_seconds
    if extra:
        body.update(extra)
    print(json.dumps(body, ensure_ascii=False), flush=True)
    return body


def _load_graph():
    import numpy as np

    from rrm.search.graph import Graph

    dest = _root() / "index_ext"
    return Graph(
        np.load(dest / "graph_ids.npy", mmap_mode="r"),
        np.load(dest / "out_indptr.npy", mmap_mode="r"),
        np.load(dest / "out_indices.npy", mmap_mode="r"),
        np.load(dest / "in_indptr.npy", mmap_mode="r"),
        np.load(dest / "in_indices.npy", mmap_mode="r"),
    )


def _neighbors(index, faiss_ids, anchor, k):
    from rrm.search.faissutil import search_vectors, vector_at

    vec = vector_at(index, faiss_ids, int(anchor))
    if vec is None:
        return []
    hits = search_vectors(index, faiss_ids, vec, int(k) + 1)
    return [cid for cid, _dist in hits if int(cid) != int(anchor)][: int(k)]


E0_CPU = 4


def _env_int(name, default, lo, hi):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    val = int(raw)
    if val < lo or val > hi:
        raise SystemExit(f"{name}={val} fuera de [{lo}, {hi}]")
    return val


def _save_npy(path, array):
    import numpy as np

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".partial.npy")
    np.save(tmp, array)
    os.replace(tmp, path)


def _iter_embeddings(path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from rrm.search.faissutil import vectors_from_table

    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(columns=["corpusid", "vector"], batch_size=65536):
        ids, vecs = vectors_from_table(pa.Table.from_batches([batch]))
        if len(ids):
            yield ids, vecs


@app.function(image=index_image, volumes={MOUNT: vol}, secrets=[stage_env], cpu=E0_CPU, memory=32768, timeout=6 * 3600, max_containers=1)
def e0_run():
    """Grupos k-means, o anclas si RRM_PASSAGES_SELECT=anchors. Solo lectura."""
    from rrm.passages.groups import select_mode

    _require("e0")
    if select_mode(os.environ.get("RRM_PASSAGES_SELECT")) == "anchors":
        return _e0_anchors()
    return _e0_groups()


def _e0_anchors():
    """Tres vecindarios de anclas. Solo lectura. Escribe passages/e0.json."""
    _require("e0")
    import numpy as np

    from rrm.passages.cut import THEMES, apply_anchor_overrides, cut_flags, resolve_seeds, theme_report
    from rrm.passages.meta import meta_from_files
    from rrm.search.display import PaperLookup
    from rrm.search.encode import QueryEncoder
    from rrm.search.store import load_display, load_faiss

    started = time.time()
    root = _root()
    graph = _load_graph()
    meta = np.load(root / "index_ext" / "node_meta.npz", mmap_mode="r", allow_pickle=True)
    cc = np.maximum(np.asarray(meta["cc"]), 0)
    field = np.asarray(meta["field"])
    names = np.asarray(meta["field_names"])
    index, faiss_ids = load_faiss(root / "index")
    display = load_display(root / "index")
    lookup = PaperLookup(display)
    encoder = None

    def title_hit(title):
        return lookup.resolve(title)

    def first_hit(question):
        nonlocal encoder
        if encoder is None:
            encoder = QueryEncoder()
            encoder.load()
        # El índice guarda título+abstract con proximidad. La pregunta del tema
        # se embebe en ese mismo espacio; el burst corto sigue en adhoc.
        vec = encoder.encode_proximity([question])[0]
        from rrm.search.faissutil import search_vectors

        hits = search_vectors(index, faiss_ids, vec, 1)
        return hits[0][0] if hits else None

    themes = apply_anchor_overrides(THEMES, os.environ.get("RRM_PASSAGES_ANCHORS", ""))
    reports = []
    display_path = root / "index" / "display.parquet"
    ext_path = root / "index_ext" / "display_ext.parquet"

    def meta_of(cid):
        return meta_from_files(cid, display_path, ext_path)

    def text_neighbors(text):
        nonlocal encoder
        if encoder is None:
            encoder = QueryEncoder()
            encoder.load()
        from rrm.search.faissutil import search_vectors

        vec = encoder.encode_proximity([text.strip() + "\n"])[0]
        return [cid for cid, _dist in search_vectors(index, faiss_ids, vec, 201)]

    def text_of(cid):
        # Solo el título: display no trae abstract. El vector de papers es título+abstract.
        return ((meta_of(cid) or {}).get("title") or "").strip()

    for spec in themes:
        seeds = resolve_seeds(
            spec,
            neighbors_of=lambda anchor: _neighbors(index, faiss_ids, anchor, 200),
            first_hit=first_hit,
            title_hit=title_hit,
            text_neighbors=text_neighbors,
            text_of=text_of,
        )
        if not seeds["seeds"]:
            reports.append({**seeds, "top": [], "by_citations": [], "ranked_ids": [], "same_order": False, "overlap": 0})
            continue
        report = theme_report(graph, cc, seeds["seeds"], meta_of, field=field, field_names=names)
        report.update({key: seeds.get(key) for key in ("name", "anchor", "seeds", "neighbors", "how", "via", "error")})
        report["seeds"] = len(seeds["seeds"])
        reports.append(report)

    flags = cut_flags(reports)
    body = {
        "select": "anchors",
        "themes": reports,
        **flags,
        "quota_note": "cupos parejos [I] si no hay burst_counts.json",
    }
    dest = _passages()
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "e0.json").write_text(json.dumps(body), encoding="utf-8")
    vol.commit()
    return _report("e0", started, cpu=E0_CPU, extra={
        "stop": flags["stop"], "close": flags["close"], "errors": flags["errors"], "themes": len(reports),
        "via": {item.get("name"): item.get("via") for item in reports},
        "neighbors": {item.get("name"): item.get("neighbors") for item in reports},
    })


def _e0_groups():
    """k-means, puntaje penalizado, unión por capas y sonda. Sin e-prints."""
    import gc

    import numpy as np

    from rrm.passages.cost import over_budget
    from rrm.passages.cut import cut_flags
    from rrm.passages.groups import (
        DONOR_DEPTH,
        N_GROUPS,
        PROBES,
        TRAIN_N,
        arxiv_from_external,
        arxiv_ids_from_table,
        assign_vectors,
        corpus_from_s2,
        dedupe_labels,
        donor_lists,
        donors_from_ranked,
        group_slices,
        ivf_labels,
        label_of,
        nearest_centroid,
        partition_stats,
        probe_group,
        resolve_corpus,
        rows_of_list,
        seeds_of,
        titled_ids_from_table,
        train_centroids,
        union_from_lists,
    )
    from rrm.passages.meta import meta_from_files
    from rrm.search.store import load_faiss, part_names, read_capped

    started = time.time()
    budget = _budget()
    root = _root()
    dest = _passages()
    dest.mkdir(parents=True, exist_ok=True)
    k = _env_int("RRM_PASSAGES_K", N_GROUPS, 2, 4096)
    train_n = _env_int("RRM_PASSAGES_TRAIN_N", TRAIN_N, 200_000, 500_000)
    emb_dir = root / "embeddings-specter_v2"
    names = part_names(emb_dir)
    if not names:
        raise SystemExit(f"no hay shards en {emb_dir}")

    def _guard(phase):
        if over_budget(time.time() - started, E0_CPU, budget):
            raise SystemExit(f"e0 llegó al tope en {phase} (RRM_PASSAGES_BUDGET_USD={budget})")

    import faiss

    faiss.omp_set_num_threads(E0_CPU)
    ids_path, lab_path, cen_path = dest / "group_ids.npy", dest / "group_labels.npy", dest / "centroids.npy"
    reuse = os.environ.get("RRM_PASSAGES_REUSE_GROUPS") == "1"
    train_s = assign_s = 0.0
    if reuse and ids_path.is_file() and lab_path.is_file() and cen_path.is_file():
        sorted_ids = np.load(ids_path)
        labels = np.load(lab_path)
        centroids = np.load(cen_path)
        print(json.dumps({"reuse_groups": True, "rows": int(sorted_ids.size), "k": int(centroids.shape[0])}), flush=True)
    else:
        rng = np.random.default_rng(0)
        from rrm.passages.groups import reservoir_extend

        buf_ids = buf_vecs = None
        seen = 0
        t0 = time.time()
        for name in names:
            _guard("muestra")
            for shard_ids, shard_vecs in _iter_embeddings(emb_dir / name):
                buf_ids, buf_vecs, seen = reservoir_extend(buf_ids, buf_vecs, seen, shard_ids, shard_vecs, train_n, rng)
            print(json.dumps({"sample_shard": name, "seen": seen, "buf": 0 if buf_ids is None else int(buf_ids.size)}), flush=True)
        if buf_vecs is None or buf_vecs.shape[0] < k:
            raise SystemExit(f"muestra {0 if buf_vecs is None else buf_vecs.shape[0]} < k={k}")
        centroids = train_centroids(buf_vecs, k, seed=0, niter=12)
        train_s = round(time.time() - t0, 3)
        print(json.dumps({"train_seconds": train_s, "train_rows": int(buf_vecs.shape[0]), "k": int(centroids.shape[0])}), flush=True)
        del buf_ids, buf_vecs
        gc.collect()
        t1 = time.time()
        id_chunks, lab_chunks = [], []
        for name in names:
            _guard("asignación")
            n_shard = 0
            for shard_ids, shard_vecs in _iter_embeddings(emb_dir / name):
                id_chunks.append(np.asarray(shard_ids, dtype=np.int64))
                lab_chunks.append(assign_vectors(centroids, shard_vecs))
                n_shard += len(shard_ids)
            print(json.dumps({"assign_shard": name, "rows": n_shard}), flush=True)
        sorted_ids, labels = dedupe_labels(np.concatenate(id_chunks), np.concatenate(lab_chunks))
        del id_chunks, lab_chunks
        assign_s = round(time.time() - t1, 3)
        _save_npy(ids_path, sorted_ids)
        _save_npy(lab_path, labels)
        _save_npy(cen_path, centroids)
        vol.commit()
        print(json.dumps({"assign_seconds": assign_s, "vectors": int(sorted_ids.size)}), flush=True)

    _guard("sonda")
    k = int(centroids.shape[0])
    order, starts, sizes = group_slices(labels, k)
    ordered_ids = sorted_ids[order]
    index, faiss_ids = load_faiss(root / "index")
    faiss_ids = np.asarray(faiss_ids, dtype=np.int64)
    ivf = ivf_labels(index)
    encoder = {"obj": None}

    def _encoder():
        if encoder["obj"] is None:
            from rrm.search.encode import QueryEncoder

            encoder["obj"] = QueryEncoder()
            encoder["obj"].load()
        return encoder["obj"]

    def encode(text):
        return _encoder().encode_proximity([text.strip() + "\n"])[0]

    display_path = root / "index" / "display.parquet"
    ext_path = root / "index_ext" / "display_ext.parquet"
    import pyarrow.parquet as pq

    def _table(path, columns):
        if not path.is_file():
            return None
        have = [col for col in columns if col in pq.read_schema(path).names]
        if "corpusid" not in have:
            return None
        return pq.read_table(path, columns=have)

    display = _table(display_path, ["corpusid", "arxiv", "title"])
    ext = _table(ext_path, ["corpusid", "title"])
    titled_parts = [part for part in (titled_ids_from_table(display), titled_ids_from_table(ext)) if part is not None]
    titled = np.unique(np.concatenate(titled_parts)) if titled_parts else None
    display_sorted = arxiv_ids_from_table(display) if display is not None else np.zeros(0, dtype=np.int64)
    print(json.dumps({
        "titled": None if titled is None else int(titled.size),
        "arxiv_known": int(display_sorted.size),
    }), flush=True)

    def meta_of(cid):
        return meta_from_files(cid, display_path, ext_path)

    specs = []
    for spec in PROBES:
        item = dict(spec)
        cid, how = resolve_corpus(
            display, corpusid=item.get("corpusid"), arxiv=item.get("arxiv"), title=item.get("title"),
        )
        if cid is None:
            cid, how = resolve_corpus(ext, arxiv=item.get("arxiv"), title=item.get("title"))
        if cid is None and item.get("arxiv"):
            cid = corpus_from_s2(item["arxiv"])
            how = "s2" if cid else "none"
        item["corpusid"] = cid
        item["how"] = how
        specs.append(item)
    del display, ext

    def locate(spec):
        cid = spec.get("corpusid")
        if cid is None:
            return None, "none", None
        cid = int(cid)
        lab = label_of(sorted_ids, labels, cid)
        if lab is not None:
            return lab, "vector", None
        text = (meta_of(cid) or {}).get("title") or spec.get("title") or spec.get("question") or ""
        if not text:
            return None, "none", None
        vec = encode(text)
        return nearest_centroid(centroids, vec), "text", vec

    ivf_seeds = {}
    for spec in specs:
        cid = spec.get("corpusid")
        if cid is None:
            continue
        hits = np.flatnonzero(faiss_ids == int(cid))
        if hits.size == 0:
            continue
        list_id = int(ivf[int(hits[0])])
        if list_id < 0:
            continue
        ivf_seeds[spec["name"]] = {
            "list": list_id,
            "size": int(np.count_nonzero(ivf == list_id)),
            "seeds": faiss_ids[rows_of_list(ivf, list_id)],
        }
    del index, ivf, faiss_ids
    gc.collect()

    graph = _load_graph()
    meta = np.load(root / "index_ext" / "node_meta.npz", mmap_mode="r", allow_pickle=True)
    cc = np.maximum(np.asarray(meta["cc"]), 0)
    field = np.asarray(meta["field"])
    names_f = np.asarray(meta["field_names"])

    def one_probe(spec, group, via):
        seeds = seeds_of(ordered_ids, starts, sizes, group) if group is not None else np.zeros(0, dtype=np.int64)
        report = probe_group(graph, cc, seeds, meta_of, field=field, field_names=names_f, titled=titled)
        report.update({
            "name": spec["name"],
            "corpusid": spec.get("corpusid"),
            "group": group,
            "group_size": int(sizes[group]) if group is not None and 0 <= group < len(sizes) else 0,
            "how": spec.get("how"),
            "via": via,
            "error": None if seeds.size else "grupo vacío",
        })
        ivf_info = ivf_seeds.get(spec["name"])
        if ivf_info:
            ivf_rep = probe_group(
                graph, cc, ivf_info["seeds"], meta_of, field=field, field_names=names_f, n=5, titled=titled,
            )
            km_ids = [row["corpusid"] for row in report["top"][:5]]
            ivf_ids = [row["corpusid"] for row in ivf_rep["top"]]
            report["ivf"] = {
                "list": ivf_info["list"],
                "size": ivf_info["size"],
                "top5": ivf_rep["top"],
                "same_order": ivf_rep["same_order"],
                "overlap_with_kmeans_top5": len(set(km_ids) & set(ivf_ids)),
            }
        return report

    probes = []
    for spec in specs:
        group, via, _vec = locate(spec)
        if group is None:
            probes.append({
                "name": spec["name"], "corpusid": spec.get("corpusid"), "group": None,
                "top": [], "by_citations": [], "same_order": False, "overlap": 0,
                "error": "sin grupo", "via": via, "how": spec.get("how"),
            })
            continue
        probes.append(one_probe(spec, group, via))
        print(json.dumps({
            "probe": spec["name"], "group": group, "via": via,
            "top1": (probes[-1]["top"][:1] or [None])[0],
        }, ensure_ascii=False), flush=True)

    split_notes = []
    flags = cut_flags(probes)
    # Sin RRM_PASSAGES_SPLIT la regla del ticket solo se cuenta en would_split.
    # No se reentrena ni se reetiqueta la partición guardada.
    do_split = os.environ.get("RRM_PASSAGES_SPLIT") == "1"
    if do_split and (flags["stop"] or flags["close"]) and os.environ.get("RRM_PASSAGES_IGNORE_STOP") != "1":
        from rrm.passages.groups import in_sorted

        for probe in list(probes):
            if not (probe.get("same_order") or (len(probe.get("top") or []) >= 10 and int(probe.get("overlap") or 0) >= 8)):
                continue
            group = probe.get("group")
            if group is None:
                continue
            member_ids = seeds_of(ordered_ids, starts, sizes, group)
            if member_ids.size < 2:
                continue
            _guard("partir grupo")
            wanted = np.unique(member_ids)
            got_i, got_v = [], []
            for name in names:
                for shard_ids, shard_vecs in _iter_embeddings(emb_dir / name):
                    mask = in_sorted(shard_ids, wanted)
                    if not np.any(mask):
                        continue
                    got_i.append(np.asarray(shard_ids, dtype=np.int64)[mask])
                    got_v.append(np.ascontiguousarray(shard_vecs[mask], dtype=np.float32))
            if not got_i:
                continue
            part_ids = np.concatenate(got_i)
            part_vecs = np.concatenate(got_v)
            if part_vecs.shape[0] > 200_000:
                pick = np.random.default_rng(1).choice(part_vecs.shape[0], 200_000, replace=False)
                sample = part_vecs[pick]
            else:
                sample = part_vecs
            child = train_centroids(sample, 2, seed=1, niter=10)
            sub = assign_vectors(child, part_vecs)
            new_label = int(labels.max()) + 1
            pos = np.searchsorted(sorted_ids, part_ids)
            valid = (pos < sorted_ids.size) & (sorted_ids[np.minimum(pos, sorted_ids.size - 1)] == part_ids)
            labels[pos[valid & (sub == 1)]] = new_label
            split_notes.append({"group": int(group), "new_group": new_label, "moved": int((sub == 1).sum())})
        if split_notes:
            order, starts, sizes = group_slices(labels, int(labels.max()) + 1)
            ordered_ids = sorted_ids[order]
            k = int(labels.max()) + 1
            probes = []
            for spec in specs:
                group, via, _vec = locate(spec)
                probes.append(one_probe(spec, group, via) if group is not None else {
                    "name": spec["name"], "error": "sin grupo", "top": [], "same_order": False, "overlap": 0,
                })
            flags = cut_flags(probes)

    _guard("donantes")
    donated = donor_lists(
        graph, cc, ordered_ids, starts, sizes, display_sorted, set(), titled=titled,
    )
    would_split = int(donated.get("would_split") or 0)
    found = {}
    papers_dir = root / "papers"
    if donated["pending"] and papers_dir.is_dir():
        needed = np.unique(np.asarray(donated["pending"], dtype=np.int64))
        for name in part_names(papers_dir):
            _guard("arxiv papers")
            table = read_capped(papers_dir / name, ["corpusid", "externalids"], 0)
            found.update(arxiv_from_external(table, needed))
            if len(found) >= needed.size:
                break
        donated = donors_from_ranked(
            donated["ranked"], display_sorted, set(found), titled=titled,
        )
    elif donated["pending"]:
        found = {}
    donated["would_split"] = would_split
    for probe in probes:
        group = probe.get("group")
        donors = donated["lists"][group] if group is not None and 0 <= int(group) < len(donated["lists"]) else []
        probe["arxiv_donor"] = bool(donors)

    ignore = os.environ.get("RRM_PASSAGES_IGNORE_STOP") == "1"
    # Contar grupos parecidos a las citas no vacía la unión. Partir sí puede pararla.
    probe_flags = dict(flags)
    if not do_split:
        flags = {"stop": False, "close": False, "errors": flags["errors"]}
    blocked = bool(flags["stop"] or flags["close"] or flags["errors"]) and not ignore
    if blocked:
        union = {
            "ids": [], "layers": [], "layer_donors": [], "layers_used": 0, "reached": False,
            "quota_source": "layers", "method": "layers", "stopped": True,
            "groups": k, "groups_that_donate": donated["groups_with_donor"],
        }
    else:
        union = union_from_lists(donated["lists"], limit=2000)
        union["stopped"] = False
    amap = {str(cid): found[int(cid)] for cid in union["ids"] if int(cid) in found}
    stats = partition_stats(sizes[:k] if sizes.size >= k else sizes)
    stats.update({
        "vectors": int(sorted_ids.size),
        "train_seconds": train_s,
        "assign_seconds": assign_s,
        "depth": DONOR_DEPTH,
        "groups_with_arxiv_donor": donated["groups_with_donor"],
        "groups_without_arxiv_donor": donated["groups_without_donor"],
        "groups_without_local": donated["groups_without_local"],
        "pending_arxiv_lookup": len(donated["pending"]),
        "arxiv_from_papers": len(found),
        "would_split": would_split,
        "probe_flags": probe_flags,
        "layers_used": union.get("layers_used"),
        "union_n": len(union.get("ids") or []),
        "split": split_notes,
    })
    body = {
        "select": "groups",
        "method": "k-means",
        "ivf_compared": True,
        "selection_note": "La unión usa k-means. Las listas IVF van solo en la sonda, al lado.",
        "probe": probes,
        "partition": stats,
        **flags,
        "split": split_notes,
    }
    (dest / "e0.json").write_text(json.dumps(body), encoding="utf-8")
    (dest / "union.json").write_text(json.dumps(union), encoding="utf-8")
    (dest / "union_arxiv.json").write_text(json.dumps(amap), encoding="utf-8")
    vol.commit()
    return _report("e0", started, cpu=E0_CPU, extra={
        "select": "groups",
        "stop": flags["stop"],
        "close": flags["close"],
        "errors": flags["errors"],
        "vectors": int(sorted_ids.size),
        "union": len(union.get("ids") or []),
        "layers": union.get("layers_used"),
        "train_seconds": train_s,
        "assign_seconds": assign_s,
        "groups_with_arxiv_donor": donated["groups_with_donor"],
        "would_split": would_split,
        "probe_flags": probe_flags,
        "probes": [
            {
                "name": item.get("name"), "corpusid": item.get("corpusid"), "how": item.get("how"),
                "group": item.get("group"), "group_size": item.get("group_size"),
                "arxiv_donor": item.get("arxiv_donor"),
                "top5": [
                    {k: row.get(k) for k in ("title", "local", "citationcount", "score")}
                    for row in (item.get("top") or [])[:5]
                ],
            }
            for item in probes
        ],
        "size_min": stats["min"],
        "size_median": stats["median"],
        "size_max": stats["max"],
    })


def _save_requests(dest, stage, client, error=None):
    """Log de peticiones a arXiv con hora de inicio y gaps. Se guarda aunque la etapa pare."""
    body = {"stage": stage, "error": error, "requests": client.log, "gaps_s": client.gaps(),
            "min_gap_s": min(client.gaps()) if client.gaps() else None}
    (Path(dest) / f"{stage}_requests.json").write_text(json.dumps(body), encoding="utf-8")
    print(json.dumps({"arxiv_requests": len(client.log), "gaps_s": body["gaps_s"], "error": error}), flush=True)


@app.function(image=cpu_image, volumes={MOUNT: vol}, secrets=[stage_env], cpu=1, memory=2048, timeout=8 * 3600, max_containers=1)
def harvest_run(stage: str, n: int):
    """Baja y parsea los primeros `n` de la unión. Reanudable. Sin GPU."""
    _require(stage)
    from rrm.passages.arxiv import ArxivClient, ArxivStopped
    from rrm.passages.cost import over_budget
    from rrm.passages.cut import union_from_reports
    from rrm.passages.harvest import StageBudget, harvest_ids
    from rrm.passages.meta import meta_from_files
    from rrm.passages.store import compile_store

    started = time.time()
    dest = _passages()
    e0_path = dest / "e0.json"
    if not e0_path.is_file():
        raise SystemExit("falta passages/e0.json; E0 no corrió")
    e0 = json.loads(e0_path.read_text(encoding="utf-8"))
    ignore = os.environ.get("RRM_PASSAGES_IGNORE_STOP") == "1"
    if (e0.get("stop") or e0.get("close") or e0.get("errors")) and not ignore:
        raise SystemExit(
            "E0 marcó stop, close o temas sin semillas "
            f"(errors={e0.get('errors')}). No se bajan e-prints. RRM_PASSAGES_IGNORE_STOP=1 si Franklin sigue."
        )
    if e0.get("select") == "anchors":
        counts_path = dest / "burst_counts.json"
        counts = None
        if counts_path.is_file():
            raw_counts = json.loads(counts_path.read_text(encoding="utf-8"))
            if isinstance(raw_counts, dict):
                counts = [raw_counts.get(item.get("name")) for item in e0.get("themes") or []]
            else:
                counts = raw_counts
        try:
            union = union_from_reports(
                e0.get("themes") or [], counts, limit=2000, ignore_stop=ignore,
            )
        except RuntimeError as err:
            raise SystemExit(str(err)) from err
        (dest / "union.json").write_text(json.dumps(union), encoding="utf-8")
    else:
        union_path = dest / "union.json"
        if not union_path.is_file():
            raise SystemExit("falta passages/union.json; E0 de grupos no escribió la unión por capas")
        union = json.loads(union_path.read_text(encoding="utf-8"))
        if union.get("method") != "layers":
            raise SystemExit("union.json no está en orden de capa")
    display_path = _root() / "index" / "display.parquet"
    ext_path = _root() / "index_ext" / "display_ext.parquet"
    papers_root = Path(MOUNT) / "papers"
    amap_path = dest / "union_arxiv.json"
    amap = {}
    if amap_path.is_file():
        amap = {int(key): value for key, value in json.loads(amap_path.read_text(encoding="utf-8")).items()}

    def meta_of(cid):
        return meta_from_files(
            cid, display_path, ext_path, arxiv_lookup=lambda c: amap.get(int(c), ""),
        )

    metas = {}
    if os.environ.get("RRM_PASSAGES_SKIP_CACHED") == "1":
        # Prueba de descarga real: los primeros `n` de la unión sin carpeta en
        # el caché del lector y con arxiv id. No se borra nada del caché.
        # El orden sigue siendo el de las capas.
        ids = []
        for cid in union["ids"]:
            if (papers_root / str(cid)).exists():
                continue
            meta = meta_of(cid)
            if not meta.get("arxiv_id"):
                continue
            metas[cid] = meta
            ids.append(cid)
            if len(ids) >= int(n):
                break
    else:
        ids = union["ids"][: int(n)]
    # Ids extra solo si ya están en el caché latex: rehacen filas y licencia, sin e-print.
    from rrm.passages.cache import latex_cache_ready

    extra = []
    for part in os.environ.get("RRM_PASSAGES_EXTRA_IDS", "").split(","):
        if part.strip().isdigit() and latex_cache_ready(papers_root / part.strip()) and int(part) not in ids:
            extra.append(int(part))
    ids = extra + ids
    for cid in ids:
        if cid not in metas:
            metas[cid] = meta_of(cid)
    budget = _budget()
    client = ArxivClient()
    downloads = {"n": 0}

    def on_paper(result):
        if result.get("downloaded"):
            downloads["n"] += 1
        if downloads["n"] > int(n):
            raise StageBudget(f"{stage} pasó de {n} e-prints")
        if over_budget(time.time() - started, 1, budget):
            raise StageBudget(f"{stage} llegó al tope RRM_PASSAGES_BUDGET_USD={budget}")
        return result

    error = None
    done = []
    try:
        done = harvest_ids(
            ids,
            metas,
            client=client,
            papers_root=papers_root,
            dest=dest,
            break_lock=os.environ.get("RRM_PASSAGES_BREAK_LOCK") == "1",
            retry=os.environ.get("RRM_PASSAGES_RETRY") == "1",
            on_paper=on_paper,
            license_lookup=os.environ.get("RRM_PASSAGES_LICENSE") == "1",
        )
    except (ArxivStopped, StageBudget) as err:
        error = str(err)
    finally:
        _save_requests(dest, stage, client, error=error)
        manifest = compile_store(
            dest,
            quota_source=union.get("quota_source"),
            layer_donors=union.get("layer_donors"),
        )
        vol.commit()
    if error:
        raise SystemExit(f"{stage} se detiene: {error}")
    fetched = [item for item in done if item.get("downloaded")]
    with_tex = [item for item in fetched if item.get("tex")]
    download_s = [float(item["eprint"]["seconds"]) for item in fetched if (item.get("eprint") or {}).get("seconds") is not None]
    parse_s = [float(item["parse_seconds"]) for item in fetched if item.get("parse_seconds") is not None]
    row_counts = [int(item.get("rows") or 0) for item in done if not item.get("skipped")]
    return _report(stage, started, cpu=1, extra={
        "n": len(ids), "extra_ids": extra, "results": done, "rows": manifest["counts"],
        "arxiv_requests": client.log, "arxiv_gaps_s": client.gaps(),
        "min_gap_s": min(client.gaps()) if client.gaps() else None,
        "pace": {
            "fetched": len(fetched),
            "with_tex": len(with_tex),
            "tex_pct": round(100.0 * len(with_tex) / len(fetched), 1) if fetched else None,
            "download_s_sum": round(sum(download_s), 3),
            "download_s_per_paper": round(sum(download_s) / len(download_s), 3) if download_s else None,
            "parse_s_sum": round(sum(parse_s), 3),
            "parse_s_per_paper": round(sum(parse_s) / len(parse_s), 3) if parse_s else None,
            "rows_per_paper": round(sum(row_counts) / len(row_counts), 2) if row_counts else None,
        },
    })


@app.function(image=gpu_image, gpu="L4", volumes={MOUNT: vol}, secrets=[stage_env], cpu=2, memory=16384, timeout=3600, max_containers=1)
def embed_run(stage: str):
    """Un job corto. Embed de las filas ya parseadas y IndexFlatIP. Luego se apaga."""
    _require(stage)
    from rrm.passages.embed import embed_rows
    from rrm.passages.store import compile_store, load_saved, write_faiss
    from rrm.search.encode import QueryEncoder

    started = time.time()
    dest = _passages()
    _papers, rows, _failures = load_saved(dest)
    if not rows:
        raise SystemExit("no hay filas; la cosecha no escribió papers/")
    encoder = QueryEncoder()
    encoder.load()
    vectors = embed_rows(rows, encoder.encode_proximity, batch=16)
    _index, unit = write_faiss(dest, vectors)
    manifest = compile_store(dest)
    gpu_s = round(time.time() - started, 3)
    extra = {
        "rows": len(rows),
        "dim": int(unit.shape[1]) if unit.ndim == 2 else 0,
        "index": manifest["index"],
    }
    if stage == "e2":
        from rrm.passages.cost import L4_USD_PER_S
        from rrm.passages.query import query_rows

        symbol = r"\sqrt{d_k}"
        query = encoder.encode_proximity([symbol + "\n"])[0]
        hits = query_rows(rows, unit, {"symbol": symbol, "vector": query}, k=3)
        extra["symbol_query"] = {
            "symbol": symbol,
            "n": len(hits),
            "hits": [
                {
                    "id": hit.get("id"),
                    "corpusid": hit.get("corpusid"),
                    "kind": hit.get("kind"),
                    "section": hit.get("section"),
                    "latex": (hit.get("latex") or "")[:180],
                    "text": (hit.get("text") or "")[:180],
                    "cosine": hit.get("cosine"),
                    "url": hit.get("url"),
                }
                for hit in hits
            ],
        }
        extra["embed_usd_l4"] = round(gpu_s * L4_USD_PER_S, 6)
    vol.commit()
    return _report(stage, started, cpu=2, gpu_l4_seconds=gpu_s, extra=extra)


@app.local_entrypoint()
def e0():
    print(json.dumps(e0_run.remote(), ensure_ascii=False))


@app.local_entrypoint()
def e1():
    print(json.dumps(harvest_run.remote("e1", 5), ensure_ascii=False))


@app.local_entrypoint()
def e2():
    print(json.dumps(harvest_run.remote("e2", 50), ensure_ascii=False))
    print(json.dumps(embed_run.remote("e2"), ensure_ascii=False))


@app.local_entrypoint()
def e3():
    print(json.dumps(harvest_run.remote("e3", 2000), ensure_ascii=False))
    print(json.dumps(embed_run.remote("e3"), ensure_ascii=False))


@app.local_entrypoint()
def e4(symbol: str = r"\sqrt{d_k}", claim: str = "", local: str = ""):
    """E4 vive en el contenedor de búsqueda. Este entrypoint no lo prende."""
    raise SystemExit(
        "E4 consulta BurstSearch, que carga passages/ solo con RRM_PASSAGES=1.\n"
        "RRM_PASSAGES=1 RRM_PASSAGES_STAGE=e4 modal run rrm/search/serve.py::passages_query "
        f"--symbol {json.dumps(symbol)} --claim {json.dumps(claim)} --local {json.dumps(local)}"
    )
