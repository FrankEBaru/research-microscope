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
_VEC = re.compile(rb'"vector"\s*:\s*\[([^\]]*)\]')

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


def _schema(dataset):
    """One schema per dataset. Unknown JSON keys are ignored at parse time."""
    global _schemas
    if _schemas is None:
        import pyarrow as pa

        i, s = pa.int64(), pa.string()
        fos = pa.list_(pa.struct([("category", s), ("source", s)]))
        # CorpusId is omitted: it is sometimes a number and sometimes a string.
        ext = pa.struct([("ArXiv", s), ("arxiv", s), ("DOI", s), ("doi", s)])
        _schemas = {
            "papers": pa.schema([
                ("corpusid", i),
                ("corpusId", i),
                ("title", s),
                ("year", i),
                ("venue", s),
                ("citationcount", i),
                ("referencecount", i),
                ("influentialcitationcount", i),
                ("s2fieldsofstudy", fos),
                ("s2FieldsOfStudy", fos),
                ("fieldsofstudy", pa.list_(s)),
                ("fieldsOfStudy", pa.list_(s)),
                ("externalids", ext),
                ("externalIds", ext),
            ]),
            "abstracts": pa.schema([("corpusid", i), ("abstract", s)]),
            "tldrs": pa.schema([("corpusid", i), ("model", s), ("text", s)]),
            # intents is list<string>. A list-of-lists block is rewritten so the
            # column stays list<string> instead of changing type mid-shard.
            "citations": pa.schema([
                ("citationid", i),
                ("citingcorpusid", i),
                ("citedcorpusid", i),
                ("isinfluential", pa.bool_()),
                ("contexts", pa.list_(s)),
                ("intents", pa.list_(s)),
            ]),
        }
    return _schemas.get(dataset)


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


def _paper_row(row):
    ext = row.get("externalids")
    if not isinstance(ext, dict):
        ext = row.get("externalIds") if isinstance(row.get("externalIds"), dict) else {}
    fos = row.get("s2fieldsofstudy")
    if fos is None:
        fos = row.get("s2FieldsOfStudy")
    if isinstance(fos, list):
        fos = [
            {
                "category": item.get("category") if isinstance(item, dict) else item,
                "source": item.get("source") if isinstance(item, dict) else None,
            }
            for item in fos
        ]
    fields = row.get("fieldsofstudy")
    if fields is None:
        fields = row.get("fieldsOfStudy")
    return {
        "corpusid": row.get("corpusid", row.get("corpusId")),
        "title": row.get("title"),
        "year": row.get("year"),
        "venue": row.get("venue"),
        "citationcount": row.get("citationcount"),
        "referencecount": row.get("referencecount"),
        "influentialcitationcount": row.get("influentialcitationcount"),
        "s2fieldsofstudy": fos,
        "fieldsofstudy": _string_list(fields),
        "externalids": {
            "ArXiv": ext.get("ArXiv") or ext.get("arxiv"),
            "arxiv": ext.get("arxiv") or ext.get("ArXiv"),
            "DOI": ext.get("DOI") or ext.get("doi"),
            "doi": ext.get("doi") or ext.get("DOI"),
        },
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


def _json_table(blob, dataset):
    """Parse one block. Fallback rows use the same schema as the fast path."""
    import pyarrow as pa
    import pyarrow.json as pj

    schema = _schema(dataset)
    options = pj.ReadOptions(use_threads=True)
    if schema is None:
        return pj.read_json(io.BytesIO(blob), read_options=options)
    parse = pj.ParseOptions(explicit_schema=schema, unexpected_field_behavior="ignore")
    try:
        return pj.read_json(io.BytesIO(blob), read_options=options, parse_options=parse)
    except pa.ArrowInvalid:
        project = _citation_row if dataset == "citations" else _paper_row
        rows = []
        for line in blob.splitlines():
            if not line.strip():
                continue
            rows.append(project(json.loads(line)))
        return pa.Table.from_pylist(rows, schema=schema)


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


def _emb_table(blob, cs):
    """Keep embedding rows. cs is a set of corpus ids, or None to keep every row.

    Lines are filtered with a byte regex before any JSON parse. The vector text
    inside the brackets is read with numpy, not converted through Python lists.
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
        if cs is not None and cid not in cs:
            continue
        brackets = _VEC.search(line)
        if not brackets or not brackets.group(1).strip():
            continue
        vecs.append(np.fromstring(brackets.group(1), sep=",", dtype=np.float16))
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
        if dataset == "embeddings-specter_v2":
            cs_path = Path(MOUNT) / release / "cs_corpusids.parquet"
            if cs_path.exists():
                cs = _load_cs(cs_path)

        def tables():
            for blob in _blocks(resp, max_mb, seen):
                if dataset == "embeddings-specter_v2":
                    yield _emb_table(blob, cs)
                else:
                    yield _json_table(blob, dataset)

        rows = _write(dest, tables())
    finally:
        resp.close()
    vol.commit()
    return _done(dataset, idx, seen[0], dest.stat().st_size, rows, started)


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
        print(
            f"{row['dataset']} {row['idx']} in_mb={row['in_mb']} "
            f"out_mb={row['out_mb']} rows={row['rows']} s={row['seconds']}"
        )
        total_in += row["in_mb"]
        total_out += row["out_mb"]
        total_rows += row["rows"]
        total_seconds += row["seconds"]
    print(
        f"total in_mb={total_in:.3f} out_mb={total_out:.3f} "
        f"rows={total_rows} container_s={total_seconds:.1f}"
    )
