"""Cosecha fuera de Modal, en la IP de esta máquina. Mismas reglas que E2.
    pip install -r rrm/passages/requirements-harvest.txt
    PYTHONPATH=. python -m rrm.passages.harvest_local --out DIR --order union.json --meta union_meta.json --limit N
`--limit` cuenta papers que todavía no están en DIR. El log se escribe siempre.
"""
import argparse
import json
import sys
from pathlib import Path
from rrm.passages.arxiv import ArxivClient, ArxivStopped
from rrm.passages.harvest import harvest_ids
from rrm.passages.store import failure_dir, paper_dir

def load_order(path):
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = body.get("ids") if isinstance(body, dict) else body
    return [int(item) for item in raw or []]

def load_meta_map(path):
    """`{cid: {arxiv_id, title, ...}}` o `{"papers": [...]}`."""
    if not path:
        return {}
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = body.get("papers") if isinstance(body, dict) and "papers" in body else body
    out = {}
    if isinstance(rows, list):
        pairs = ((row.get("corpusid"), row) for row in rows)
    elif isinstance(rows, dict):
        pairs = ((row.get("corpusid", key), row) for key, row in rows.items())
    else:
        raise SystemExit("meta no es un mapa ni una lista de papers")
    for key, row in pairs:
        if not isinstance(row, dict):
            continue
        cid = int(key)
        item = dict(row)
        item["corpusid"] = cid
        item["arxiv_id"] = item.get("arxiv_id") or item.get("arxiv") or ""
        out[cid] = item
    return out

def pending_ids(ids, dest, limit):
    """Los primeros `limit` que no tienen filas ni falla anotada, en el orden dado."""
    dest = Path(dest)
    kept = []
    for cid in ids:
        cid = int(cid)
        if (paper_dir(dest) / f"{cid}.json").is_file():
            continue
        if (failure_dir(dest) / f"{cid}.json").is_file():
            continue
        kept.append(cid)
        if len(kept) >= int(limit):
            break
    return kept

def write_request_log(dest, client, error=None):
    body = {
        "stage": "local",
        "error": error,
        "requests": client.log,
        "gaps_s": client.gaps(),
        "min_gap_s": min(client.gaps()) if client.gaps() else None,
    }
    path = Path(dest) / "local_requests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path

def run_local(order_ids, metas, dest, *, limit, client=None, papers_root=None):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ids = pending_ids(order_ids, dest, limit)
    client = client or ArxivClient()
    error = None
    done = []
    try:
        done = harvest_ids(
            ids,
            metas,
            client=client,
            papers_root=papers_root or (dest / "src_cache"),
            dest=dest,
        )
    except ArxivStopped as err:
        error = str(err)
    finally:
        write_request_log(dest, client, error=error)
    return {"ids": ids, "results": done, "error": error}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Cosecha arXiv local, una IP, reanudable.")
    parser.add_argument("--out", required=True, help="Directorio de papers/, failures/ y el log")
    parser.add_argument("--order", required=True, help="union.json (ids en orden de capa)")
    parser.add_argument("--meta", default="", help="union_meta.json con arxiv_id por corpusid")
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args(argv)
    if args.limit < 1:
        raise SystemExit("--limit tiene que ser ≥ 1")
    metas = load_meta_map(args.meta)
    summary = run_local(load_order(args.order), metas, args.out, limit=args.limit)
    print(json.dumps({
        "attempted": len(summary["ids"]),
        "results": len(summary["results"]),
        "error": summary["error"],
        "log": str(Path(args.out) / "local_requests.json"),
    }, ensure_ascii=False))
    if summary["error"]:
        return 2
    return 0
if __name__ == "__main__":
    sys.exit(main())
