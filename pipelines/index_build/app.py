"""Build FAISS, the CS-CS citation graph, and the display table on rrm-data.

Inputs are the parquet trees written by pipelines/s2_download, under
/s2/<release>/ (the release id, for example 2026-10-20). Embeddings are
already limited to Computer Science. cs_corpusids.parquet comes from
build_cs_ids. Each stage takes limit (number of shards, 0 = all) and
row_limit (rows per shard, 0 = all). Artifacts go to /s2/<release>/<dest>/.
Use dest=index_test for a short run so the full index is left alone.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modal

from rrm.search.display import empty_papers, empty_tldrs, filter_papers, filter_tldrs, merge_display
from rrm.search.faissutil import add_vectors, ensure_direct_map, merge_indexes, reservoir, train_ivfpq, vectors_from_table
from rrm.search.graph import Graph, edges_from_pairs, int_column, sorted_ids, stack_edges
from rrm.search.store import part_names, read_capped, save_graph

MOUNT = "/s2"
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "pyarrow", "faiss-cpu")
    .add_local_python_source("rrm")
)
app = modal.App("rrm-index")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


def _root(release, dest):
    return Path(MOUNT) / _safe(release) / _safe(dest)


def _work(release, dest):
    return _root(release, dest) / "work"


def _load_cs(release):
    import numpy as np
    import pyarrow.parquet as pq

    path = Path(MOUNT) / _safe(release) / "cs_corpusids.parquet"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}; run build_cs_ids first")
    col = pq.read_table(path, columns=["corpusid"]).column("corpusid").combine_chunks()
    valid = np.asarray(col.is_valid().to_numpy(zero_copy_only=False), dtype=bool)
    values = col.fill_null(0).to_numpy(zero_copy_only=False).astype("int64", copy=False)
    return sorted_ids(values[valid])


def _save_npy(path, array):
    import numpy as np

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".partial.npy")
    np.save(tmp, array)
    os.replace(tmp, path)


def _save_npz(path, **arrays):
    import numpy as np

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.stem + ".partial.npz")
    np.savez(tmp, **arrays)
    os.replace(tmp, path)


def _save_index(index, path):
    import faiss

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".partial")
    faiss.write_index(index, str(tmp))
    os.replace(tmp, path)


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=512, timeout=300)
def list_parts(release: str, dataset: str):
    vol.reload()
    return part_names(Path(MOUNT) / _safe(release) / _safe(dataset))


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=4096, timeout=3600, retries=1)
def sample_embeddings(release: str, dest: str, name: str, sample_n: int, row_limit: int, seed: int):
    vol.reload()
    ids, vecs = vectors_from_table(
        read_capped(Path(MOUNT) / _safe(release) / "embeddings-specter_v2" / name, ["corpusid", "vector"], row_limit)
    )
    ids, vecs = reservoir(ids, vecs, sample_n, seed)
    path = _work(release, dest) / f"sample-{Path(name).stem}.npz"
    _save_npz(path, ids=ids.astype("int64"), vecs=vecs.astype("float16"))
    vol.commit()
    return {"shard": name, "rows": int(len(ids))}


@app.function(image=image, volumes={MOUNT: vol}, cpu=4, memory=16384, timeout=3600)
def train_faiss(release: str, dest: str, nlist: int, m: int, nbits: int, nprobe: int, train_size: int):
    import numpy as np

    vol.reload()
    work = _work(release, dest)
    files = sorted(work.glob("sample-*.npz"))
    if not files:
        raise RuntimeError("no embedding samples")
    ids, vecs = [], []
    for path in files:
        blob = np.load(path)
        if blob["vecs"].shape[0]:
            ids.append(blob["ids"])
            vecs.append(blob["vecs"])
    if not vecs:
        raise RuntimeError("embedding samples are empty")
    mat = np.concatenate(vecs)
    _idv, mat = reservoir(np.concatenate(ids), mat, train_size, 0)
    index = train_ivfpq(mat, nlist, m, nbits, nprobe)
    _save_index(index, work / "trained.index")
    vol.commit()
    return {"train_rows": int(mat.shape[0]), "dim": int(mat.shape[1])}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=4096, timeout=3600, retries=1)
def add_shard(release: str, dest: str, name: str, row_limit: int):
    import faiss

    vol.reload()
    work = _work(release, dest)
    ids, vecs = vectors_from_table(
        read_capped(Path(MOUNT) / _safe(release) / "embeddings-specter_v2" / name, ["corpusid", "vector"], row_limit)
    )
    index = faiss.read_index(str(work / "trained.index"))
    added = add_vectors(index, vecs)
    stem = Path(name).stem
    _save_index(index, work / f"added-{stem}.index")
    _save_npy(work / f"added-{stem}.npy", ids.astype("int64"))
    vol.commit()
    return {"shard": name, "rows": added}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=8192, timeout=3600)
def merge_faiss(release: str, dest: str, nprobe: int):
    import faiss
    import numpy as np

    vol.reload()
    work = _work(release, dest)
    paths = sorted(work.glob("added-*.index"))
    if not paths:
        raise RuntimeError("no shard indexes")
    indexes, lists = [], []
    for path in paths:
        indexes.append(faiss.read_index(str(path)))
        lists.append(np.load(path.with_suffix(".npy")))
    index, ids = merge_indexes(indexes, lists)
    index.nprobe = int(nprobe)
    ensure_direct_map(index)
    root = _root(release, dest)
    _save_index(index, root / "faiss.index")
    _save_npy(root / "faiss_ids.npy", ids)
    vol.commit()
    return {"rows": int(len(ids))}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=4096, timeout=1800)
def prepare_graph_ids(release: str, dest: str):
    vol.reload()
    ids = _load_cs(release)
    _save_npy(_root(release, dest) / "graph_ids.npy", ids)
    vol.commit()
    return {"rows": int(len(ids))}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=4096, timeout=3600, retries=1)
def citation_shard(release: str, dest: str, name: str, row_limit: int):
    import numpy as np

    vol.reload()
    cs = np.load(_root(release, dest) / "graph_ids.npy")
    table = read_capped(
        Path(MOUNT) / _safe(release) / "citations" / name,
        ["citingcorpusid", "citedcorpusid"],
        row_limit,
    )
    citing, citing_ok = int_column(table, "citingcorpusid")
    cited, cited_ok = int_column(table, "citedcorpusid")
    src, dst = edges_from_pairs(citing, cited, cs, citing_ok, cited_ok)
    _save_npz(_work(release, dest) / f"edges-{Path(name).stem}.npz", src=src, dst=dst)
    vol.commit()
    return {"shard": name, "edges": int(len(src))}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=16384, timeout=7200)
def merge_graph(release: str, dest: str):
    import numpy as np

    vol.reload()
    root = _root(release, dest)
    ids = np.load(root / "graph_ids.npy")
    pairs = []
    for path in sorted(_work(release, dest).glob("edges-*.npz")):
        blob = np.load(path)
        pairs.append((blob["src"], blob["dst"]))
    src, dst = stack_edges(pairs)
    graph = Graph.from_edges(ids, src, dst)
    save_graph(root, graph)
    vol.commit()
    return {"nodes": int(len(ids)), "edges": int(len(graph.out_indices))}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=4096, timeout=3600, retries=1)
def papers_shard(release: str, dest: str, name: str, row_limit: int):
    import numpy as np
    import pyarrow.parquet as pq

    vol.reload()
    cs = np.load(_root(release, dest) / "graph_ids.npy")
    table = read_capped(
        Path(MOUNT) / _safe(release) / "papers" / name,
        ["corpusid", "title", "year", "venue", "citationcount", "externalids"],
        row_limit,
    )
    out = filter_papers(table, cs)
    path = _work(release, dest) / f"papers-{Path(name).stem}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(out, path, compression="zstd")
    vol.commit()
    return {"shard": name, "rows": int(out.num_rows)}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=2048, timeout=3600, retries=1)
def tldr_shard(release: str, dest: str, name: str, row_limit: int):
    import numpy as np
    import pyarrow.parquet as pq

    vol.reload()
    cs = np.load(_root(release, dest) / "graph_ids.npy")
    table = read_capped(
        Path(MOUNT) / _safe(release) / "tldrs" / name,
        ["corpusid", "text"],
        row_limit,
    )
    out = filter_tldrs(table, cs)
    path = _work(release, dest) / f"tldr-{Path(name).stem}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(out, path, compression="zstd")
    vol.commit()
    return {"shard": name, "rows": int(out.num_rows)}


@app.function(image=image, volumes={MOUNT: vol}, cpu=1, memory=16384, timeout=7200)
def merge_display_table(release: str, dest: str):
    import pyarrow as pa
    import pyarrow.parquet as pq

    vol.reload()
    work = _work(release, dest)
    papers = [pq.read_table(path) for path in sorted(work.glob("papers-*.parquet"))]
    tldrs = [pq.read_table(path) for path in sorted(work.glob("tldr-*.parquet"))]
    paper = pa.concat_tables(papers) if papers else empty_papers()
    tldr = pa.concat_tables(tldrs) if tldrs else empty_tldrs()
    table = merge_display(paper, tldr)
    path = _root(release, dest) / "display.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")
    vol.commit()
    return {"rows": int(table.num_rows)}


def _take(names, limit):
    names = list(names)
    if int(limit) > 0:
        return names[: int(limit)]
    return names


def _map(fn, jobs, label):
    failed = 0
    for row in fn.starmap(jobs, order_outputs=False, return_exceptions=True):
        if isinstance(row, BaseException):
            failed += 1
            print(f"ERROR {label} {type(row).__name__} {str(row).split(chr(10), 1)[0][:180]}")
            continue
        print(f"{label} {row}")
    if failed:
        raise SystemExit(f"{label} failed={failed}")


@app.local_entrypoint()
def faiss_index(
    release: str = "2026-10-20",
    dest: str = "index",
    limit: int = 0,
    row_limit: int = 0,
    nlist: int = 4096,
    m: int = 96,
    nbits: int = 8,
    nprobe: int = 32,
    train_size: int = 262144,
    sample_per_shard: int = 4096,
    cpu: float = 1,
    memory: int = 4096,
    train_cpu: float = 4,
    train_memory: int = 16384,
):
    names = _take(list_parts.remote(release, "embeddings-specter_v2"), limit)
    if not names:
        raise SystemExit("no embedding shards")
    sampler = sample_embeddings.with_options(cpu=float(cpu), memory=int(memory))
    _map(
        sampler,
        [(release, dest, name, int(sample_per_shard), int(row_limit), i) for i, name in enumerate(names)],
        "sample",
    )
    trained = train_faiss.with_options(cpu=float(train_cpu), memory=int(train_memory)).remote(
        release, dest, int(nlist), int(m), int(nbits), int(nprobe), int(train_size)
    )
    print(f"train {trained}")
    adder = add_shard.with_options(cpu=float(cpu), memory=int(memory))
    _map(adder, [(release, dest, name, int(row_limit)) for name in names], "add")
    merged = merge_faiss.with_options(cpu=float(cpu), memory=max(int(memory), 8192)).remote(
        release, dest, int(nprobe)
    )
    print(f"faiss {merged}")


@app.local_entrypoint()
def citation_graph(
    release: str = "2026-10-20",
    dest: str = "index",
    limit: int = 0,
    row_limit: int = 0,
    cpu: float = 1,
    memory: int = 4096,
    merge_memory: int = 16384,
):
    names = _take(list_parts.remote(release, "citations"), limit)
    prepared = prepare_graph_ids.remote(release, dest)
    print(f"ids {prepared}")
    if not names:
        raise SystemExit("no citation shards")
    worker = citation_shard.with_options(cpu=float(cpu), memory=int(memory))
    _map(worker, [(release, dest, name, int(row_limit)) for name in names], "citations")
    merged = merge_graph.with_options(cpu=1, memory=int(merge_memory)).remote(release, dest)
    print(f"graph {merged}")


@app.local_entrypoint()
def display_table(
    release: str = "2026-10-20",
    dest: str = "index",
    limit: int = 0,
    row_limit: int = 0,
    cpu: float = 1,
    memory: int = 4096,
    merge_memory: int = 16384,
):
    """limit applies separately to papers shards and to tldr shards."""
    papers = _take(list_parts.remote(release, "papers"), limit)
    tldrs = _take(list_parts.remote(release, "tldrs"), limit)
    prepared = prepare_graph_ids.remote(release, dest)
    print(f"ids {prepared}")
    worker = papers_shard.with_options(cpu=float(cpu), memory=int(memory))
    _map(worker, [(release, dest, name, int(row_limit)) for name in papers], "papers")
    tldr_worker = tldr_shard.with_options(cpu=float(cpu), memory=min(int(memory), 4096))
    _map(tldr_worker, [(release, dest, name, int(row_limit)) for name in tldrs], "tldr")
    merged = merge_display_table.with_options(cpu=1, memory=int(merge_memory)).remote(release, dest)
    print(f"display {merged}")
