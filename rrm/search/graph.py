"""CS-to-CS citation graph stored as CSR numpy arrays."""

import numpy as np


def sorted_ids(ids):
    arr = np.asarray(ids, dtype=np.int64).reshape(-1)
    if arr.size == 0:
        return arr
    return np.unique(arr)


def locate(sorted_corpus, values):
    """hit mask and positions of values inside a sorted unique id array."""
    values = np.asarray(values, dtype=np.int64).reshape(-1)
    n = len(sorted_corpus)
    if n == 0 or values.size == 0:
        return np.zeros(values.size, dtype=bool), np.zeros(values.size, dtype=np.int64)
    pos = np.searchsorted(sorted_corpus, values)
    in_range = pos < n
    clipped = np.minimum(pos, n - 1)
    hit = in_range & (sorted_corpus[clipped] == values)
    return hit, clipped


def int_column(table, name):
    """int64 values plus a valid mask. Nulls become 0 and valid=False."""
    col = table.column(name).combine_chunks()
    valid = np.asarray(col.is_valid().to_numpy(zero_copy_only=False), dtype=bool)
    values = col.fill_null(0).to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
    return values, valid


def edges_from_pairs(citing, cited, cs_sorted, citing_ok=None, cited_ok=None):
    """Local int32 endpoints for pairs whose both ends are CS ids. Drops self-loops."""
    citing = np.asarray(citing, dtype=np.int64).reshape(-1)
    cited = np.asarray(cited, dtype=np.int64).reshape(-1)
    if citing_ok is None:
        citing_ok = np.ones(citing.size, dtype=bool)
    if cited_ok is None:
        cited_ok = np.ones(cited.size, dtype=bool)
    valid = np.asarray(citing_ok, dtype=bool) & np.asarray(cited_ok, dtype=bool)
    valid &= citing != cited
    empty = np.zeros(0, dtype=np.int32)
    if citing.size == 0 or not valid.any():
        return empty, empty
    hit_src, src = locate(cs_sorted, citing[valid])
    hit_dst, dst = locate(cs_sorted, cited[valid])
    both = hit_src & hit_dst
    return src[both].astype(np.int32, copy=False), dst[both].astype(np.int32, copy=False)


def stack_edges(pairs):
    srcs, dsts = [], []
    for src, dst in pairs:
        src = np.asarray(src, dtype=np.int32).reshape(-1)
        dst = np.asarray(dst, dtype=np.int32).reshape(-1)
        if src.size:
            srcs.append(src)
            dsts.append(dst)
    if not srcs:
        return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32)
    return np.concatenate(srcs), np.concatenate(dsts)


def csr_from_edges(src, dst, n):
    """Directed CSR. Duplicate (src, dst) pairs are dropped. Rows are sorted."""
    src = np.asarray(src, dtype=np.int64).reshape(-1)
    dst = np.asarray(dst, dtype=np.int64).reshape(-1)
    indptr = np.zeros(n + 1, dtype=np.int64)
    if src.size == 0:
        return indptr, np.zeros(0, dtype=np.int32)
    keep = src != dst
    src = src[keep]
    dst = dst[keep]
    if src.size == 0:
        return indptr, np.zeros(0, dtype=np.int32)
    order = np.lexsort((dst, src))
    src = src[order]
    dst = dst[order]
    if src.size > 1:
        dup = np.empty(src.size, dtype=bool)
        dup[0] = False
        dup[1:] = (src[1:] == src[:-1]) & (dst[1:] == dst[:-1])
        src = src[~dup]
        dst = dst[~dup]
    counts = np.bincount(src, minlength=n)
    np.cumsum(counts, out=indptr[1:])
    return indptr, dst.astype(np.int32, copy=False)


def transpose_csr(indptr, indices, n):
    """Incoming-edge CSR for a directed graph."""
    indices = np.asarray(indices)
    if indices.size == 0:
        return np.zeros(n + 1, dtype=np.int64), np.zeros(0, dtype=np.int32)
    counts = np.bincount(indices, minlength=n)
    in_indptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(counts, out=in_indptr[1:])
    degree = np.diff(indptr).astype(np.int64, copy=False)
    src = np.repeat(np.arange(n, dtype=np.int32), degree)
    order = np.argsort(indices, kind="mergesort")
    return in_indptr, src[order].astype(np.int32, copy=False)


class Graph:
    def __init__(self, ids, out_indptr, out_indices, in_indptr, in_indices):
        self.ids = np.asarray(ids, dtype=np.int64)
        self.out_indptr = np.asarray(out_indptr, dtype=np.int64)
        self.out_indices = np.asarray(out_indices, dtype=np.int32)
        self.in_indptr = np.asarray(in_indptr, dtype=np.int64)
        self.in_indices = np.asarray(in_indices, dtype=np.int32)

    @staticmethod
    def from_edges(ids, src, dst):
        ids = np.asarray(ids, dtype=np.int64)
        n = len(ids)
        out_indptr, out_indices = csr_from_edges(src, dst, n)
        in_indptr, in_indices = transpose_csr(out_indptr, out_indices, n)
        return Graph(ids, out_indptr, out_indices, in_indptr, in_indices)

    def out_neighbors(self, local):
        local = int(local)
        return self.out_indices[self.out_indptr[local] : self.out_indptr[local + 1]]
