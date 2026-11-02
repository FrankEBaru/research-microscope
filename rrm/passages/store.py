"""rows.parquet, índice exacto y manifest en `passages/`.

El índice es `IndexFlatIP` sobre float32 normalizado. El producto punto es
el coseno que devuelve la consulta. El índice de papers sigue siendo
IVF-PQ con L2; este es otro índice.
"""

import json
import os
from pathlib import Path

import numpy as np

from rrm.passages.embed import embed_policy, l2_normalize, proximity_name
from rrm.passages.rows import excluded_headings, generic_headings
from rrm.passages.union import title_notes

ROWS_SCHEMA_FIELDS = (
    "id",
    "corpusid",
    "arxiv_id",
    "kind",
    "section",
    "text",
    "latex",
    "license",
    "url",
    "title",
    "head",
    "ctx_before",
    "ctx_after",
    "ctx_refs",
)


def _schema():
    import pyarrow as pa

    return pa.schema([
        ("id", pa.string()),
        ("corpusid", pa.int64()),
        ("arxiv_id", pa.string()),
        ("kind", pa.string()),
        ("section", pa.string()),
        ("text", pa.string()),
        ("latex", pa.string()),
        ("license", pa.string()),
        ("url", pa.string()),
        ("title", pa.string()),
        ("head", pa.string()),
        ("ctx_before", pa.string()),
        ("ctx_after", pa.string()),
        ("ctx_refs", pa.list_(pa.string())),
    ])


def _clean_row(row):
    out = {}
    for name in ROWS_SCHEMA_FIELDS:
        value = row.get(name)
        if name == "corpusid":
            out[name] = int(value)
        elif name == "ctx_refs":
            out[name] = [str(item) for item in value or []]
        else:
            out[name] = "" if value is None else str(value)
    return out


def paper_dir(dest):
    return Path(dest) / "papers"


def failure_dir(dest):
    return Path(dest) / "failures"


def paper_record(meta, rows):
    by = {"eq": 0, "p": 0, "def": 0}
    for row in rows or []:
        kind = row.get("kind")
        if kind in by:
            by[kind] += 1
    return {
        "corpusid": int(meta["corpusid"]),
        "arxiv_id": meta.get("arxiv_id") or "",
        "url": meta.get("url") or "",
        "license": meta.get("license") or "",
        "title": meta.get("title"),
        "year": meta.get("year"),
        "venue": meta.get("venue"),
        "citationcount": meta.get("citationcount"),
        "authors": list(meta.get("authors") or []),
        "has_emb": meta.get("has_emb"),
        "title_notes": title_notes(meta.get("title")),
        "rows": by,
        "table": meta.get("table"),
    }


def save_paper_rows(dest, meta, rows):
    path = paper_dir(dest) / f"{int(meta['corpusid'])}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"paper": paper_record(meta, rows), "rows": [_clean_row(row) for row in rows or []]}
    _atomic_json(path, body)
    return path


def save_failure(dest, corpusid, reason):
    path = failure_dir(dest) / f"{int(corpusid)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(path, {"corpusid": int(corpusid), "reason": str(reason)[:500]})
    return path


def load_saved(dest):
    papers, rows, failures = [], [], []
    root = paper_dir(dest)
    if root.is_dir():
        files = sorted(root.glob("*.json"), key=lambda path: int(path.stem))
        for path in files:
            body = json.loads(path.read_text(encoding="utf-8"))
            papers.append(body.get("paper") or {})
            rows.extend(body.get("rows") or [])
    fail_root = failure_dir(dest)
    if fail_root.is_dir():
        for path in sorted(fail_root.glob("*.json"), key=lambda item: int(item.stem)):
            failures.append(json.loads(path.read_text(encoding="utf-8")))
    return papers, rows, failures


def write_rows_parquet(dest, rows):
    import pyarrow as pa
    import pyarrow.parquet as pq

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    schema = _schema()
    cleaned = [_clean_row(row) for row in rows or []]
    table = pa.Table.from_pylist(cleaned, schema=schema)
    tmp = dest / "rows.parquet.partial"
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, dest / "rows.parquet")
    return dest / "rows.parquet"


def read_rows(path):
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    return table.to_pylist()


def write_faiss(dest, vectors):
    """IndexFlatIP. Los vectores se normalizan aquí. El orden es el de las filas."""
    import faiss

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    unit = l2_normalize(vectors)
    if unit.ndim != 2 or unit.shape[0] == 0:
        raise ValueError("no vectors")
    index = faiss.IndexFlatIP(int(unit.shape[1]))
    index.add(np.ascontiguousarray(unit, dtype=np.float32))
    tmp = dest / "faiss.index.partial"
    faiss.write_index(index, str(tmp))
    os.replace(tmp, dest / "faiss.index")
    return index, unit


def read_faiss_vectors(path):
    import faiss

    index = faiss.read_index(str(path))
    n = int(index.ntotal)
    if n == 0:
        return index, np.zeros((0, int(index.d)), dtype=np.float32)
    vectors = np.asarray(index.reconstruct_n(0, n), dtype=np.float32)
    return index, vectors


def code_commit():
    env = os.environ.get("RRM_COMMIT", "").strip()
    if env:
        return env
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def versions():
    faiss_version = ""
    try:
        import faiss

        faiss_version = str(getattr(faiss, "__version__", "") or "")
    except Exception:
        faiss_version = ""
    return {
        "specter2": proximity_name(),
        "specter2_base": "allenai/specter2_base",
        "faiss": faiss_version,
        "parser": "rrm.reader.latex",
    }


def build_manifest(papers, failures, *, quota_source=None, index_built=False, commit=None, layer_donors=None):
    counts = {"papers": len(papers or []), "rows": 0, "eq": 0, "p": 0, "def": 0}
    for paper in papers or []:
        by = paper.get("rows") or {}
        for kind in ("eq", "p", "def"):
            n = int(by.get(kind) or 0)
            counts[kind] += n
            counts["rows"] += n
    return {
        "papers": list(papers or []),
        "counts": counts,
        "failures": list(failures or []),
        "excluded_headings": excluded_headings(),
        "generic_headings": generic_headings(),
        "embed_text": embed_policy(),
        "quota_source": quota_source,
        "layer_donors": None if layer_donors is None else list(layer_donors),
        "index": {
            "type": "IndexFlatIP",
            "dtype": "float32",
            "normalized": True,
            "metric": "inner product of L2-normalized vectors equals cosine",
            "built": bool(index_built),
        },
        "versions": versions(),
        "commit": commit if commit is not None else code_commit(),
        "reader_cache": "save_paper + save_meta + write_phrases; figures skipped; BurstGate not used",
    }


def write_manifest(dest, manifest):
    path = Path(dest) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(path, manifest)
    return path


def read_manifest(dest):
    path = Path(dest) / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def compile_store(dest, *, quota_source=None, commit=None, layer_donors=None):
    """Junta los JSON por paper en rows.parquet y reescribe el manifest."""
    existing = read_manifest(dest) or {}
    if quota_source is None:
        quota_source = existing.get("quota_source")
    if layer_donors is None:
        layer_donors = existing.get("layer_donors")
    papers, rows, failures = load_saved(dest)
    write_rows_parquet(dest, rows)
    built = (Path(dest) / "faiss.index").is_file()
    manifest = build_manifest(
        papers, failures, quota_source=quota_source, index_built=built, commit=commit,
        layer_donors=layer_donors,
    )
    write_manifest(dest, manifest)
    return manifest


def _atomic_json(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
