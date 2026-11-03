#!/usr/bin/env python3
"""Arma licenses.json desde un snapshot parquet de metadatos de arXiv.

Lee solo las columnas id, license y versions, y se queda con los ids pedidos.
``--corpus-map`` escribe corpusid por id: un JSON (id → corpusid, o papers[]),
un directorio de fixtures (papers/*.json) o una base sqlite con esas columnas.

    python3 scripts/build_license_map.py --snapshot 'snap/*.parquet' \\
        --ids ids.txt [--corpus-map union_meta.json] --out licenses.json

``version`` es ``v`` + len(versions).
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


def _qid(name):
    return '"' + str(name).replace('"', '""') + '"'


def _corpus_sqlite(path):
    import sqlite3

    con = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    out = {}
    try:
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            cols = [row[1] for row in con.execute(f"PRAGMA table_info({_qid(table)})")]
            low = {col.lower(): col for col in cols}
            ax_col = next((low[key] for key in ("arxiv", "arxiv_id", "arxivid") if key in low), None)
            if ax_col is None and "id" in low and "corpusid" in low:
                ax_col = low["id"]
            cid_col = next((low[key] for key in ("corpusid", "corpus_id") if key in low), None)
            if not ax_col or not cid_col or ax_col == cid_col:
                continue
            query = f"SELECT DISTINCT {_qid(ax_col)}, {_qid(cid_col)} FROM {_qid(table)}"
            for ax, cid in con.execute(query):
                base = _base(ax)
                if base and cid is not None and base not in out:
                    out[base] = cid
            if out:
                return out
    finally:
        con.close()
    return out


def _corpus_dir(root):
    out = {}
    files = sorted(root.glob("papers/*.json")) or sorted(p for p in root.glob("*.json") if p.is_file())
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        paper = data.get("paper") if isinstance(data.get("paper"), dict) else data
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        ax = _base(paper.get("arxivId") or paper.get("arxiv") or meta.get("arxiv") or data.get("arxiv"))
        cid = paper.get("corpusid", meta.get("corpusid", data.get("corpusid")))
        if cid is None and path.stem.isdigit():
            cid = int(path.stem)
        if ax and cid is not None:
            out[ax] = cid
    return out


def load_corpus(path):
    if not path:
        return {}
    file = Path(path)
    if file.is_dir():
        return _corpus_dir(file)
    if file.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return _corpus_sqlite(file)
    data = json.loads(file.read_text(encoding="utf-8"))
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


def read_rows(pattern, wanted):
    """Solo id, license y versions. El filtro por id evita cargar el snapshot entero."""
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise SystemExit(f"no hay parquet en {pattern}")
    try:
        import pyarrow.parquet as pq
    except ImportError as err:
        raise SystemExit("pyarrow is required to read the snapshot by column") from err
    wanted = set(wanted)
    rows = []
    id_names = ("id", "arxiv_id", "arxiv")
    for path in files:
        pf = pq.ParquetFile(path)
        lower = {name.lower(): name for name in pf.schema_arrow.names}
        use = []
        for key in ("id", "arxiv_id", "arxiv", "license", "versions"):
            col = lower.get(key)
            if col and col not in use:
                use.append(col)
        id_col = next((col for col in use if col.lower() in id_names), "")
        if not id_col:
            continue
        filters = [(id_col, "in", sorted(wanted))] if wanted else None
        try:
            table = pf.read(columns=use, filters=filters)
        except (TypeError, ValueError, OSError):
            table = pf.read(columns=use)
        data = table.to_pydict()
        keys = list(data)
        for i in range(table.num_rows):
            row = {key: data[key][i] for key in keys}
            ax = _base(_col(row, "id", "arxiv_id", "arxiv"))
            if ax and ax in wanted:
                rows.append(row)
    return rows


def build(pattern, ids_path, out_path, corpus_path=None):
    wanted = set(load_ids(ids_path))
    corpus = load_corpus(corpus_path)
    out = {"_source": f"snapshot {pattern}; ids {ids_path}"}
    for row in read_rows(pattern, wanted):
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
