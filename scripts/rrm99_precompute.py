"""Precalcula /notes v2 (RRM_ANALYSIS=v2) para los papers del demo y lo deja listo para el volumen.

    python scripts/rrm99_precompute.py --cids 13756489,258959321 [--wonder 13756489] [--put]

Salida local: <data>/analysis/v2/<cid>-<hash>.json (mismo nombre que busca run.cache_path).
--put sube cada archivo a rrm-data:/analysis/v2/ (no toca otras rutas del volumen).
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cids", required=True)
    ap.add_argument("--wonder", default="", help="cids cuyo planificador va con Wonder")
    ap.add_argument("--data", default=str(Path.home() / "projects/hackaton/rrm99-data"))
    ap.add_argument("--put", action="store_true")
    a = ap.parse_args()
    data = Path(a.data)
    os.environ.setdefault("RRM_ANALYSIS_CACHE", str(data / "cache"))
    os.environ.setdefault("RRM_PASSAGES_DIR", str(data / "passages"))
    os.environ["RRM_DATA"] = str(data)  # cache_path → <data>/analysis/v2
    os.environ.setdefault("RRM_KATEX_NODE_PATH", str(Path.home() / "projects/hackaton/research-microscope/apps/reader/node_modules"))
    import rrm99_retrieve_modal as M
    from rrm.reader.analysis import llm, run
    from rrm.reader.analysis.candidates import Retr

    stack = contextlib.ExitStack()
    h = {}

    def remote(jobs):
        if "r" not in h:
            stack.enter_context(M.app.run())
            h["r"] = M.Retriever()
        return h["r"].search.remote(jobs)["results"]

    retr = Retr(remote, data / "cache")
    wonder = set(a.wonder.split(",")) if a.wonder else set()
    done = []
    try:
        for cid in a.cids.split(","):
            paper = json.loads((data / "papers" / cid / "paper.json").read_text())
            cfg = {"models": {"planner": llm.WONDER}} if cid in wonder else None
            out = run.analyze_paper(paper, retr=retr, cfg=cfg, write_cache=True)
            out["analysis"]["planner_model"] = llm.WONDER if cid in wonder else llm.CONTRIBUTOR
            brief_hash = out["analysis"]["hash"]
            path = run.cache_path(int(cid), brief_hash)
            path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            print(cid, path.name, len(out["notes"]), "notes", len(out["widgets"]), "widgets", out["analysis"].get("total_s"), "s", flush=True)
            done.append(path)
    finally:
        stack.close()
    print("Meta", llm.LEDGER["usd"])
    if a.put:
        for path in done:
            subprocess.run(["modal", "volume", "put", "--force", "rrm-data", str(path), f"/analysis/v2/{path.name}"], check=True)
            print("put", path.name)


if __name__ == "__main__":
    main()
