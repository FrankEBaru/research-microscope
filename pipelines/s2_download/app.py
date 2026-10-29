"""Stream Semantic Scholar shards to zstd Parquet on volume rrm-data."""

import io, json, os, time
from pathlib import Path

import modal

BASE = "https://api.semanticscholar.org/datasets/v1/"
MOUNT, BLOCK, MB = "/s2", 64 << 20, 1 << 20
image = modal.Image.debian_slim(python_version="3.12").pip_install("requests", "isal", "pyarrow", "numpy")
app = modal.App("rrm-s2-download")
vol = modal.Volume.from_name("rrm-data", create_if_missing=True)
secret = modal.Secret.from_name("s2-api-key")
_next = 0.0


def _safe(name):
    if not name or len(name) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
        raise ValueError("bad name")
    return name


def _api(path):
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


def _blocks(resp, max_mb, seen):
    import isal.isal_zlib as iz
    dec, buf = iz.decompressobj(16 + iz.MAX_WBITS), bytearray()
    limit = max_mb * MB if max_mb else 0
    while not (limit and seen[0] >= limit):
        data = resp.raw.read(min(1 << 20, limit - seen[0]) if limit else 1 << 20)
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


def _json_table(blob):
    import pyarrow as pa
    import pyarrow.json as pj
    opts = pj.ReadOptions(use_threads=True)
    try:
        return pj.read_json(io.BytesIO(blob), read_options=opts)
    except pa.ArrowInvalid:
        fixed = []
        for line in blob.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for key, val in row.items():
                if isinstance(val, (dict, list)):
                    row[key] = json.dumps(val, separators=(",", ":"))
            fixed.append(json.dumps(row).encode())
        return pj.read_json(io.BytesIO(b"\n".join(fixed) + b"\n"), read_options=opts)


def _align(table, schema):
    import pyarrow as pa
    cols = []
    for field in schema:
        if field.name not in table.column_names:
            cols.append(pa.nulls(table.num_rows, type=field.type))
            continue
        col = table.column(field.name)
        if col.type != field.type:
            try:
                col = col.cast(field.type, safe=False)
            except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
                if not (pa.types.is_string(field.type) or pa.types.is_large_string(field.type)):
                    raise
                col = pa.array([
                    None if v is None else v if isinstance(v, str) else json.dumps(v, default=str)
                    for v in col.to_pylist()
                ], type=field.type)
        cols.append(col)
    return pa.table({field.name: col for field, col in zip(schema, cols)}, schema=schema)


def _emb(table, cs):
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc
    name = "corpusid" if "corpusid" in table.column_names else "corpusId"
    cid, vec = table.column(name).cast(pa.int64()), table.column("vector")
    if cs is not None:
        keep = pc.is_in(cid, value_set=cs.cast(pa.int64()))
        cid, vec = cid.filter(keep), vec.filter(keep)
    if len(cid) == 0:
        return None
    rows = [json.loads(v) if isinstance(v, str) else v for v in vec.to_pylist()]
    flat = pa.array(np.concatenate([np.asarray(v, dtype=np.float16) for v in rows]), type=pa.float16())
    return pa.table({"corpusid": cid, "vector": pa.FixedSizeListArray.from_arrays(flat, len(rows[0]))})


def _cs_ids(table):
    keys = [n for n in ("s2fieldsofstudy", "s2FieldsOfStudy", "fieldsofstudy", "fieldsOfStudy") if n in table.column_names]
    cid_name = "corpusid" if "corpusid" in table.column_names else "corpusId"
    ids = table.column(cid_name).to_pylist()
    cols = [table.column(k).to_pylist() for k in keys]
    keep = []
    for i, cid in enumerate(ids):
        if cid is None:
            continue
        if any("Computer Science" in (v if isinstance(v, str) else json.dumps(v, default=str)) for v in (c[i] for c in cols) if v is not None):
            keep.append(int(cid))
    return keep


def _write(dest, tables):
    import pyarrow as pa
    import pyarrow.parquet as pq
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp, writer, rows = dest.with_suffix(".partial"), None, 0
    try:
        for table in tables:
            if table is None or table.num_rows == 0:
                continue
            if writer is None:
                writer = pq.ParquetWriter(str(tmp), table.schema, compression="zstd")
            else:
                table = _align(table, writer.schema)
            writer.write_table(table)
            rows += table.num_rows
        if writer is None:
            pq.write_table(pa.table({"corpusid": pa.array([], type=pa.int64())}), str(tmp), compression="zstd")
        else:
            writer.close()
            writer = None
        os.replace(tmp, dest)
    except Exception:
        if writer:
            writer.close()
        tmp.unlink(missing_ok=True)
        raise
    return rows


def _done(dataset, idx, in_b, out_b, rows, t0):
    return {"dataset": dataset, "idx": idx, "in_mb": round(in_b / MB, 3), "out_mb": round(out_b / MB, 3),
            "rows": rows, "seconds": round(time.perf_counter() - t0, 1)}


@app.function(image=image, cpu=2, memory=4096, retries=2, timeout=3600, volumes={MOUNT: vol}, secrets=[secret])
def process_shard(dataset: str, idx: int, release: str, max_mb: int = 0):
    import pyarrow.parquet as pq
    import requests
    t0 = time.perf_counter()
    dataset, release = _safe(dataset), _release(release)
    vol.reload()
    if max_mb:
        dest = Path(MOUNT) / "_test" / f"{dataset}-{idx}.parquet"
    else:
        dest = Path(MOUNT) / release / dataset / f"part-{idx:04d}.parquet"
        if dest.exists() and dest.stat().st_size:
            return _done(dataset, idx, 0, dest.stat().st_size, pq.read_metadata(dest).num_rows, t0)
    urls = _urls(release, dataset)
    if idx < 0 or idx >= len(urls):
        raise RuntimeError(f"{dataset} shard {idx} out of range")
    resp = requests.get(urls[idx], stream=True, timeout=(30, 600))
    resp.raise_for_status()
    resp.raw.decode_content = False
    seen = [0]
    try:
        cs = None
        if dataset == "embeddings-specter_v2":
            cs_path = Path(MOUNT) / release / "cs_corpusids.parquet"
            if cs_path.exists():
                cs = pq.read_table(cs_path, columns=["corpusid"]).column("corpusid")
        def tables():
            for blob in _blocks(resp, max_mb, seen):
                table = _json_table(blob)
                yield _emb(table, cs) if dataset == "embeddings-specter_v2" else table
        rows = _write(dest, tables())
    finally:
        resp.close()
    vol.commit()
    return _done(dataset, idx, seen[0], dest.stat().st_size, rows, t0)


@app.function(image=image, cpu=2, memory=4096, timeout=3600, volumes={MOUNT: vol}, secrets=[secret])
def build_cs_ids(release: str):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t0 = time.perf_counter()
    vol.reload()
    release = _release(release)
    ids = []
    for path in sorted((Path(MOUNT) / release / "papers").glob("part-*.parquet")):
        ids.extend(_cs_ids(pq.read_table(path)))
    arr = pc.unique(pa.array(ids, type=pa.int64())) if ids else pa.array([], type=pa.int64())
    dest = Path(MOUNT) / release / "cs_corpusids.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"corpusid": arr}), dest, compression="zstd")
    vol.commit()
    return {"rows": len(arr), "seconds": round(time.perf_counter() - t0, 1)}


@app.function(image=image, secrets=[secret], timeout=900)
def list_counts(release: str, datasets: str):
    release = _release(release)
    counts = {}
    for name in (part.strip() for part in datasets.split(",")):
        if name:
            counts[_safe(name)] = len(_urls(release, name))
    return {"release": release, "counts": counts}


@app.local_entrypoint()
def main(datasets: str = "papers", limit: int = 0, max_mb: int = 0, concurrency: int = 100, release: str = "latest"):
    plan = list_counts.remote(release, datasets)
    jobs = []
    for name, count in plan["counts"].items():
        n = count if int(limit) <= 0 else min(int(limit), count)
        jobs += [(name, i, plan["release"], int(max_mb)) for i in range(n)]
    tin = tout = secs = 0.0
    rows = 0
    fn = process_shard.with_options(max_containers=int(concurrency))
    for row in fn.starmap(jobs, order_outputs=False, return_exceptions=True):
        if isinstance(row, BaseException):
            print(f"ERROR {type(row).__name__} {str(row).split('?', 1)[0][:160]}")
            continue
        print(f"{row['dataset']} {row['idx']} in_mb={row['in_mb']} out_mb={row['out_mb']} rows={row['rows']} s={row['seconds']}")
        tin += row["in_mb"]
        tout += row["out_mb"]
        rows += row["rows"]
        secs += row["seconds"]
    print(f"total in_mb={tin:.3f} out_mb={tout:.3f} rows={rows} container_s={secs:.1f}")
