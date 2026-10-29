"""Stream Semantic Scholar JSONL.gz shards into zstd Parquet.

Papers, abstracts, citations, and tldrs are decompressed in large
newline-aligned blocks and parsed with ``pyarrow.json`` (threaded, explicit
schema). Embeddings stay on a line parser because the vector column is a
JSON string. A shard is never held as one bytes object or one table. The CS
corpus id set is a sorted uint32 array plus a packed bitmap, not a Python set.
"""

from __future__ import annotations

import array
import io
import json
import os
import queue
import re
import resource
import sys
import threading
import time
from typing import Callable, Iterable, Iterator

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.json as pj
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

# Parse schemas accept both casings. Nested corpus ids are omitted so a numeric
# CorpusId does not fail the block; the top-level corpusid is the one we keep.
# Unknown keys are ignored (the output ``extra`` column stays null).
_EXT_PARSE_FIELDS = [
    ("ACL", pa.string()),
    ("acl", pa.string()),
    ("DBLP", pa.string()),
    ("dblp", pa.string()),
    ("ArXiv", pa.string()),
    ("arxiv", pa.string()),
    ("MAG", pa.string()),
    ("mag", pa.string()),
    ("PubMed", pa.string()),
    ("pubmed", pa.string()),
    ("DOI", pa.string()),
    ("doi", pa.string()),
    ("PubMedCentral", pa.string()),
    ("pubmedcentral", pa.string()),
    ("Medline", pa.string()),
    ("medline", pa.string()),
]
_EXT_PARSE = pa.struct(_EXT_PARSE_FIELDS)
_AUTHOR_PARSE = pa.struct(
    [("authorId", pa.string()), ("authorid", pa.string()), ("name", pa.string())]
)
_OA_PARSE = pa.struct(
    [
        ("externalids", _EXT_PARSE),
        ("externalIds", _EXT_PARSE),
        ("license", pa.string()),
        ("url", pa.string()),
        ("status", pa.string()),
        ("disclaimer", pa.string()),
    ]
)

PAPERS_PARSE_SCHEMA = pa.schema(
    [
        ("corpusid", pa.int64()),
        ("corpusId", pa.int64()),
        ("externalids", _EXT_PARSE),
        ("externalIds", _EXT_PARSE),
        ("url", pa.string()),
        ("title", pa.string()),
        ("authors", pa.list_(_AUTHOR_PARSE)),
        ("venue", pa.string()),
        ("publicationvenueid", pa.string()),
        ("year", pa.int64()),
        ("referencecount", pa.int64()),
        ("citationcount", pa.int64()),
        ("influentialcitationcount", pa.int64()),
        ("isopenaccess", pa.bool_()),
        ("s2fieldsofstudy", pa.list_(_FOS_TYPE)),
        ("s2FieldsOfStudy", pa.list_(_FOS_TYPE)),
        ("fieldsofstudy", pa.list_(pa.string())),
        ("fieldsOfStudy", pa.list_(pa.string())),
        ("publicationtypes", pa.list_(pa.string())),
        ("publicationdate", pa.string()),
        ("journal", _JOURNAL_TYPE),
    ]
)
ABSTRACTS_PARSE_SCHEMA = pa.schema(
    [
        ("corpusid", pa.int64()),
        ("corpusId", pa.int64()),
        ("abstract", pa.string()),
        ("openaccessinfo", _OA_PARSE),
        ("openAccessInfo", _OA_PARSE),
    ]
)
TLDRS_PARSE_SCHEMA = pa.schema(
    [
        ("corpusid", pa.int64()),
        ("corpusId", pa.int64()),
        ("model", pa.string()),
        ("text", pa.string()),
    ]
)
CITATIONS_PARSE_SCHEMA = pa.schema(
    [
        ("citationid", pa.int64()),
        ("citingcorpusid", pa.int64()),
        ("citedcorpusid", pa.int64()),
        ("isinfluential", pa.bool_()),
        ("contexts", pa.list_(pa.string())),
        ("intents", pa.list_(pa.string())),
    ]
)
_PARSE_SCHEMA = {
    "papers": PAPERS_PARSE_SCHEMA,
    "abstracts": ABSTRACTS_PARSE_SCHEMA,
    "tldrs": TLDRS_PARSE_SCHEMA,
    "citations": CITATIONS_PARSE_SCHEMA,
}
_PARSE_OPTIONS = {
    name: pj.ParseOptions(explicit_schema=schema, unexpected_field_behavior="ignore")
    for name, schema in _PARSE_SCHEMA.items()
}

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

# Decompressed JSON per parse. 64 MiB keeps the Arrow table under the 4 GiB
# container (peak stays well below 3 GiB). Callers may pass 32 KiB..256 MiB.
JSON_BLOCK_BYTES = 64 * 1024 * 1024
_JSON_DATASETS = frozenset({"papers", "abstracts", "tldrs", "citations"})
_JSON_READ = pj.ReadOptions(use_threads=True, block_size=16 * 1024 * 1024)

# Quote bare numbers only for fields whose Parquet type is a string. Top-level
# corpusid / year / counts stay numeric. Applied only after a block fails with
# a string-vs-number error, then kept on for the rest of the shard.
_NUMERIC_STRING_KEYS = re.compile(
    rb'("(?:authorId|authorid|ACL|acl|DBLP|dblp|ArXiv|arxiv|MAG|mag|'
    rb"PubMed|pubmed|DOI|doi|PubMedCentral|pubmedcentral|Medline|medline|"
    rb'publicationvenueid|volume|pages)"\s*:\s*)(-?\d+(?:\.\d+)?)'
)


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
        "parser": "python",
    }


def _use_cpu(cpu: float | None) -> None:
    if not cpu:
        return
    try:
        pa.set_cpu_count(max(1, int(cpu)))
    except Exception:
        pass


def _block_bytes(value: int | None) -> int:
    if value is None:
        return JSON_BLOCK_BYTES
    size = int(value)
    if size < 32 * 1024:
        size = 32 * 1024
    if size > 256 * 1024 * 1024:
        size = 256 * 1024 * 1024
    return size


def _combine(value):
    if isinstance(value, pa.ChunkedArray):
        return value.combine_chunks()
    return value


def _nulls(n: int, typ: pa.DataType) -> pa.Array:
    return pa.nulls(n, type=typ)


def _column(table: pa.Table, name: str, n: int, typ: pa.DataType) -> pa.Array:
    if name not in table.column_names:
        return _nulls(n, typ)
    col = table.column(name)
    if pa.types.is_null(col.type):
        return _nulls(n, typ)
    try:
        casted = pc.cast(col, typ, safe=True)
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
        return _nulls(n, typ)
    return _combine(casted)


def _coalesce_named(table: pa.Table, names: tuple[str, ...], n: int, typ: pa.DataType) -> pa.Array:
    chosen = None
    for name in names:
        if name not in table.column_names:
            continue
        col = table.column(name)
        if pa.types.is_null(col.type):
            continue
        try:
            casted = _combine(pc.cast(col, typ, safe=True))
        except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
            continue
        chosen = casted if chosen is None else _combine(pc.coalesce(chosen, casted))
    if chosen is None:
        return _nulls(n, typ)
    return chosen


def _pack_external(struct_arr, n: int) -> pa.Array:
    struct_arr = None if struct_arr is None else _combine(struct_arr)
    if struct_arr is None or pa.types.is_null(struct_arr.type) or not pa.types.is_struct(struct_arr.type):
        return _nulls(n, _EXT_TYPE)
    names = {field.name for field in struct_arr.type}
    arrays = []
    for src, canon in EXT_KEYS:
        chosen = None
        for key in (canon, src):
            if key not in names:
                continue
            col = _combine(pc.cast(pc.struct_field(struct_arr, key), pa.string(), safe=True))
            chosen = col if chosen is None else _combine(pc.coalesce(chosen, col))
        arrays.append(chosen if chosen is not None else _nulls(n, pa.string()))
    return pa.StructArray.from_arrays(arrays, names=[canon for _, canon in EXT_KEYS])


def _coalesce_external(table: pa.Table, names: tuple[str, ...], n: int) -> pa.Array:
    packed = []
    for name in names:
        if name not in table.column_names:
            continue
        col = table.column(name)
        if pa.types.is_null(col.type):
            continue
        packed.append(_pack_external(col, n))
    if not packed:
        return _nulls(n, _EXT_TYPE)
    acc = packed[0]
    for item in packed[1:]:
        acc = _combine(pc.coalesce(acc, item))
    return acc


def _rebuild_authors(table: pa.Table, n: int) -> pa.Array:
    if "authors" not in table.column_names:
        return _nulls(n, pa.list_(_AUTHOR_TYPE))
    arr = _combine(table.column("authors"))
    if pa.types.is_null(arr.type) or not pa.types.is_list(arr.type):
        return _nulls(n, pa.list_(_AUTHOR_TYPE))
    flat = _combine(pc.list_flatten(arr))
    if not pa.types.is_struct(flat.type):
        return _nulls(n, pa.list_(_AUTHOR_TYPE))
    fields = {field.name for field in flat.type}
    chosen = None
    for key in ("authorId", "authorid"):
        if key not in fields:
            continue
        col = _combine(pc.cast(pc.struct_field(flat, key), pa.string(), safe=True))
        chosen = col if chosen is None else _combine(pc.coalesce(chosen, col))
    if chosen is None:
        chosen = _nulls(len(flat), pa.string())
    name = (
        _combine(pc.cast(pc.struct_field(flat, "name"), pa.string(), safe=True))
        if "name" in fields
        else _nulls(len(flat), pa.string())
    )
    values = pa.StructArray.from_arrays([chosen, name], names=["authorId", "name"])
    mask = arr.is_null() if hasattr(arr, "is_null") else None
    return pa.ListArray.from_arrays(arr.offsets, values, mask=mask)


def _list_strings(table: pa.Table, names: tuple[str, ...], n: int) -> pa.Array:
    typ = pa.list_(pa.string())
    return _coalesce_named(table, names, n, typ)


def _any_equal(list_arr, n: int, *, field: str | None) -> np.ndarray:
    """True where any list element equals 'computer science' (trimmed, lower)."""
    out = np.zeros(n, dtype=bool)
    if list_arr is None:
        return out
    arr = _combine(list_arr)
    if pa.types.is_null(arr.type) or not pa.types.is_list(arr.type) or len(arr) == 0:
        return out
    flat = _combine(pc.list_flatten(arr))
    if len(flat) == 0:
        return out
    if field is not None:
        names = {item.name for item in flat.type}
        if not pa.types.is_struct(flat.type) or field not in names:
            return out
        values = pc.struct_field(flat, field)
    else:
        values = flat
    try:
        text = pc.utf8_lower(pc.utf8_trim_whitespace(pc.cast(values, pa.string(), safe=True)))
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
        return out
    flag = _combine(pc.fill_null(pc.equal(text, CS_CATEGORY), False))
    parents = _combine(pc.list_parent_indices(arr)).to_numpy(zero_copy_only=False)
    flags = np.asarray(flag.to_numpy(zero_copy_only=False), dtype=bool)
    if parents.size:
        np.logical_or.at(out, parents, flags)
    return out


def _cs_mask(table: pa.Table) -> np.ndarray:
    n = table.num_rows
    mask = np.zeros(n, dtype=bool)
    for name in ("s2fieldsofstudy", "s2FieldsOfStudy"):
        if name in table.column_names:
            mask |= _any_equal(table.column(name), n, field="category")
    for name in ("fieldsofstudy", "fieldsOfStudy"):
        if name in table.column_names:
            mask |= _any_equal(table.column(name), n, field=None)
    return mask


def _intents_json(column, n: int) -> pa.Array:
    if column is None or pa.types.is_null(column.type):
        return _nulls(n, pa.string())
    values = _combine(column).to_pylist()
    encoded = []
    for value in values:
        if value is None:
            encoded.append(None)
        else:
            encoded.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return pa.array(encoded, type=pa.string())


def _align_papers(table: pa.Table) -> tuple[pa.Table, np.ndarray, pa.Table]:
    n = table.num_rows
    corpus = _coalesce_named(table, ("corpusid", "corpusId"), n, pa.int64())
    external = _coalesce_external(table, ("externalids", "externalIds"), n)
    year = _coalesce_named(table, ("year",), n, pa.int32())
    fos = _coalesce_named(table, ("s2fieldsofstudy", "s2FieldsOfStudy"), n, pa.list_(_FOS_TYPE))
    fields = _list_strings(table, ("fieldsofstudy", "fieldsOfStudy"), n)
    journal = _column(table, "journal", n, _JOURNAL_TYPE)
    out = pa.Table.from_arrays(
        [
            corpus,
            external,
            _column(table, "url", n, pa.string()),
            _column(table, "title", n, pa.string()),
            _rebuild_authors(table, n),
            _column(table, "venue", n, pa.string()),
            _column(table, "publicationvenueid", n, pa.string()),
            year,
            _column(table, "referencecount", n, pa.int64()),
            _column(table, "citationcount", n, pa.int64()),
            _column(table, "influentialcitationcount", n, pa.int64()),
            _column(table, "isopenaccess", n, pa.bool_()),
            fos,
            fields,
            _column(table, "publicationtypes", n, pa.list_(pa.string())),
            _column(table, "publicationdate", n, pa.string()),
            journal,
            _nulls(n, pa.string()),
        ],
        schema=PAPERS_SCHEMA,
    )
    mask = _cs_mask(table)
    ids = np.asarray(pc.fill_null(corpus, -1).to_numpy(zero_copy_only=False), dtype=np.int64)
    arxiv = None
    ext = _combine(external)
    if pa.types.is_struct(ext.type) and "ArXiv" in {field.name for field in ext.type}:
        arxiv = pc.utf8_trim_whitespace(pc.struct_field(ext, "ArXiv"))
    if arxiv is None:
        arxiv_table = pa.Table.from_pylist([], schema=ARXIV_SCHEMA)
    else:
        text = _combine(arxiv)
        valid_text = pc.and_(pc.is_valid(text), pc.not_equal(text, ""))
        valid_id = pa.array(ids >= 0)
        valid = _combine(pc.and_(valid_text, valid_id))
        if pc.sum(valid).as_py() == 0:
            arxiv_table = pa.Table.from_pylist([], schema=ARXIV_SCHEMA)
        else:
            kept_text = _combine(pc.filter(text, valid))
            kept_ids = _combine(pc.filter(corpus, valid))
            versionless = _combine(pc.replace_substring_regex(kept_text, r"v\d+$", ""))
            arxiv_table = pa.Table.from_arrays(
                [kept_text, versionless, kept_ids],
                schema=ARXIV_SCHEMA,
            )
    return out, mask, arxiv_table


def _align_openaccess(table: pa.Table, n: int) -> pa.Array:
    packed = []
    for name in ("openaccessinfo", "openAccessInfo"):
        if name not in table.column_names:
            continue
        col = _combine(table.column(name))
        if not pa.types.is_struct(col.type):
            continue
        names = {field.name for field in col.type}
        external = None
        for key in ("externalids", "externalIds"):
            if key in names:
                external = _pack_external(pc.struct_field(col, key), n)
                break
        if external is None:
            external = _nulls(n, _EXT_TYPE)

        def field(key: str) -> pa.Array:
            if key not in names:
                return _nulls(n, pa.string())
            return _combine(pc.cast(pc.struct_field(col, key), pa.string(), safe=True))

        packed.append(
            pa.StructArray.from_arrays(
                [external, field("license"), field("url"), field("status"), field("disclaimer")],
                names=["externalids", "license", "url", "status", "disclaimer"],
            )
        )
    if not packed:
        return _nulls(n, _OA_TYPE)
    acc = packed[0]
    for item in packed[1:]:
        acc = _combine(pc.coalesce(acc, item))
    return acc


def _align_abstracts(table: pa.Table) -> pa.Table:
    n = table.num_rows
    return pa.Table.from_arrays(
        [
            _coalesce_named(table, ("corpusid", "corpusId"), n, pa.int64()),
            _column(table, "abstract", n, pa.string()),
            _align_openaccess(table, n),
            _nulls(n, pa.string()),
        ],
        schema=ABSTRACTS_SCHEMA,
    )


def _align_tldrs(table: pa.Table) -> pa.Table:
    n = table.num_rows
    return pa.Table.from_arrays(
        [
            _coalesce_named(table, ("corpusid", "corpusId"), n, pa.int64()),
            _column(table, "model", n, pa.string()),
            _column(table, "text", n, pa.string()),
            _nulls(n, pa.string()),
        ],
        schema=TLDRS_SCHEMA,
    )


def _align_citations(table: pa.Table) -> pa.Table:
    n = table.num_rows
    intents = table.column("intents") if "intents" in table.column_names else None
    return pa.Table.from_arrays(
        [
            _column(table, "citationid", n, pa.int64()),
            _column(table, "citingcorpusid", n, pa.int64()),
            _column(table, "citedcorpusid", n, pa.int64()),
            _column(table, "isinfluential", n, pa.bool_()),
            _list_strings(table, ("contexts",), n),
            _intents_json(intents, n),
            _nulls(n, pa.string()),
        ],
        schema=CITATIONS_SCHEMA,
    )


def _read_json_block(dataset: str, block: bytes) -> pa.Table:
    return pj.read_json(
        io.BytesIO(block),
        read_options=_JSON_READ,
        parse_options=_PARSE_OPTIONS[dataset],
    )


def _quote_string_ids(block: bytes) -> bytes:
    return _NUMERIC_STRING_KEYS.sub(rb'\1"\2"', block)


class _ParseState:
    def __init__(self):
        self.quote_ids = False

    def parse(self, dataset: str, block: bytes) -> pa.Table:
        data = _quote_string_ids(block) if self.quote_ids else block
        try:
            return _read_json_block(dataset, data)
        except pa.ArrowInvalid as exc:
            text = str(exc)
            if not self.quote_ids and "changed from string to number" in text:
                self.quote_ids = True
                return _read_json_block(dataset, _quote_string_ids(block))
            raise


def _split_block(block: bytes) -> tuple[bytes, bytes] | None:
    if block.count(b"\n") <= 1:
        return None
    mid = len(block) // 2
    cut = block.rfind(b"\n", 0, mid)
    if cut < 0:
        cut = block.find(b"\n", mid)
    if cut <= 0 or cut >= len(block) - 1:
        return None
    return block[: cut + 1], block[cut + 1 :]


class TableWriter:
    """Write Arrow tables as zstd row groups. One table is one flush."""

    def __init__(self, path: str, schema: pa.Schema):
        self.path = path
        self.schema = schema
        self.rows = 0
        self.max_buffered = 0
        self.flushes = 0
        self._writer: pq.ParquetWriter | None = None
        self._tmp = path + ".partial"

    def write_table(self, table: pa.Table) -> None:
        if table is None or table.num_rows == 0:
            return
        if table.schema != self.schema:
            table = table.cast(self.schema, safe=False)
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._writer = pq.ParquetWriter(self._tmp, self.schema, compression="zstd")
        self._writer.write_table(table, row_group_size=max(table.num_rows, 1))
        self.rows += table.num_rows
        self.max_buffered = max(self.max_buffered, table.num_rows)
        self.flushes += 1

    def close(self) -> None:
        if self._writer is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            pq.write_table(pa.Table.from_pylist([], schema=self.schema), self._tmp, compression="zstd")
            self.flushes += 1
        else:
            self._writer.close()
            self._writer = None
        os.replace(self._tmp, self.path)

    def abort(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        if os.path.exists(self._tmp):
            os.remove(self._tmp)
        if os.path.exists(self.path):
            os.remove(self.path)


def iter_json_blocks(gz, block_bytes: int) -> Iterator[tuple[bytes, int]]:
    """Yield decompressed newline-terminated blocks and a bad-line count.

    A block ends on a newline at or just after ``block_bytes``. A single line
    may run past that (up to ``MAX_LINE_BYTES``) so a record is never split.
    Longer lines are counted as bad and dropped.
    """
    buf = bytearray()
    pending_bad = 0
    read_size = 8 * 1024 * 1024

    def take(end: int) -> tuple[bytes, int]:
        nonlocal pending_bad
        piece = bytes(buf[: end + 1])
        del buf[: end + 1]
        bad = pending_bad
        pending_bad = 0
        return piece, bad

    while True:
        if len(buf) >= block_bytes:
            cut = buf.rfind(b"\n", 0, block_bytes)
            if cut >= 0:
                piece, bad = take(cut)
                if piece and not piece.isspace():
                    yield piece, bad
                continue
            cut = buf.find(b"\n")
            if cut >= 0:
                if cut > MAX_LINE_BYTES:
                    del buf[: cut + 1]
                    pending_bad += 1
                else:
                    piece, bad = take(cut)
                    if piece and not piece.isspace():
                        yield piece, bad
                continue
            if len(buf) > MAX_LINE_BYTES * 2:
                pending_bad += 1
                buf.clear()
        chunk = gz.read(read_size)
        if not chunk:
            # The tail is smaller than one block. Flush it on newline
            # boundaries instead of treating the whole tail as one line.
            if buf and not buf.endswith(b"\n"):
                buf.extend(b"\n")
            while buf:
                window = min(len(buf), block_bytes)
                cut = buf.rfind(b"\n", 0, window)
                if cut < 0:
                    cut = buf.find(b"\n")
                    if cut < 0 or cut > MAX_LINE_BYTES:
                        pending_bad += 1
                        buf.clear()
                        break
                piece, bad = take(cut)
                if piece and not piece.isspace():
                    yield piece, bad
            if pending_bad:
                yield b"", pending_bad
            return
        buf.extend(chunk)


def _append_cs_ids(chunks: list[np.ndarray], ids: np.ndarray) -> None:
    if ids.size:
        chunks.append(np.asarray(ids, dtype=np.int64))


def _store_cs_ids(chunks: list[np.ndarray]) -> np.ndarray:
    if not chunks:
        return np.zeros(0, dtype=np.uint32)
    values = np.concatenate(chunks)
    if values.size and int(values.max()) > np.iinfo(np.uint32).max:
        return values
    return values.astype(np.uint32, copy=False)


def process_json_blocks(
    dataset: str,
    gz,
    *,
    root: str,
    release: str,
    index: int,
    cs: CSIndex | None = None,
    should_stop: Callable[[], str | None] | None = None,
    cpu: float | None = None,
    block_bytes: int | None = None,
) -> dict:
    """Parse one JSONL gzip body with pyarrow and write zstd Parquet."""
    if dataset not in _JSON_DATASETS:
        raise ValueError(f"{dataset} is not a JSONL dataset")
    if dataset in NEEDS_CS and cs is None:
        raise RuntimeError(f"{dataset} requires the CS corpus id bitmap")
    _use_cpu(cpu)
    size = _block_bytes(block_bytes)
    paths = outputs_for(root, release, dataset, index)
    writers: list[TableWriter] = []
    cs_chunks: list[np.ndarray] = []
    bad_lines = 0
    rows_in = 0
    cs_rows = 0
    both_cs = 0
    arxiv_rows = 0
    started = time.perf_counter()
    blocks_seen = 0
    state = _ParseState()
    stop_read = threading.Event()

    def check_stop() -> None:
        if should_stop is None:
            return
        reason = should_stop()
        if reason:
            raise StopShard(reason)

    def write_fallback(line: bytes, writer: TableWriter, arxiv_writer: TableWriter | None, cs_writer: TableWriter | None) -> None:
        nonlocal bad_lines, rows_in, cs_rows, both_cs, arxiv_rows
        rows_in += 1
        stripped = line.strip()
        if not stripped:
            return
        if len(stripped) > MAX_LINE_BYTES:
            bad_lines += 1
            return
        try:
            record = loads(stripped)
        except Exception:
            bad_lines += 1
            return
        if dataset == "papers":
            row = paper_row(record)
            writer.write_table(pa.Table.from_pylist([row], schema=PAPERS_SCHEMA))
            corpus_id = row["corpusid"]
            if corpus_id is not None and corpus_id >= 0 and is_computer_science(record):
                _append_cs_ids(cs_chunks, np.asarray([corpus_id], dtype=np.int64))
                cs_rows += 1
            arxiv = extract_arxiv(record)
            if arxiv and corpus_id is not None and arxiv_writer is not None:
                arxiv_writer.write_table(
                    pa.Table.from_pylist(
                        [
                            {
                                "arxiv_id": arxiv,
                                "arxiv_id_versionless": versionless_arxiv(arxiv),
                                "corpusid": corpus_id,
                            }
                        ],
                        schema=ARXIV_SCHEMA,
                    )
                )
                arxiv_rows += 1
            return
        if dataset == "abstracts":
            writer.write_table(pa.Table.from_pylist([abstract_row(record)], schema=ABSTRACTS_SCHEMA))
            return
        if dataset == "tldrs":
            writer.write_table(pa.Table.from_pylist([tldr_row(record)], schema=TLDRS_SCHEMA))
            return
        row = citation_row(record)
        writer.write_table(pa.Table.from_pylist([row], schema=CITATIONS_SCHEMA))
        if cs is None or cs_writer is None:
            return
        citing = bool(cs.contains(row["citingcorpusid"]))
        cited = bool(cs.contains(row["citedcorpusid"]))
        if citing or cited:
            flagged = dict(row)
            flagged["citing_is_cs"] = citing
            flagged["cited_is_cs"] = cited
            flagged["both_cs"] = citing and cited
            cs_writer.write_table(pa.Table.from_pylist([flagged], schema=CITATIONS_CS_SCHEMA))
            cs_rows += 1
            if citing and cited:
                both_cs += 1

    def emit_table(table: pa.Table, writer: TableWriter, arxiv_writer: TableWriter | None, cs_writer: TableWriter | None) -> None:
        nonlocal rows_in, cs_rows, both_cs, arxiv_rows
        if table is None or table.num_rows == 0:
            return
        rows_in += table.num_rows
        if dataset == "papers":
            out, mask, arxiv_table = _align_papers(table)
            writer.write_table(out)
            ids = np.asarray(pc.fill_null(out.column("corpusid"), -1).to_numpy(zero_copy_only=False), dtype=np.int64)
            chosen = ids[mask & (ids >= 0)]
            _append_cs_ids(cs_chunks, chosen)
            cs_rows += int(chosen.size)
            if arxiv_writer is not None and arxiv_table.num_rows:
                arxiv_writer.write_table(arxiv_table)
                arxiv_rows += arxiv_table.num_rows
            return
        if dataset == "abstracts":
            writer.write_table(_align_abstracts(table))
            return
        if dataset == "tldrs":
            writer.write_table(_align_tldrs(table))
            return
        out = _align_citations(table)
        writer.write_table(out)
        if cs is None or cs_writer is None:
            return
        citing_ids = np.asarray(pc.fill_null(out.column("citingcorpusid"), -1).to_numpy(zero_copy_only=False), dtype=np.int64)
        cited_ids = np.asarray(pc.fill_null(out.column("citedcorpusid"), -1).to_numpy(zero_copy_only=False), dtype=np.int64)
        citing = cs.contains_many(citing_ids)
        cited = cs.contains_many(cited_ids)
        keep = citing | cited
        cs_rows += int(keep.sum())
        both = citing & cited
        both_cs += int(both.sum())
        if not np.any(keep):
            return
        mask = pa.array(keep)
        filtered = out.filter(mask)
        flagged = filtered.append_column("citing_is_cs", pa.array(citing[keep]))
        flagged = flagged.append_column("cited_is_cs", pa.array(cited[keep]))
        flagged = flagged.append_column("both_cs", pa.array(both[keep]))
        cs_writer.write_table(flagged.cast(CITATIONS_CS_SCHEMA, safe=False))

    def consume(block: bytes, writer: TableWriter, arxiv_writer: TableWriter | None, cs_writer: TableWriter | None) -> None:
        if not block or block.isspace():
            return
        try:
            emit_table(state.parse(dataset, block), writer, arxiv_writer, cs_writer)
            return
        except pa.ArrowInvalid:
            pass
        parts = _split_block(block)
        if parts is None:
            write_fallback(block, writer, arxiv_writer, cs_writer)
            return
        consume(parts[0], writer, arxiv_writer, cs_writer)
        consume(parts[1], writer, arxiv_writer, cs_writer)

    arxiv_writer: TableWriter | None = None
    cs_writer: TableWriter | None = None
    try:
        check_stop()
        if dataset == "papers":
            writer = TableWriter(paths[0], PAPERS_SCHEMA)
            arxiv_writer = TableWriter(
                os.path.join(partial_dir(root, release), f"shard-{index:05d}.arxiv.parquet"),
                ARXIV_SCHEMA,
            )
            writers.extend((writer, arxiv_writer))
        elif dataset == "abstracts":
            writer = TableWriter(paths[0], ABSTRACTS_SCHEMA)
            writers.append(writer)
        elif dataset == "tldrs":
            writer = TableWriter(paths[0], TLDRS_SCHEMA)
            writers.append(writer)
        else:
            writer = TableWriter(paths[0], CITATIONS_SCHEMA)
            cs_writer = TableWriter(paths[1], CITATIONS_CS_SCHEMA)
            writers.extend((writer, cs_writer))

        blocks: queue.Queue = queue.Queue(maxsize=1)
        producer_error: list[BaseException] = []

        def produce() -> None:
            try:
                for block, skipped in iter_json_blocks(gz, size):
                    if stop_read.is_set():
                        return
                    blocks.put((block, skipped))
            except BaseException as exc:
                producer_error.append(exc)
            finally:
                blocks.put(None)

        reader = threading.Thread(target=produce, name="s2-json-blocks", daemon=True)
        reader.start()
        try:
            while True:
                item = blocks.get()
                if item is None:
                    break
                check_stop()
                block, skipped = item
                bad_lines += int(skipped)
                rows_in += int(skipped)
                if block and not block.isspace():
                    blocks_seen += 1
                consume(block, writer, arxiv_writer, cs_writer)
        finally:
            stop_read.set()
            while reader.is_alive():
                try:
                    leftover = blocks.get(timeout=0.2)
                except queue.Empty:
                    continue
                if leftover is None:
                    break
            reader.join(timeout=5)

        if producer_error:
            raise producer_error[0]

        for item in writers:
            item.close()
        if dataset == "papers":
            atomic_npy(
                os.path.join(partial_dir(root, release), f"shard-{index:05d}.csids.npy"),
                _store_cs_ids(cs_chunks),
            )
    except Exception:
        stop_read.set()
        for item in writers:
            item.abort()
        _remove(paths)
        raise

    main = paths[0]
    rows = pq.read_metadata(main).num_rows if parquet_ok(main) else 0
    output_bytes = sum(_file_size(path) for path in paths)
    max_buffered = max((item.max_buffered for item in writers), default=0)
    flushes = sum(item.flushes for item in writers)
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
        "vector_dim": None,
        "output_bytes": output_bytes,
        "wall_seconds": time.perf_counter() - started,
        "peak_ram_mib": peak_rss_mib(),
        "max_buffered": max_buffered,
        "flushes": flushes,
        "blocks": blocks_seen,
        "batch_size": size,
        "block_bytes": size,
        "parser": "pyarrow.json",
        "quote_ids": state.quote_ids,
    }


def process_stream(
    dataset: str,
    gz,
    *,
    root: str,
    release: str,
    index: int,
    cs: CSIndex | None = None,
    batch_size: int | None = None,
    should_stop: Callable[[], str | None] | None = None,
    cpu: float | None = None,
    block_bytes: int | None = None,
) -> dict:
    """Dispatch one decompressed shard. JSONL datasets use the block parser."""
    _use_cpu(cpu)
    if dataset in _JSON_DATASETS:
        return process_json_blocks(
            dataset,
            gz,
            root=root,
            release=release,
            index=index,
            cs=cs,
            should_stop=should_stop,
            cpu=cpu,
            block_bytes=block_bytes,
        )
    return process_records(
        dataset,
        iter_records(gz),
        root=root,
        release=release,
        index=index,
        cs=cs,
        batch_size=batch_size,
        should_stop=should_stop,
    )


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
    cpu: float | None = None,
    block_bytes: int | None = None,
) -> dict:
    raw = reader or CountingReader(open(gz_path, "rb"))
    owns = reader is None
    gz = gzip_stream(raw)
    try:
        result = process_stream(
            dataset,
            gz,
            root=root,
            release=release,
            index=index,
            cs=cs,
            batch_size=batch_size,
            should_stop=should_stop,
            cpu=cpu,
            block_bytes=block_bytes,
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
