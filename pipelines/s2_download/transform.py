"""Stream Semantic Scholar JSONL.gz shards into zstd Parquet.

Records are parsed and written in batches. A shard is never held as one
bytes object or one table. The CS corpus id set is a sorted uint32 array
plus a packed bitmap, not a Python set.
"""

from __future__ import annotations

import array
import json
import os
import re
import resource
import sys
import time
from typing import Callable, Iterable, Iterator

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.s2_download.fetch import CountingReader, gzip_stream

CS_CATEGORY = "computer science"
MAX_BITMAP_ID = 500_000_000
MAX_LINE_BYTES = 32 * 1024 * 1024
_ARXIV_VERSION = re.compile(r"v\d+$")

DATASETS = (
    "papers",
    "abstracts",
    "tldrs",
    "citations",
    "embeddings-specter_v2",
)
NEEDS_CS = frozenset({"citations", "embeddings-specter_v2"})

EXT_KEYS = (
    ("acl", "ACL"),
    ("dblp", "DBLP"),
    ("arxiv", "ArXiv"),
    ("mag", "MAG"),
    ("corpusid", "CorpusId"),
    ("pubmed", "PubMed"),
    ("doi", "DOI"),
    ("pubmedcentral", "PubMedCentral"),
)

_EXT_TYPE = pa.struct([(name, pa.string()) for _, name in EXT_KEYS])
_AUTHOR_TYPE = pa.struct([("authorId", pa.string()), ("name", pa.string())])
_FOS_TYPE = pa.struct([("category", pa.string()), ("source", pa.string())])
_JOURNAL_TYPE = pa.struct(
    [("name", pa.string()), ("pages", pa.string()), ("volume", pa.string())]
)
_OA_EXT_TYPE = pa.struct([(name, pa.string()) for _, name in EXT_KEYS])
_OA_TYPE = pa.struct(
    [
        ("externalids", _OA_EXT_TYPE),
        ("license", pa.string()),
        ("url", pa.string()),
        ("status", pa.string()),
        ("disclaimer", pa.string()),
    ]
)

PAPERS_SCHEMA = pa.schema(
    [
        ("corpusid", pa.int64()),
        ("externalids", _EXT_TYPE),
        ("url", pa.string()),
        ("title", pa.string()),
        ("authors", pa.list_(_AUTHOR_TYPE)),
        ("venue", pa.string()),
        ("publicationvenueid", pa.string()),
        ("year", pa.int32()),
        ("referencecount", pa.int64()),
        ("citationcount", pa.int64()),
        ("influentialcitationcount", pa.int64()),
        ("isopenaccess", pa.bool_()),
        ("s2fieldsofstudy", pa.list_(_FOS_TYPE)),
        ("fieldsofstudy", pa.list_(pa.string())),
        ("publicationtypes", pa.list_(pa.string())),
        ("publicationdate", pa.string()),
        ("journal", _JOURNAL_TYPE),
        ("extra", pa.string()),
    ]
)

ABSTRACTS_SCHEMA = pa.schema(
    [
        ("corpusid", pa.int64()),
        ("abstract", pa.string()),
        ("openaccessinfo", _OA_TYPE),
        ("extra", pa.string()),
    ]
)

TLDRS_SCHEMA = pa.schema(
    [
        ("corpusid", pa.int64()),
        ("model", pa.string()),
        ("text", pa.string()),
        ("extra", pa.string()),
    ]
)

CITATIONS_SCHEMA = pa.schema(
    [
        ("citationid", pa.int64()),
        ("citingcorpusid", pa.int64()),
        ("citedcorpusid", pa.int64()),
        ("isinfluential", pa.bool_()),
        ("contexts", pa.list_(pa.string())),
        ("intents", pa.string()),
        ("extra", pa.string()),
    ]
)

CITATIONS_CS_SCHEMA = pa.schema(
    list(CITATIONS_SCHEMA)
    + [
        ("citing_is_cs", pa.bool_()),
        ("cited_is_cs", pa.bool_()),
        ("both_cs", pa.bool_()),
    ]
)

ARXIV_SCHEMA = pa.schema(
    [
        ("arxiv_id", pa.string()),
        ("arxiv_id_versionless", pa.string()),
        ("corpusid", pa.int64()),
    ]
)

PAPER_KEYS = {field.name for field in PAPERS_SCHEMA if field.name != "extra"}
ABSTRACT_KEYS = {field.name for field in ABSTRACTS_SCHEMA if field.name != "extra"}
TLDR_KEYS = {field.name for field in TLDRS_SCHEMA if field.name != "extra"}
CITATION_KEYS = {field.name for field in CITATIONS_SCHEMA if field.name != "extra"}

BATCH_SIZE = {
    "papers": 512,
    "abstracts": 256,
    "tldrs": 1024,
    "citations": 4096,
    "embeddings-specter_v2": 2048,
}


def loads(line: bytes) -> dict:
    try:
        import orjson

        value = orjson.loads(line)
    except Exception:
        value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("record is not an object")
    return value


def peak_rss_mib() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024.0


def shard_name(index: int) -> str:
    return f"shard-{index:05d}.parquet"


def dataset_dir(root: str, release: str, dataset: str) -> str:
    return os.path.join(root, release, dataset)


def shard_path(root: str, release: str, dataset: str, index: int) -> str:
    return os.path.join(dataset_dir(root, release, dataset), shard_name(index))


def partial_dir(root: str, release: str) -> str:
    return os.path.join(root, release, "papers", "_partial")


def cs_dir(root: str, release: str) -> str:
    return os.path.join(root, release, "_cs")


def runs_dir(root: str) -> str:
    return os.path.join(root, "_runs")


def _as_str(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return bool(value)


def _norm_external(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    lowered = {str(key).lower(): item for key, item in value.items()}
    return {canon: _as_str(lowered.get(src)) for src, canon in EXT_KEYS}


def _norm_authors(value) -> list | None:
    if not isinstance(value, list):
        return None
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "authorId": _as_str(item.get("authorId")),
                "name": _as_str(item.get("name")),
            }
        )
    return rows or None


def _norm_fos(value) -> list | None:
    if not isinstance(value, list):
        return None
    rows = []
    for item in value:
        if isinstance(item, dict):
            rows.append(
                {
                    "category": _as_str(item.get("category")),
                    "source": _as_str(item.get("source")),
                }
            )
        elif isinstance(item, str):
            rows.append({"category": item, "source": None})
    return rows or None


def _norm_str_list(value) -> list | None:
    if not isinstance(value, list):
        return None
    rows = []
    for item in value:
        if item is None:
            rows.append(None)
        elif isinstance(item, str):
            rows.append(item)
        else:
            rows.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
    return rows


def _norm_journal(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {
        "name": _as_str(value.get("name")),
        "pages": _as_str(value.get("pages")),
        "volume": _as_str(value.get("volume")),
    }


def _extra(record: dict, known: set[str], aliases: dict[str, str]) -> str | None:
    dropped = {}
    for key, value in record.items():
        canon = aliases.get(key, key)
        if canon not in known and key not in known:
            dropped[key] = value
    if not dropped:
        return None
    return json.dumps(dropped, ensure_ascii=False, separators=(",", ":"), default=str)


def _category_is_cs(value) -> bool:
    if isinstance(value, dict):
        value = value.get("category")
    return isinstance(value, str) and value.strip().lower() == CS_CATEGORY


def is_computer_science(record: dict) -> bool:
    for key in ("s2fieldsofstudy", "s2FieldsOfStudy"):
        items = record.get(key)
        if isinstance(items, list) and any(_category_is_cs(item) for item in items):
            return True
    for key in ("fieldsOfStudy", "fieldsofstudy"):
        items = record.get(key)
        if isinstance(items, list) and any(_category_is_cs(item) for item in items):
            return True
    return False


def extract_arxiv(record: dict) -> str | None:
    external = record.get("externalids")
    if external is None:
        external = record.get("externalIds")
    if not isinstance(external, dict):
        return None
    for key, value in external.items():
        if str(key).lower() == "arxiv" and value:
            text = str(value).strip()
            return text or None
    return None


def versionless_arxiv(arxiv_id: str) -> str:
    return _ARXIV_VERSION.sub("", arxiv_id.strip())


def paper_row(record: dict) -> dict:
    fos = record.get("s2fieldsofstudy")
    if fos is None:
        fos = record.get("s2FieldsOfStudy")
    fields = record.get("fieldsofstudy")
    if fields is None:
        fields = record.get("fieldsOfStudy")
    field_list = None
    if isinstance(fields, list):
        field_list = [_as_str(item) if not isinstance(item, dict) else _as_str(item.get("category")) for item in fields]
    return {
        "corpusid": _as_int(record.get("corpusid", record.get("corpusId"))),
        "externalids": _norm_external(record.get("externalids", record.get("externalIds"))),
        "url": _as_str(record.get("url")),
        "title": _as_str(record.get("title")),
        "authors": _norm_authors(record.get("authors")),
        "venue": _as_str(record.get("venue")),
        "publicationvenueid": _as_str(record.get("publicationvenueid")),
        "year": _as_int(record.get("year")),
        "referencecount": _as_int(record.get("referencecount")),
        "citationcount": _as_int(record.get("citationcount")),
        "influentialcitationcount": _as_int(record.get("influentialcitationcount")),
        "isopenaccess": _as_bool(record.get("isopenaccess")),
        "s2fieldsofstudy": _norm_fos(fos),
        "fieldsofstudy": field_list,
        "publicationtypes": _norm_str_list(record.get("publicationtypes")),
        "publicationdate": _as_str(record.get("publicationdate")),
        "journal": _norm_journal(record.get("journal")),
        "extra": _extra(
            record,
            PAPER_KEYS,
            {
                "corpusId": "corpusid",
                "externalIds": "externalids",
                "s2FieldsOfStudy": "s2fieldsofstudy",
                "fieldsOfStudy": "fieldsofstudy",
            },
        ),
    }


def abstract_row(record: dict) -> dict:
    info = record.get("openaccessinfo")
    parsed = None
    if isinstance(info, dict):
        parsed = {
            "externalids": _norm_external(info.get("externalids") or info.get("externalIds")),
            "license": _as_str(info.get("license")),
            "url": _as_str(info.get("url")),
            "status": _as_str(info.get("status")),
            "disclaimer": _as_str(info.get("disclaimer")),
        }
    return {
        "corpusid": _as_int(record.get("corpusid", record.get("corpusId"))),
        "abstract": _as_str(record.get("abstract")),
        "openaccessinfo": parsed,
        "extra": _extra(record, ABSTRACT_KEYS, {"corpusId": "corpusid"}),
    }


def tldr_row(record: dict) -> dict:
    return {
        "corpusid": _as_int(record.get("corpusid", record.get("corpusId"))),
        "model": _as_str(record.get("model")),
        "text": _as_str(record.get("text")),
        "extra": _extra(record, TLDR_KEYS, {"corpusId": "corpusid"}),
    }


def citation_row(record: dict) -> dict:
    intents = record.get("intents")
    intents_json = None if intents is None else json.dumps(intents, ensure_ascii=False, separators=(",", ":"), default=str)
    return {
        "citationid": _as_int(record.get("citationid")),
        "citingcorpusid": _as_int(record.get("citingcorpusid")),
        "citedcorpusid": _as_int(record.get("citedcorpusid")),
        "isinfluential": _as_bool(record.get("isinfluential")),
        "contexts": _norm_str_list(record.get("contexts")),
        "intents": intents_json,
        "extra": _extra(record, CITATION_KEYS, {}),
    }


def parse_vector(value) -> np.ndarray:
    if isinstance(value, str):
        value = json.loads(value)
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("vector must be a 1-d list")
    return array


def embedding_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            ("corpusid", pa.int64()),
            ("vector", pa.list_(pa.float16(), dim)),
        ]
    )


class BatchWriter:
    def __init__(self, path: str, schema: pa.Schema, batch_size: int):
        self.path = path
        self.schema = schema
        self.batch_size = batch_size
        self.rows = 0
        self.max_buffered = 0
        self.flushes = 0
        self._buf: list[dict] = []
        self._writer: pq.ParquetWriter | None = None
        self._tmp = path + ".partial"

    def write(self, row: dict) -> None:
        self._buf.append(row)
        self.max_buffered = max(self.max_buffered, len(self._buf))
        if len(self._buf) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buf:
            return
        table = pa.Table.from_pylist(self._buf, schema=self.schema)
        self._write_table(table)
        self._buf.clear()

    def _write_table(self, table: pa.Table) -> None:
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._writer = pq.ParquetWriter(self._tmp, self.schema, compression="zstd")
        self._writer.write_table(table)
        self.rows += table.num_rows
        self.flushes += 1

    def close(self) -> None:
        self.flush()
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            pq.write_table(pa.Table.from_pylist([], schema=self.schema), self._tmp, compression="zstd")
            self.flushes += 1
        else:
            self._writer.close()
            self._writer = None
        os.replace(self._tmp, self.path)

    def abort(self) -> None:
        self._buf.clear()
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        if os.path.exists(self._tmp):
            os.remove(self._tmp)
        if os.path.exists(self.path):
            os.remove(self.path)


class EmbeddingWriter:
    def __init__(self, path: str, batch_size: int):
        self.path = path
        self.batch_size = batch_size
        self.rows = 0
        self.max_buffered = 0
        self.flushes = 0
        self.dim: int | None = None
        self.schema: pa.Schema | None = None
        self._ids: list[int] = []
        self._vecs: list[np.ndarray] = []
        self._writer: pq.ParquetWriter | None = None
        self._tmp = path + ".partial"

    def write(self, corpus_id: int, vector: np.ndarray) -> None:
        dim = int(vector.shape[0])
        if self.dim is None:
            self.schema = embedding_schema(dim)
            self.dim = dim
        elif dim != self.dim:
            raise ValueError("mixed vector dimensions in one shard")
        self._ids.append(int(corpus_id))
        self._vecs.append(np.asarray(vector, dtype=np.float16))
        self.max_buffered = max(self.max_buffered, len(self._ids))
        if len(self._ids) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._ids:
            return
        assert self.schema is not None and self.dim is not None
        flat = np.concatenate(self._vecs).astype(np.float16, copy=False)
        values = pa.array(flat, type=pa.float16())
        vectors = pa.FixedSizeListArray.from_arrays(values, self.dim)
        ids = pa.array(self._ids, type=pa.int64())
        table = pa.Table.from_arrays([ids, vectors], schema=self.schema)
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._writer = pq.ParquetWriter(self._tmp, self.schema, compression="zstd")
        self._writer.write_table(table)
        self.rows += table.num_rows
        self.flushes += 1
        self._ids.clear()
        self._vecs.clear()

    def close(self) -> None:
        self.flush()
        if self.schema is None:
            self.dim = 768
            self.schema = embedding_schema(self.dim)
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            pq.write_table(pa.Table.from_pylist([], schema=self.schema), self._tmp, compression="zstd")
            self.flushes += 1
        else:
            self._writer.close()
            self._writer = None
        os.replace(self._tmp, self.path)

    def abort(self) -> None:
        self._ids.clear()
        self._vecs.clear()
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        if os.path.exists(self._tmp):
            os.remove(self._tmp)
        if os.path.exists(self.path):
            os.remove(self.path)


def iter_records(gz) -> Iterator[tuple[str, dict | None]]:
    for line in gz:
        if not line or not line.strip():
            continue
        if len(line) > MAX_LINE_BYTES:
            yield ("bad", None)
            continue
        try:
            yield ("ok", loads(line))
        except Exception:
            yield ("bad", None)


def atomic_npy(path: str, array: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npy"
    np.save(tmp, array)
    os.replace(tmp, path)


class CSIndex:
    def __init__(self, bits: np.ndarray, max_id: int, count: int):
        self.bits = np.asarray(bits, dtype=np.uint8)
        self.max_id = int(max_id)
        self.count = int(count)

    def contains(self, corpus_id: int | None) -> bool:
        if corpus_id is None or corpus_id < 0 or corpus_id > self.max_id:
            return False
        return bool(self.bits[corpus_id >> 3] & (np.uint8(1) << np.uint8(corpus_id & 7)))

    def contains_many(self, ids: np.ndarray) -> np.ndarray:
        ids = np.asarray(ids, dtype=np.int64)
        ok = (ids >= 0) & (ids <= self.max_id)
        out = np.zeros(ids.shape[0], dtype=bool)
        if not np.any(ok):
            return out
        chosen = ids[ok]
        masks = np.left_shift(np.uint8(1), (chosen & 7).astype(np.uint8))
        out[ok] = (self.bits[chosen >> 3] & masks) != 0
        return out


def popcount(bits: np.ndarray) -> int:
    table = np.unpackbits(np.arange(256, dtype=np.uint8)).reshape(256, 8).sum(axis=1)
    return int(table[np.asarray(bits, dtype=np.uint8)].sum())


def build_cs_index(ids: np.ndarray) -> tuple[CSIndex, np.ndarray]:
    values = np.asarray(ids, dtype=np.int64).reshape(-1)
    values = values[values >= 0]
    if values.size == 0:
        empty = np.zeros(0, dtype=np.uint32)
        return CSIndex(np.zeros(1, dtype=np.uint8), 0, 0), empty
    values = np.unique(values)
    max_id = int(values[-1])
    if max_id > MAX_BITMAP_ID:
        raise RuntimeError(f"corpus id {max_id} is above the bitmap cap {MAX_BITMAP_ID}")
    bits = np.zeros((max_id >> 3) + 1, dtype=np.uint8)
    masks = np.left_shift(np.uint8(1), (values & 7).astype(np.uint8))
    np.bitwise_or.at(bits, values >> 3, masks)
    index = CSIndex(bits, max_id, int(values.size))
    if max_id <= np.iinfo(np.uint32).max:
        stored = values.astype(np.uint32)
    else:
        stored = values
    return index, stored


def save_cs(
    directory: str,
    index: CSIndex,
    sorted_ids: np.ndarray,
    release: str,
    *,
    partial: bool = False,
) -> None:
    os.makedirs(directory, exist_ok=True)
    atomic_npy(os.path.join(directory, "bitmap.npy"), index.bits)
    atomic_npy(os.path.join(directory, "corpusids.npy"), sorted_ids)
    meta = {
        "release_id": release,
        "count": index.count,
        "max_id": index.max_id,
        "dtype": str(sorted_ids.dtype),
        "partial": bool(partial),
    }
    _write_json(os.path.join(directory, "meta.json"), meta)


def load_cs(directory: str) -> CSIndex:
    meta_path = os.path.join(directory, "meta.json")
    with open(meta_path, encoding="utf-8") as handle:
        meta = json.load(handle)
    bits = np.load(os.path.join(directory, "bitmap.npy"))
    return CSIndex(bits, int(meta["max_id"]), int(meta["count"]))


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def _file_size(path: str) -> int:
    if not os.path.exists(path):
        return 0
    return os.path.getsize(path)


def parquet_ok(path: str) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        pq.read_metadata(path)
    except Exception:
        return False
    return True


def outputs_for(root: str, release: str, dataset: str, index: int) -> list[str]:
    paths = [shard_path(root, release, dataset, index)]
    if dataset == "papers":
        partial = partial_dir(root, release)
        paths.append(os.path.join(partial, f"shard-{index:05d}.csids.npy"))
        paths.append(os.path.join(partial, f"shard-{index:05d}.arxiv.parquet"))
    elif dataset == "citations":
        paths.append(shard_path(root, release, "citations-cs", index))
    return paths


def shard_complete(root: str, release: str, dataset: str, index: int) -> bool:
    paths = outputs_for(root, release, dataset, index)
    for path in paths:
        if path.endswith(".parquet"):
            if not parquet_ok(path):
                return False
        elif not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
    return True


def _remove(paths: Iterable[str]) -> None:
    for path in paths:
        if os.path.exists(path):
            os.remove(path)
        partial = path + ".partial"
        if os.path.exists(partial):
            os.remove(partial)


class StopShard(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def process_records(
    dataset: str,
    records: Iterator[tuple[str, dict | None]],
    *,
    root: str,
    release: str,
    index: int,
    cs: CSIndex | None = None,
    batch_size: int | None = None,
    should_stop: Callable[[], str | None] | None = None,
) -> dict:
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset}")
    if dataset in NEEDS_CS and cs is None:
        raise RuntimeError(f"{dataset} requires the CS corpus id bitmap")

    batch = batch_size or BATCH_SIZE[dataset]
    paths = outputs_for(root, release, dataset, index)
    writers: list = []
    cs_ids: array.array = array.array("I")
    cs_overflow: list[int] = []
    bad_lines = 0
    rows_in = 0
    cs_rows = 0
    both_cs = 0
    arxiv_rows = 0
    vector_dim = None
    max_buffered = 0
    flushes = 0
    started = time.perf_counter()

    def stop_if_needed() -> None:
        if should_stop is None or rows_in % batch != 0:
            return
        reason = should_stop()
        if reason:
            raise StopShard(reason)

    try:
        if dataset == "embeddings-specter_v2":
            writer = EmbeddingWriter(paths[0], batch)
            writers.append(writer)
            for kind, record in records:
                rows_in += 1
                if kind != "ok" or record is None:
                    bad_lines += 1
                    stop_if_needed()
                    continue
                corpus_id = _as_int(record.get("corpusid", record.get("corpusId")))
                if corpus_id is None or not cs.contains(corpus_id):
                    stop_if_needed()
                    continue
                try:
                    vector = parse_vector(record.get("vector"))
                    writer.write(corpus_id, vector)
                except Exception:
                    bad_lines += 1
                    stop_if_needed()
                    continue
                cs_rows += 1
                stop_if_needed()
            vector_dim = writer.dim
        elif dataset == "papers":
            writer = BatchWriter(paths[0], PAPERS_SCHEMA, batch)
            arxiv_writer = BatchWriter(
                os.path.join(partial_dir(root, release), f"shard-{index:05d}.arxiv.parquet"),
                ARXIV_SCHEMA,
                batch,
            )
            writers.extend((writer, arxiv_writer))
            for kind, record in records:
                rows_in += 1
                if kind != "ok" or record is None:
                    bad_lines += 1
                    stop_if_needed()
                    continue
                row = paper_row(record)
                writer.write(row)
                corpus_id = row["corpusid"]
                if corpus_id is not None and corpus_id >= 0 and is_computer_science(record):
                    if corpus_id > 0xFFFFFFFF:
                        cs_overflow.append(corpus_id)
                    else:
                        cs_ids.append(corpus_id)
                    cs_rows += 1
                arxiv = extract_arxiv(record)
                if arxiv and corpus_id is not None:
                    arxiv_writer.write(
                        {
                            "arxiv_id": arxiv,
                            "arxiv_id_versionless": versionless_arxiv(arxiv),
                            "corpusid": corpus_id,
                        }
                    )
                    arxiv_rows += 1
                stop_if_needed()
        elif dataset == "abstracts":
            writer = BatchWriter(paths[0], ABSTRACTS_SCHEMA, batch)
            writers.append(writer)
            for kind, record in records:
                rows_in += 1
                if kind != "ok" or record is None:
                    bad_lines += 1
                    stop_if_needed()
                    continue
                writer.write(abstract_row(record))
                stop_if_needed()
        elif dataset == "tldrs":
            writer = BatchWriter(paths[0], TLDRS_SCHEMA, batch)
            writers.append(writer)
            for kind, record in records:
                rows_in += 1
                if kind != "ok" or record is None:
                    bad_lines += 1
                    stop_if_needed()
                    continue
                writer.write(tldr_row(record))
                stop_if_needed()
        else:
            full = BatchWriter(paths[0], CITATIONS_SCHEMA, batch)
            cs_writer = BatchWriter(paths[1], CITATIONS_CS_SCHEMA, batch)
            writers.extend((full, cs_writer))
            for kind, record in records:
                rows_in += 1
                if kind != "ok" or record is None:
                    bad_lines += 1
                    stop_if_needed()
                    continue
                row = citation_row(record)
                full.write(row)
                citing = cs.contains(row["citingcorpusid"])
                cited = cs.contains(row["citedcorpusid"])
                if citing or cited:
                    flagged = dict(row)
                    flagged["citing_is_cs"] = citing
                    flagged["cited_is_cs"] = cited
                    flagged["both_cs"] = citing and cited
                    cs_writer.write(flagged)
                    cs_rows += 1
                    if citing and cited:
                        both_cs += 1
                stop_if_needed()

        for writer in writers:
            writer.close()
        if writers:
            max_buffered = max(writer.max_buffered for writer in writers)
            flushes = sum(writer.flushes for writer in writers)
        if dataset == "papers":
            stored = np.frombuffer(cs_ids, dtype=np.uint32).copy()
            if cs_overflow:
                stored = np.concatenate(
                    [stored.astype(np.int64), np.asarray(cs_overflow, dtype=np.int64)]
                )
            atomic_npy(os.path.join(partial_dir(root, release), f"shard-{index:05d}.csids.npy"), stored)
    except Exception:
        for writer in writers:
            writer.abort()
        _remove(paths)
        raise

    main = paths[0]
    rows = pq.read_metadata(main).num_rows if parquet_ok(main) else 0
    output_bytes = sum(_file_size(path) for path in paths)
    return {
        "ok": True,
        "dataset": dataset,
        "index": index,
        "rows_in": rows_in,
        "rows": rows,
        "bad_lines": bad_lines,
        "cs_rows": cs_rows,
        "both_cs": both_cs,
        "arxiv_rows": arxiv_rows,
        "vector_dim": vector_dim,
        "output_bytes": output_bytes,
        "wall_seconds": time.perf_counter() - started,
        "peak_ram_mib": peak_rss_mib(),
        "max_buffered": max_buffered,
        "flushes": flushes,
        "batch_size": batch,
    }


def process_gzip_path(
    dataset: str,
    gz_path: str,
    *,
    root: str,
    release: str,
    index: int,
    cs: CSIndex | None = None,
    batch_size: int | None = None,
    should_stop: Callable[[], str | None] | None = None,
    reader: CountingReader | None = None,
) -> dict:
    raw = reader or CountingReader(open(gz_path, "rb"))
    owns = reader is None
    gz = gzip_stream(raw)
    try:
        result = process_records(
            dataset,
            iter_records(gz),
            root=root,
            release=release,
            index=index,
            cs=cs,
            batch_size=batch_size,
            should_stop=should_stop,
        )
    finally:
        gz.close()
        if owns:
            raw.close()
    result["input_bytes"] = _file_size(gz_path)
    result["stream_max_read"] = raw.max_read
    result["stream_read_all"] = raw.read_all
    result["stream_bytes"] = raw.bytes_read
    if result["wall_seconds"] > 0 and result["input_bytes"]:
        result["mb_per_s"] = (result["input_bytes"] / 1e6) / result["wall_seconds"]
    else:
        result["mb_per_s"] = 0.0
    result["output_gb"] = result["output_bytes"] / 1e9
    return result


def merge_cs(root: str, release: str, *, partial: bool = False) -> dict:
    """Merge per-shard CS ids. ``partial`` stays true when the shards are a sample."""
    partial_root = partial_dir(root, release)
    paths = []
    if os.path.isdir(partial_root):
        paths = sorted(
            os.path.join(partial_root, name)
            for name in os.listdir(partial_root)
            if name.endswith(".csids.npy")
        )
    arrays = [np.load(path).astype(np.int64, copy=False) for path in paths]
    if arrays:
        combined = np.concatenate(arrays)
    else:
        combined = np.zeros(0, dtype=np.int64)
    index, stored = build_cs_index(combined)
    directory = cs_dir(root, release)
    save_cs(directory, index, stored, release, partial=partial)

    arxiv_paths = []
    if os.path.isdir(partial_root):
        arxiv_paths = sorted(
            os.path.join(partial_root, name)
            for name in os.listdir(partial_root)
            if name.endswith(".arxiv.parquet")
        )
    dest = os.path.join(directory, "arxiv_corpusid.parquet")
    writer = BatchWriter(dest, ARXIV_SCHEMA, 4096)
    arxiv_rows = 0
    try:
        for path in arxiv_paths:
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=4096):
                rows = batch.to_pylist()
                for row in rows:
                    writer.write(row)
                    arxiv_rows += 1
        writer.close()
    except Exception:
        writer.abort()
        raise
    return {
        "ok": True,
        "cs_papers": index.count,
        "max_id": index.max_id,
        "partial_shards": len(paths),
        "partial": bool(partial),
        "arxiv_rows": arxiv_rows,
        "output_bytes": sum(_file_size(os.path.join(directory, name)) for name in os.listdir(directory)),
    }


def _parquet_stats(directory: str) -> dict:
    rows = 0
    files = 0
    output_bytes = 0
    if not os.path.isdir(directory):
        return {"rows": 0, "files": 0, "output_bytes": 0, "present": False}
    for dirpath, dirnames, names in os.walk(directory):
        dirnames[:] = [name for name in dirnames if name != "_partial"]
        for name in names:
            path = os.path.join(dirpath, name)
            output_bytes += os.path.getsize(path)
            if name.endswith(".parquet"):
                rows += pq.read_metadata(path).num_rows
                files += 1
    return {"rows": rows, "files": files, "output_bytes": output_bytes, "present": files > 0}


def _both_cs_count(directory: str) -> int:
    if not os.path.isdir(directory):
        return 0
    total = 0
    for dirpath, _, names in os.walk(directory):
        for name in names:
            if not name.endswith(".parquet"):
                continue
            parquet = pq.ParquetFile(os.path.join(dirpath, name))
            if "both_cs" not in parquet.schema_arrow.names:
                continue
            for batch in parquet.iter_batches(columns=["both_cs"], batch_size=65536):
                values = batch.column("both_cs").fill_null(False).to_numpy(zero_copy_only=False)
                total += int(np.asarray(values, dtype=bool).sum())
    return total


def _arxiv_coverage(root: str, release: str, cs: CSIndex | None) -> dict:
    path = os.path.join(cs_dir(root, release), "arxiv_corpusid.parquet")
    if not parquet_ok(path) or cs is None:
        return {"arxiv_rows": 0, "arxiv_rows_in_cs": 0, "cs_papers_with_arxiv": 0}
    rows = 0
    in_cs = 0
    seen = np.zeros_like(cs.bits)
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(columns=["corpusid"], batch_size=65536):
        ids = batch.column("corpusid").fill_null(-1).to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
        rows += int(ids.shape[0])
        mask = cs.contains_many(ids)
        in_cs += int(mask.sum())
        hit = ids[mask]
        if hit.size:
            masks = np.left_shift(np.uint8(1), (hit & 7).astype(np.uint8))
            np.bitwise_or.at(seen, hit >> 3, masks)
    return {
        "arxiv_rows": rows,
        "arxiv_rows_in_cs": in_cs,
        "cs_papers_with_arxiv": popcount(seen),
    }


def verify_tree(root: str, release: str) -> dict:
    release_root = os.path.join(root, release)
    datasets = {}
    for name in list(DATASETS) + ["citations-cs"]:
        stats = _parquet_stats(dataset_dir(root, release, name))
        datasets[name] = stats
    datasets["citations-cs"]["both_cs"] = _both_cs_count(dataset_dir(root, release, "citations-cs"))

    cs = None
    cs_papers = 0
    cs_meta_ok = False
    directory = cs_dir(root, release)
    meta_path = os.path.join(directory, "meta.json")
    if os.path.exists(meta_path):
        cs = load_cs(directory)
        stored = np.load(os.path.join(directory, "corpusids.npy"))
        cs_papers = int(stored.shape[0])
        cs_meta_ok = cs_papers == cs.count == popcount(cs.bits)

    coverage = _arxiv_coverage(root, release, cs)
    coverage_fraction = None
    if cs_papers:
        coverage_fraction = coverage["cs_papers_with_arxiv"] / cs_papers

    def tree_bytes(path: str) -> int:
        if not os.path.exists(path):
            return 0
        total = 0
        for dirpath, _, names in os.walk(path):
            for name in names:
                total += os.path.getsize(os.path.join(dirpath, name))
        return total

    release_bytes = tree_bytes(release_root)
    total_bytes = tree_bytes(root)
    present = [name for name, stats in datasets.items() if stats["present"]]
    return {
        "ok": os.path.isdir(release_root),
        "datasets_present": present,
        "release_id": release,
        "datasets": datasets,
        "cs_papers": cs_papers,
        "cs_index_consistent": cs_meta_ok,
        "cs_embeddings": datasets["embeddings-specter_v2"]["rows"],
        "arxiv_rows": coverage["arxiv_rows"],
        "arxiv_rows_in_cs": coverage["arxiv_rows_in_cs"],
        "cs_papers_with_arxiv": coverage["cs_papers_with_arxiv"],
        "cs_arxiv_coverage": coverage_fraction,
        "release_gb": release_bytes / 1e9,
        "total_gb": total_bytes / 1e9,
        "release_bytes": release_bytes,
        "total_bytes": total_bytes,
    }


def write_run_record(root: str, stage: str, payload: dict) -> str:
    directory = runs_dir(root)
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stamped = os.path.join(directory, f"{stage}-{stamp}.json")
    latest = os.path.join(directory, f"latest-{stage}.json")
    _write_json(stamped, payload)
    _write_json(latest, payload)
    return stamped
