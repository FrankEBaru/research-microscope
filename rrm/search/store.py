"""Read and write the index directory on the volume. No Modal import."""

from pathlib import Path

import numpy as np


def read_capped(path, columns, row_limit):
    """Read parquet columns, stopping after row_limit rows (0 means all)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    if not row_limit:
        return pf.read(columns=columns)
    batches = []
    seen = 0
    limit = int(row_limit)
    for batch in pf.iter_batches(columns=columns, batch_size=65536):
        if seen + batch.num_rows > limit:
            batch = batch.slice(0, limit - seen)
        batches.append(batch)
        seen += batch.num_rows
        if seen >= limit:
            break
    if not batches:
        fields = []
        schema = pf.schema_arrow
        for name in columns:
            fields.append(schema.field(name))
        return pa.schema(fields).empty_table()
    return pa.Table.from_batches(batches)


def save_graph(dest, graph):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    np.save(dest / "graph_ids.npy", np.asarray(graph.ids, dtype=np.int64))
    np.save(dest / "out_indptr.npy", np.asarray(graph.out_indptr, dtype=np.int64))
    np.save(dest / "out_indices.npy", np.asarray(graph.out_indices, dtype=np.int32))
    np.save(dest / "in_indptr.npy", np.asarray(graph.in_indptr, dtype=np.int64))
    np.save(dest / "in_indices.npy", np.asarray(graph.in_indices, dtype=np.int32))


def load_graph(dest):
    from rrm.search.graph import Graph

    dest = Path(dest)
    return Graph(
        np.load(dest / "graph_ids.npy"),
        np.load(dest / "out_indptr.npy"),
        np.load(dest / "out_indices.npy"),
        np.load(dest / "in_indptr.npy"),
        np.load(dest / "in_indices.npy"),
    )


def load_faiss(dest):
    import faiss

    dest = Path(dest)
    index = faiss.read_index(str(dest / "faiss.index"))
    ids = np.load(dest / "faiss_ids.npy")
    return index, ids


def load_display(dest):
    import pyarrow.parquet as pq

    return pq.read_table(Path(dest) / "display.parquet")


def load_bundle(dest):
    index, ids = load_faiss(dest)
    return {
        "index": index,
        "faiss_ids": ids,
        "graph": load_graph(dest),
        "display": load_display(dest),
    }


def part_names(directory):
    root = Path(directory)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.glob("part-*.parquet"))
