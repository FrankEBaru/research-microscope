#!/usr/bin/env python3
"""Arma licenses.json desde un snapshot parquet de metadatos de arXiv.

No lo corre el agente sobre datos reales. Prueba con un parquet diminuto:

    python3 scripts/build_license_map.py --snapshot 'snap/*.parquet' \\
        --ids ids.txt [--corpus-map union_meta.json] --out licenses.json

``--ids`` es un archivo de ids de arXiv (uno por línea) o un JSON
(lista, o un objeto tipo union_meta). ``version`` es ``v`` + len(versions).
"""

import argparse
import glob
import json
import re
from pathlib import Path

_ARXIV = re.compile(r"(\d{4}\.\d{4,5}|(?:[a-z-]+(?:\.[a-z]{2})?)/\d{7})", re.I)


def _base(raw):
    match = _ARXIV.search(str(raw or "").strip())
    return match.group(1) if match else ""


def _ids_from(data):
    found = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                found.append(_base(item) or item.strip())
            elif isinstance(item, dict):
                found.append(_base(item.get("arxiv") or item.get("arxiv_id") or item.get("id")))
    elif isinstance(data, dict):
        if isinstance(data.get("papers"), list):
            return _ids_from(data["papers"])
        for key, val in data.items():
            if str(key).startswith("_"):
                continue
            if _base(key):
                found.append(_base(key))
            elif isinstance(val, dict):
                found.append(_base(val.get("arxiv") or val.get("arxiv_id") or val.get("id")))
    return [item for item in found if item]


def load_ids(path):
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if file.suffix == ".json" or text.lstrip()[:1] in "{[":
        return _ids_from(json.loads(text))
    return [_base(line) or line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def load_corpus(path):
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    rows = data.get("papers") if isinstance(data, dict) and isinstance(data.get("papers"), list) else None
    if rows is None and isinstance(data, list):
        rows = data
    if rows is not None:
        for item in rows:
            if not isinstance(item, dict):
                continue
            ax = _base(item.get("arxiv") or item.get("arxiv_id") or item.get("id"))
            cid = item.get("corpusid", item.get("corpus_id"))
            if ax and cid is not None:
                out[ax] = cid
        return out
    if isinstance(data, dict):
        for key, val in data.items():
            ax = _base(key)
            if not ax:
                continue
            if isinstance(val, dict):
                cid = val.get("corpusid", val.get("corpus_id"))
            else:
                cid = val
            if cid is not None:
                out[ax] = cid
    return out


def _col(row, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    folded = {str(key).lower(): val for key, val in row.items()}
    for name in names:
        if name in folded and folded[name] is not None:
            return folded[name]
    return None


def _version(value):
    if value is None:
        return ""
    try:
        return "v" + str(len(list(value)))
    except TypeError:
        return ""


def read_rows(pattern):
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise SystemExit(f"no hay parquet en {pattern}")
    try:
        import duckdb
    except ImportError:
        duckdb = None
    if duckdb is not None:
        cur = duckdb.connect().execute("SELECT * FROM read_parquet(?)", [files])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, rec)) for rec in cur.fetchall()]
    import pyarrow.dataset as ds

    return ds.dataset(files, format="parquet").to_table().to_pylist()


def build(pattern, ids_path, out_path, corpus_path=None):
    wanted = set(load_ids(ids_path))
    corpus = load_corpus(corpus_path)
    out = {"_source": f"snapshot {pattern}; ids {ids_path}"}
    for row in read_rows(pattern):
        ax = _base(_col(row, "id", "arxiv_id", "arxiv"))
        if not ax or ax not in wanted:
            continue
        cid = corpus.get(ax)
        if cid is None:
            cid = _col(row, "corpusid", "corpus_id")
        out[ax] = {"license": _col(row, "license") or "", "version": _version(_col(row, "versions")), "corpusid": cid}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Snapshot parquet + ids → licenses.json. No usa datos en este repo.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--ids", required=True)
    parser.add_argument("--corpus-map", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    build(args.snapshot, args.ids, args.out, args.corpus_map or None)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
