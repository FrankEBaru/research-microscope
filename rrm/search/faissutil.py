"""IVF-PQ over SPECTER vectors. L2 matches the SPECTER2 card (Euclidean)."""

import numpy as np


def dedup_keep_first(ids, vecs):
    ids = np.asarray(ids, dtype=np.int64).reshape(-1)
    if ids.size == 0:
        return ids, vecs[:0]
    _, first = np.unique(ids, return_index=True)
    first.sort()
    return ids[first], vecs[first]


def vectors_from_table(table):
    """corpusid plus float16 matrix from a fixed_size_list column named vector."""
    ids, valid = _ids(table)
    vec_col = table.column("vector").combine_chunks()
    dim = vec_col.type.list_size
    flat = np.asarray(vec_col.values.to_numpy(zero_copy_only=False))
    vecs = flat.reshape(-1, dim)
    if vec_col.null_count:
        vvalid = np.asarray(vec_col.is_valid().to_numpy(zero_copy_only=False), dtype=bool)
        valid = valid & vvalid
    return dedup_keep_first(ids[valid], vecs[valid])


def _ids(table):
    from rrm.search.graph import int_column

    return int_column(table, "corpusid")


def reservoir(ids, vecs, k, seed):
    n = len(ids)
    if n <= int(k):
        return ids, vecs
    rng = np.random.default_rng(int(seed))
    pick = np.sort(rng.choice(n, size=int(k), replace=False))
    return ids[pick], vecs[pick]


def train_ivfpq(sample, nlist, m, nbits, nprobe):
    import faiss

    sample = np.ascontiguousarray(sample, dtype=np.float32)
    if sample.ndim != 2 or sample.shape[0] == 0:
        raise ValueError("train sample is empty")
    dim = int(sample.shape[1])
    if m < 1 or dim % int(m) != 0:
        raise ValueError(f"m={m} must divide dim={dim}")
    if sample.shape[0] < int(nlist):
        raise ValueError(f"need at least nlist={nlist} train rows, got {sample.shape[0]}")
    quantizer = faiss.IndexFlatL2(dim)
    index = faiss.IndexIVFPQ(quantizer, dim, int(nlist), int(m), int(nbits))
    index.train(sample)
    index.nprobe = int(nprobe)
    return index


def add_vectors(index, vectors):
    vecs = np.ascontiguousarray(vectors, dtype=np.float32)
    if vecs.shape[0] == 0:
        return 0
    index.add(vecs)
    return int(vecs.shape[0])


def search_vectors(index, faiss_ids, vector, k):
    """Nearest corpus ids. faiss_ids[row] is the corpus id added at that row."""
    q = np.ascontiguousarray(vector, dtype=np.float32).reshape(1, -1)
    total = int(index.ntotal)
    k = int(min(int(k), total))
    if k <= 0:
        return []
    dists, rows = index.search(q, k)
    out = []
    for dist, row in zip(dists[0], rows[0]):
        if row < 0:
            continue
        out.append((int(faiss_ids[int(row)]), float(dist)))
    return out


def merge_indexes(indexes, id_lists):
    """Merge trained IVF indexes. Id lists follow add order in each shard."""
    base = None
    ids = []
    for index, id_list in zip(indexes, id_lists):
        id_list = np.asarray(id_list, dtype=np.int64).reshape(-1)
        if int(index.ntotal) == 0 or id_list.size == 0:
            continue
        if id_list.size != int(index.ntotal):
            raise ValueError("faiss id list length does not match ntotal")
        if base is None:
            base = index
            ids.append(id_list)
            continue
        base.merge_from(index, int(base.ntotal))
        ids.append(id_list)
    if base is None:
        raise ValueError("no vectors to merge")
    return base, np.concatenate(ids)
