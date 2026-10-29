"""Stream one Semantic Scholar release onto the rrm-data volume as zstd Parquet.

Shards are fetched with presigned URLs taken once per dataset. Each container
decompresses with isal, parses 64 MiB newline-aligned blocks, and writes
part-NNNN.parquet. Citations and papers use one explicit Arrow schema so list
columns are never cast between blocks (that cast corrupts list offsets).
"""

import io
import json
import os
import re
import time
from pathlib import Path

import modal

BASE = "https://api.semanticscholar.org/datasets/v1/"
MOUNT = "/s2"
BLOCK = 64 << 20
MB = 1 << 20
_CID = re.compile(rb'"(?:corpusid|corpusId)"\s*:\s*(\d+)')
# The vector is usually a JSON string ("[0.1, -0.2]"), sometimes a bare array.
_VEC = re.compile(rb'"vector"\s*:\s*"?\[([^\]]*)\]')
_QUOTE_IDS = re.compile(
    rb'"(ACL|acl|DBLP|dblp|ArXiv|arxiv|MAG|mag|CorpusId|PubMed|pubmed|'
    rb'DOI|doi|PubMedCentral|pubmedcentral|authorId|authorid|volume|pages)"'
    rb'\s*:\s*(-?\d+)(?![\d.])'
)
_EXT_NAMES = ["ACL", "DBLP", "ArXiv", "MAG", "CorpusId", "PubMed", "DOI", "PubMedCentral"]
_JOURNAL_NAMES = ["name", "pages", "volume"]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("requests", "isal", "pyarrow", "numpy")
)
app = modal.App("rrm-s2-download")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
secret = modal.Secret.from_name("s2-api-key")
_next = 0.0
_schemas = None


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


def _api(path):
    """Datasets API. At most one request per second, with backoff on 429 and 5xx."""
    import requests

    global _next
    delay = 1.0
    for _ in range(6):
        wait = _next - time.time()
        if wait > 0:
            time.sleep(wait)
        resp = requests.get(BASE + path, headers={"x-api-key": os.environ["S2_API_KEY"]}, timeout=120)
        _next = time.time() + 1
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("s2 api failed")


def _release(release):
    if release == "latest":
        release = str(_api("release/latest")["release_id"])
    return _safe(release)


def _urls(release, dataset):
    files = _api(f"release/{release}/dataset/{dataset}").get("files") or []
    return [item["url"] if isinstance(item, dict) else str(item) for item in files]


def _build_schemas():
    """Parse schemas accept both casings. Output schemas are one canonical shape.

    Numeric ids (CorpusId, authorId, journal volume) are quoted to strings
    before parse, so a block that mixes int and string still has one type.
    Keys that are not in the parse schema are inferred and then stored as JSON
    text instead of being dropped.
    """
    import pyarrow as pa

    i, s = pa.int64(), pa.string()
    fos = pa.list_(pa.struct([("category", s), ("source", s)]))
    ext_parse = pa.struct([(name, s) for name in _EXT_NAMES] + [(name.lower(), s) for name in _EXT_NAMES])
    ext_out = pa.struct([(name, s) for name in _EXT_NAMES])
    author_parse = pa.struct([("authorId", s), ("authorid", s), ("name", s)])
    author_out = pa.struct([("authorId", s), ("name", s)])
    journal = pa.struct([(name, s) for name in _JOURNAL_NAMES])
    papers_common = [
        ("url", s),
        ("title", s),
        ("venue", s),
        ("publicationvenueid", s),
        ("year", i),
        ("referencecount", i),
        ("citationcount", i),
        ("influentialcitationcount", i),
        ("isopenaccess", pa.bool_()),
        ("publicationtypes", pa.list_(s)),
        ("publicationdate", s),
        ("journal", journal),
    ]
    return {
        "parse": {
            "papers": pa.schema(
                [
                    ("corpusid", i),
                    ("corpusId", i),
                    ("externalids", ext_parse),
                    ("externalIds", ext_parse),
                    ("authors", pa.list_(author_parse)),
                    ("s2fieldsofstudy", fos),
                    ("s2FieldsOfStudy", fos),
                    ("fieldsofstudy", pa.list_(s)),
                    ("fieldsOfStudy", pa.list_(s)),
                ]
                + papers_common
            ),
            "abstracts": pa.schema([("corpusid", i), ("corpusId", i), ("abstract", s)]),
            "tldrs": pa.schema([("corpusid", i), ("corpusId", i), ("model", s), ("text", s)]),
            "citations": pa.schema([
                ("citationid", i),
                ("citingcorpusid", i),
                ("citedcorpusid", i),
                ("isinfluential", pa.bool_()),
                ("contexts", pa.list_(s)),
                ("intents", pa.list_(s)),
            ]),
        },
        "out": {
            "papers": pa.schema(
                [
                    ("corpusid", i),
                    ("externalids", ext_out),
                    ("authors", pa.list_(author_out)),
                    ("s2fieldsofstudy", fos),
                    ("fieldsofstudy", pa.list_(s)),
                ]
                + papers_common
                + [("extra", pa.large_string())]
            ),
            "abstracts": pa.schema([
                ("corpusid", i),
                ("abstract", s),
                ("openaccessinfo", pa.large_string()),
                ("extra", pa.large_string()),
            ]),
            "tldrs": pa.schema([
                ("corpusid", i),
                ("model", s),
                ("text", s),
                ("extra", pa.large_string()),
            ]),
        },
    }


def _schemas_for(dataset, kind):
    global _schemas
    if _schemas is None:
        _schemas = _build_schemas()
    bucket = _schemas[kind]
    return bucket.get(dataset)


def _blocks(resp, max_mb, seen):
    """Yield decompressed newline-aligned blocks. seen[0] counts compressed bytes.

    max_mb > 0 stops the HTTP read at that many MiB and keeps only complete lines.
    isal's incremental gzip decoder returns the bytes already inflated when the
    member is cut short.
    """
    import isal.isal_zlib as iz

    dec = iz.decompressobj(16 + iz.MAX_WBITS)
    buf = bytearray()
    limit = max_mb * MB if max_mb else 0
    while not (limit and seen[0] >= limit):
        want = min(1 << 20, limit - seen[0]) if limit else 1 << 20
        data = resp.raw.read(want)
        if not data:
            break
        seen[0] += len(data)
        buf += dec.decompress(data)
        while len(buf) >= BLOCK:
            cut = buf.rfind(b"\n", 0, BLOCK)
            if cut < 0:
                cut = buf.find(b"\n")
            if cut < 0:
                break
            piece = bytes(buf[: cut + 1])
            del buf[: cut + 1]
            if not piece.isspace():
                yield piece
    if not max_mb:
        buf += dec.flush()
        if buf and not buf.endswith(b"\n"):
            buf += b"\n"
    cut = buf.rfind(b"\n")
    if cut >= 0 and not buf[: cut + 1].isspace():
        yield bytes(buf[: cut + 1])


def _string_list(value):
    """List of strings. Nested values are JSON text so the Arrow type stays list<string>."""
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        else:
            out.append(json.dumps(item, separators=(",", ":")))
    return out


def _lookup(mapping, name):
    if not isinstance(mapping, dict):
        return None
    if name in mapping:
        return mapping[name]
    return mapping.get(name.lower())


def _as_text(value):
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _paper_row(row):
    """Slow path used only when a papers block still fails after quoting ids."""
    ext_in = row.get("externalids")
    if not isinstance(ext_in, dict):
        ext_in = row.get("externalIds")
    fos = row.get("s2fieldsofstudy")
    if fos is None:
        fos = row.get("s2FieldsOfStudy")
    if isinstance(fos, list):
        fos = [
            {
                "category": item.get("category") if isinstance(item, dict) else _as_text(item),
                "source": item.get("source") if isinstance(item, dict) else None,
            }
            for item in fos
        ]
    fields = row.get("fieldsofstudy")
    if fields is None:
        fields = row.get("fieldsOfStudy")
    raw_authors = row.get("authors")
    if isinstance(raw_authors, list):
        authors = []
        for item in raw_authors:
            if not isinstance(item, dict):
                authors.append(None)
                continue
            authors.append({
                "authorId": _as_text(item.get("authorId", item.get("authorid"))),
                "name": item.get("name"),
            })
    else:
        authors = None
    journal = row.get("journal")
    if isinstance(journal, dict):
        journal = {name: _as_text(_lookup(journal, name)) for name in _JOURNAL_NAMES}
    else:
        journal = None
    known = {
        "corpusid", "corpusId", "externalids", "externalIds", "url", "title", "authors",
        "venue", "publicationvenueid", "year", "referencecount", "citationcount",
        "influentialcitationcount", "isopenaccess", "s2fieldsofstudy", "s2FieldsOfStudy",
        "fieldsofstudy", "fieldsOfStudy", "publicationtypes", "publicationdate", "journal",
    }
    extra = {key: value for key, value in row.items() if key not in known}
    return {
        "corpusid": row.get("corpusid", row.get("corpusId")),
        "externalids": (
            {name: _as_text(_lookup(ext_in, name)) for name in _EXT_NAMES}
            if isinstance(ext_in, dict) else None
        ),
        "url": row.get("url"),
        "title": row.get("title"),
        "authors": authors,
        "venue": row.get("venue"),
        "publicationvenueid": row.get("publicationvenueid"),
        "year": row.get("year"),
        "referencecount": row.get("referencecount"),
        "citationcount": row.get("citationcount"),
        "influentialcitationcount": row.get("influentialcitationcount"),
        "isopenaccess": row.get("isopenaccess"),
        "s2fieldsofstudy": fos,
        "fieldsofstudy": _string_list(fields),
        "publicationtypes": _string_list(row.get("publicationtypes")),
        "publicationdate": _as_text(row.get("publicationdate")),
        "journal": journal,
        "extra": json.dumps(extra, default=str, separators=(",", ":")) if extra else None,
    }


def _citation_row(row):
    return {
        "citationid": row.get("citationid"),
        "citingcorpusid": row.get("citingcorpusid"),
        "citedcorpusid": row.get("citedcorpusid"),
        "isinfluential": row.get("isinfluential"),
        "contexts": _string_list(row.get("contexts")),
        "intents": _string_list(row.get("intents")),
    }


def _read_json(blob, schema, unexpected):
    import pyarrow.json as pj

    return pj.read_json(
        io.BytesIO(blob),
        read_options=pj.ReadOptions(use_threads=True),
        parse_options=pj.ParseOptions(explicit_schema=schema, unexpected_field_behavior=unexpected),
    )


def _quote_ids(blob):
    """Turn unquoted numeric ids into JSON strings so int and str share one column."""
    return _QUOTE_IDS.sub(lambda match: b'"' + match.group(1) + b'": "' + match.group(2) + b'"', blob)


def _combine(col):
    if col is None:
        return None
    return col.combine_chunks() if hasattr(col, "combine_chunks") else col


def _coalesce_named(table, names):
    import pyarrow.compute as pc

    cols = [_combine(table.column(name)) for name in names if name in table.column_names]
    if not cols:
        return None
    col = cols[0]
    for extra in cols[1:]:
        col = pc.coalesce(col, extra)
    return col


def _text_array(col, n):
    import pyarrow as pa
    import pyarrow.compute as pc

    if col is None or pa.types.is_null(col.type):
        return pa.nulls(n, pa.string())
    if not (pa.types.is_string(col.type) or pa.types.is_large_string(col.type)):
        col = pc.cast(col, pa.string(), safe=False)
    return col.cast(pa.string())


def _struct_children(struct_col, names):
    """String fields, coalescing Name and name. struct_col is one struct array."""
    import pyarrow as pa
    import pyarrow.compute as pc

    width = len(struct_col)
    if struct_col is None or not pa.types.is_struct(struct_col.type):
        return [pa.nulls(width, pa.string()) for _ in names]
    present = set(struct_col.type.names)
    children = []
    for name in names:
        parts = []
        for candidate in (name, name.lower()):
            if candidate in present:
                parts.append(_text_array(struct_col.field(candidate), width))
        if not parts:
            children.append(pa.nulls(width, pa.string()))
            continue
        col = parts[0]
        for extra in parts[1:]:
            col = pc.coalesce(col, extra)
        # A null struct's .field() is "" rather than null. Put the null back.
        col = pc.if_else(struct_col.is_null(), pa.scalar(None, type=pa.string()), col)
        children.append(col)
    return children


def _struct_array(struct_col, names, n):
    import pyarrow as pa

    if struct_col is None:
        children = [pa.nulls(n, pa.string()) for _ in names]
        return pa.StructArray.from_arrays(children, names)
    return pa.StructArray.from_arrays(
        _struct_children(struct_col, names),
        names,
        mask=struct_col.is_null(),
    )


def _authors_array(col, n):
    import pyarrow as pa
    import pyarrow.compute as pc

    typ = pa.list_(pa.struct([("authorId", pa.string()), ("name", pa.string())]))
    if col is None or not pa.types.is_list(col.type):
        return pa.nulls(n, typ)
    flat = pc.list_flatten(col)
    if len(flat) == 0:
        structs = pa.StructArray.from_arrays(
            [pa.array([], type=pa.string()), pa.array([], type=pa.string())],
            ["authorId", "name"],
        )
    elif not pa.types.is_struct(flat.type):
        return pa.nulls(n, typ)
    else:
        structs = pa.StructArray.from_arrays(
            _struct_children(flat, ["authorId", "name"]),
            ["authorId", "name"],
            mask=flat.is_null(),
        )
    return pa.ListArray.from_arrays(col.offsets, structs, mask=col.is_null())


def _json_text(col, n):
    import pyarrow as pa

    if col is None or pa.types.is_null(_combine(col).type):
        return pa.nulls(n, pa.large_string())
    col = _combine(col)
    if pa.types.is_string(col.type) or pa.types.is_large_string(col.type):
        return col.cast(pa.large_string())
    values = []
    for item in col.to_pylist():
        if item is None:
            values.append(None)
        elif isinstance(item, str):
            values.append(item)
        else:
            values.append(json.dumps(item, default=str, separators=(",", ":")))
    return pa.array(values, type=pa.large_string())


def _pack_extra(table, used, n):
    import pyarrow as pa

    names = [name for name in table.column_names if name not in used]
    if not names:
        return pa.nulls(n, pa.large_string())
    columns = [table.column(name).to_pylist() for name in names]
    packed = []
    for index in range(n):
        obj = {}
        for name, values in zip(names, columns):
            if values[index] is not None:
                obj[name] = values[index]
        packed.append(json.dumps(obj, default=str, separators=(",", ":")) if obj else None)
    return pa.array(packed, type=pa.large_string())


def _rows_table(blob, project, schema):
    import pyarrow as pa

    rows = []
    for line in blob.splitlines():
        if line.strip():
            rows.append(project(json.loads(line)))
    return pa.Table.from_pylist(rows, schema=schema)


def _papers_table(blob):
    import pyarrow as pa
    import pyarrow.compute as pc

    out = _schemas_for("papers", "out")
    parse = _schemas_for("papers", "parse")
    try:
        table = _read_json(_quote_ids(blob), parse, "infer")
    except pa.ArrowInvalid:
        return _rows_table(blob, _paper_row, out)
    n = table.num_rows
    ext = _coalesce_named(table, ("externalids", "externalIds"))
    fos = _coalesce_named(table, ("s2fieldsofstudy", "s2FieldsOfStudy"))
    fields = _coalesce_named(table, ("fieldsofstudy", "fieldsOfStudy"))
    authors = _combine(table.column("authors")) if "authors" in table.column_names else None
    journal = _combine(table.column("journal")) if "journal" in table.column_names else None
    used = set(parse.names)
    columns = {
        "corpusid": _corpus_ids(table),
        "externalids": _struct_array(ext, _EXT_NAMES, n),
        "url": _text_array(_combine(table.column("url")) if "url" in table.column_names else None, n),
        "title": _text_array(_combine(table.column("title")) if "title" in table.column_names else None, n),
        "authors": _authors_array(authors, n),
        "venue": _text_array(_combine(table.column("venue")) if "venue" in table.column_names else None, n),
        "publicationvenueid": _text_array(_combine(table.column("publicationvenueid")) if "publicationvenueid" in table.column_names else None, n),
        "year": _coalesce_named(table, ("year",)) if "year" in table.column_names else pa.nulls(n, pa.int64()),
        "referencecount": table.column("referencecount") if "referencecount" in table.column_names else pa.nulls(n, pa.int64()),
        "citationcount": table.column("citationcount") if "citationcount" in table.column_names else pa.nulls(n, pa.int64()),
        "influentialcitationcount": table.column("influentialcitationcount") if "influentialcitationcount" in table.column_names else pa.nulls(n, pa.int64()),
        "isopenaccess": table.column("isopenaccess") if "isopenaccess" in table.column_names else pa.nulls(n, pa.bool_()),
        "s2fieldsofstudy": fos if fos is not None else pa.nulls(n, out.field("s2fieldsofstudy").type),
        "fieldsofstudy": fields if fields is not None else pa.nulls(n, pa.list_(pa.string())),
        "publicationtypes": table.column("publicationtypes") if "publicationtypes" in table.column_names else pa.nulls(n, pa.list_(pa.string())),
        "publicationdate": _text_array(_combine(table.column("publicationdate")) if "publicationdate" in table.column_names else None, n),
        "journal": _struct_array(journal, _JOURNAL_NAMES, n),
        "extra": _pack_extra(table, used, n),
    }
    # year/counts may be chunked; cast only scalars, never lists.
    for name, typ in (("year", pa.int64()), ("referencecount", pa.int64()), ("citationcount", pa.int64()), ("influentialcitationcount", pa.int64())):
        if columns[name].type != typ:
            columns[name] = pc.cast(columns[name], typ, safe=False)
    return pa.table(columns, schema=out)


def _simple_table(blob, dataset, text_fields, json_fields):
    """abstracts and tldrs: keep named fields, JSON-stringify the rest."""
    import pyarrow as pa
    import pyarrow.compute as pc

    out = _schemas_for(dataset, "out")
    parse = _schemas_for(dataset, "parse")
    try:
        table = _read_json(blob, parse, "infer")
    except pa.ArrowInvalid:
        return _rows_table(blob, _loose_row(dataset), out)
    n = table.num_rows
    used = set(parse.names)
    columns = {"corpusid": _corpus_ids(table)}
    for name in text_fields:
        columns[name] = _text_array(_combine(table.column(name)) if name in table.column_names else None, n)
    for name, aliases in json_fields:
        used.update(aliases)
        parts = [_json_text(table.column(alias), n) for alias in aliases if alias in table.column_names]
        if not parts:
            columns[name] = pa.nulls(n, pa.large_string())
        else:
            col = parts[0]
            for extra in parts[1:]:
                col = pc.coalesce(col, extra)
            columns[name] = col
    columns["extra"] = _pack_extra(table, used, n)
    return pa.table(columns, schema=out)


def _loose_row(dataset):
    def project(row):
        if dataset == "abstracts":
            info = row.get("openaccessinfo", row.get("openAccessInfo"))
            extra = {key: value for key, value in row.items() if key not in {"corpusid", "corpusId", "abstract", "openaccessinfo", "openAccessInfo"}}
            return {
                "corpusid": row.get("corpusid", row.get("corpusId")),
                "abstract": row.get("abstract"),
                "openaccessinfo": None if info is None else info if isinstance(info, str) else json.dumps(info, default=str),
                "extra": json.dumps(extra, default=str) if extra else None,
            }
        extra = {key: value for key, value in row.items() if key not in {"corpusid", "corpusId", "model", "text"}}
        return {
            "corpusid": row.get("corpusid", row.get("corpusId")),
            "model": row.get("model"),
            "text": row.get("text"),
            "extra": json.dumps(extra, default=str) if extra else None,
        }
    return project


def _json_table(blob, dataset):
    """Parse one block into the dataset's stable output schema."""
    import pyarrow as pa

    if dataset == "papers":
        return _papers_table(blob)
    if dataset == "abstracts":
        return _simple_table(blob, dataset, ["abstract"], [("openaccessinfo", ("openaccessinfo", "openAccessInfo"))])
    if dataset == "tldrs":
        return _simple_table(blob, dataset, ["model", "text"], [])
    schema = _schemas_for("citations", "parse")
    try:
        return _read_json(blob, schema, "ignore")
    except pa.ArrowInvalid:
        return _rows_table(blob, _citation_row, schema)


def _align(table, schema):
    """Add columns that this block lacks.

    List and struct columns are not cast. Casting them between blocks produces
    Arrow arrays whose list offsets run past the values buffer.
    """
    import pyarrow as pa

    if table.schema.equals(schema, check_metadata=False):
        return table
    cols = []
    for field in schema:
        if field.name not in table.column_names:
            cols.append(pa.nulls(table.num_rows, type=field.type))
            continue
        col = table.column(field.name)
        if col.type == field.type:
            cols.append(col)
            continue
        nested = (
            pa.types.is_list(col.type)
            or pa.types.is_struct(col.type)
            or pa.types.is_list(field.type)
            or pa.types.is_struct(field.type)
        )
        if nested:
            raise pa.ArrowInvalid(f"nested schema mismatch on {field.name}")
        cols.append(col.cast(field.type, safe=False))
    names = [field.name for field in schema]
    return pa.table(dict(zip(names, cols)), schema=schema)


def _emb_table(blob, cs, missed):
    """Keep embedding rows. cs is a set of corpus ids, or None to keep every row.

    Lines are filtered with a byte regex before any JSON parse. The vector text
    inside the brackets is read with numpy. missed counts lines that had a
    corpus id but no vector text.
    """
    import numpy as np
    import pyarrow as pa

    ids = []
    vecs = []
    for line in blob.splitlines():
        found = _CID.search(line)
        if not found:
            continue
        cid = int(found.group(1))
        brackets = _VEC.search(line)
        if not brackets or not brackets.group(1).strip():
            missed[0] += 1
            continue
        if cs is not None and cid not in cs:
            continue
        vecs.append(np.fromstring(brackets.group(1).decode(), sep=",", dtype=np.float16))
        ids.append(cid)
    if not ids:
        return None
    flat = pa.array(np.concatenate(vecs), type=pa.float16())
    vectors = pa.FixedSizeListArray.from_arrays(flat, len(vecs[0]))
    return pa.table({
        "corpusid": pa.array(ids, type=pa.int64()),
        "vector": vectors,
    })


def _load_cs(path):
    import pyarrow.parquet as pq

    column = pq.read_table(path, columns=["corpusid"]).column("corpusid")
    return {int(value) for value in column.to_pylist() if value is not None}


def _corpus_ids(table):
    import pyarrow as pa
    import pyarrow.compute as pc

    cols = []
    for name in ("corpusid", "corpusId"):
        if name in table.column_names:
            cols.append(table.column(name).cast(pa.int64()))
    if not cols:
        raise RuntimeError("papers parquet has no corpusid")
    ids = cols[0]
    for extra in cols[1:]:
        ids = pc.coalesce(ids, extra)
    return ids


def _cs_ids(table):
    keys = ("s2fieldsofstudy", "s2FieldsOfStudy", "fieldsofstudy", "fieldsOfStudy")
    present = [name for name in keys if name in table.column_names]
    ids = _corpus_ids(table).to_pylist()
    cols = [table.column(name).to_pylist() for name in present]
    keep = []
    for index, cid in enumerate(ids):
        if cid is None:
            continue
        for col in cols:
            value = col[index]
            if value is None:
                continue
            text = value if isinstance(value, str) else json.dumps(value, default=str)
            if "Computer Science" in text:
                keep.append(int(cid))
                break
    return keep


def _write(dest, tables):
    import pyarrow as pa
    import pyarrow.parquet as pq

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".partial")
    writer = None
    rows = 0
    try:
        for table in tables:
            if table is None or table.num_rows == 0:
                continue
            if writer is None:
                writer = pq.ParquetWriter(str(tmp), table.schema, compression="zstd")
            elif not table.schema.equals(writer.schema, check_metadata=False):
                table = _align(table, writer.schema)
            writer.write_table(table)
            rows += table.num_rows
        if writer is None:
            empty = pa.table({"corpusid": pa.array([], type=pa.int64())})
            pq.write_table(empty, str(tmp), compression="zstd")
        else:
            writer.close()
            writer = None
        os.replace(tmp, dest)
    except Exception:
        if writer is not None:
            writer.close()
        tmp.unlink(missing_ok=True)
        raise
    return rows


def _done(dataset, idx, in_bytes, out_bytes, rows, started):
    return {
        "dataset": dataset,
        "idx": idx,
        "in_mb": round(in_bytes / MB, 3),
        "out_mb": round(out_bytes / MB, 3),
        "rows": rows,
        "seconds": round(time.perf_counter() - started, 1),
    }


def _open(url, dataset, idx, release):
    """GET a presigned shard. Refresh the file list once on an expired signature."""
    import requests

    resp = requests.get(url, stream=True, timeout=(30, 600))
    if resp.status_code in (400, 401, 403):
        resp.close()
        fresh = _urls(release, dataset)
        if idx < 0 or idx >= len(fresh):
            raise RuntimeError(f"{dataset} shard {idx} out of range")
        resp = requests.get(fresh[idx], stream=True, timeout=(30, 600))
    resp.raise_for_status()
    resp.raw.decode_content = False
    return resp


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    retries=2,
    timeout=3600,
    volumes={MOUNT: vol},
    secrets=[secret],
)
def process_shard(dataset: str, idx: int, release: str, url: str, max_mb: int = 0):
    import pyarrow.parquet as pq

    started = time.perf_counter()
    dataset, release = _safe(dataset), _release(release)
    vol.reload()
    if max_mb:
        dest = Path(MOUNT) / "_test" / f"{dataset}-{idx}.parquet"
    else:
        dest = Path(MOUNT) / release / dataset / f"part-{idx:04d}.parquet"
        if dest.exists() and dest.stat().st_size:
            rows = pq.read_metadata(dest).num_rows
            return _done(dataset, idx, 0, dest.stat().st_size, rows, started)
    resp = _open(url, dataset, idx, release)
    seen = [0]
    try:
        cs = None
        missed = [0]
        if dataset == "embeddings-specter_v2":
            cs_path = Path(MOUNT) / release / "cs_corpusids.parquet"
            if cs_path.exists():
                cs = _load_cs(cs_path)

        def tables():
            for blob in _blocks(resp, max_mb, seen):
                if dataset == "embeddings-specter_v2":
                    yield _emb_table(blob, cs, missed)
                else:
                    yield _json_table(blob, dataset)

        rows = _write(dest, tables())
    finally:
        resp.close()
    vol.commit()
    result = _done(dataset, idx, seen[0], dest.stat().st_size, rows, started)
    if dataset == "embeddings-specter_v2":
        result["vec_miss"] = missed[0]
    return result


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    timeout=3600,
    volumes={MOUNT: vol},
    secrets=[secret],
)
def build_cs_ids(release: str):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    started = time.perf_counter()
    vol.reload()
    release = _release(release)
    ids = []
    papers = Path(MOUNT) / release / "papers"
    for path in sorted(papers.glob("part-*.parquet")):
        ids.extend(_cs_ids(pq.read_table(path)))
    if ids:
        arr = pc.unique(pa.array(ids, type=pa.int64()))
    else:
        arr = pa.array([], type=pa.int64())
    dest = Path(MOUNT) / release / "cs_corpusids.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"corpusid": arr}), dest, compression="zstd")
    vol.commit()
    return {"rows": len(arr), "seconds": round(time.perf_counter() - started, 1)}


@app.function(image=image, secrets=[secret], timeout=900)
def list_files(release: str, datasets: str):
    """Resolve the release and fetch each dataset file list, spaced by _api."""
    release = _release(release)
    files = {}
    for part in datasets.split(","):
        name = part.strip()
        if name:
            files[_safe(name)] = _urls(release, name)
    return {"release": release, "files": files}


@app.local_entrypoint()
def main(
    datasets: str = "papers",
    limit: int = 0,
    max_mb: int = 0,
    concurrency: int = 100,
    release: str = "latest",
    cpu: float = 2,
    memory: int = 4096,
):
    plan = list_files.remote(release, datasets)
    jobs = []
    for name, urls in plan["files"].items():
        count = len(urls) if int(limit) <= 0 else min(int(limit), len(urls))
        for idx in range(count):
            jobs.append((name, idx, plan["release"], urls[idx], int(max_mb)))
    total_in = 0.0
    total_out = 0.0
    total_rows = 0
    total_seconds = 0.0
    worker = process_shard.with_options(
        max_containers=int(concurrency),
        cpu=float(cpu),
        memory=int(memory),
    )
    for row in worker.starmap(jobs, order_outputs=False, return_exceptions=True):
        if isinstance(row, BaseException):
            text = str(row).split("?", 1)[0][:160]
            print(f"ERROR {type(row).__name__} {text}")
            continue
        line = (
            f"{row['dataset']} {row['idx']} in_mb={row['in_mb']} "
            f"out_mb={row['out_mb']} rows={row['rows']} s={row['seconds']}"
        )
        if "vec_miss" in row:
            line += f" vec_miss={row['vec_miss']}"
            if row["vec_miss"]:
                print(f"WARNING {row['dataset']} {row['idx']} cid_without_vector={row['vec_miss']}")
        print(line)
        total_in += row["in_mb"]
        total_out += row["out_mb"]
        total_rows += row["rows"]
        total_seconds += row["seconds"]
    print(
        f"total in_mb={total_in:.3f} out_mb={total_out:.3f} "
        f"rows={total_rows} container_s={total_seconds:.1f}"
    )
