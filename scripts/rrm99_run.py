"""RRM-99: corre una ronda (candidatos × papers), juzga y resume. Lo pesado va a Modal.

    python scripts/rrm99_run.py --round r1 --cands C0,C1,C2,C3,C4,C5 --papers 13756489,... \
        --data ~/projects/hackaton/rrm99-data [--cfg '{"passages": false}'] [--tag nopsg] [--no-judge]

Salida: <data>/runs/<round>/<cand><tag>-<cid>.json y <data>/runs/<round>/summary.json.
Caché de Meta en <data>/cache (RRM_ANALYSIS_CACHE); tope por proceso con RRM_ANALYSIS_MAX_USD.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True)
    ap.add_argument("--cands", default="C0,C1,C2,C3,C4,C5")
    ap.add_argument("--papers", default="13756489,258959321,257219404,247778764,249151871")
    ap.add_argument("--data", default=str(Path.home() / "projects/hackaton/rrm99-data"))
    ap.add_argument("--cfg", default="{}")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--v1", action="store_true", help="aplica V1 (juez barato) antes del juez de evaluación")
    args = ap.parse_args()
    data = Path(args.data).expanduser()
    os.environ.setdefault("RRM_ANALYSIS_CACHE", str(data / "cache"))
    os.environ.setdefault("RRM_KATEX_NODE_PATH", str(Path.home() / "projects/hackaton/research-microscope/apps/reader/node_modules"))
    from rrm.reader.analysis import llm
    from rrm.reader.analysis.brief import BriefIndex
    from rrm.reader.analysis.candidates import CANDIDATES, Retr, _cfg, v1
    from rrm.reader.analysis.evaluate import judge, score

    cfg = json.loads(args.cfg)
    gold = json.loads((data / "gold.json").read_text())
    out_dir = data / "runs" / args.round
    out_dir.mkdir(parents=True, exist_ok=True)

    stack = contextlib.ExitStack()
    lock = threading.Lock()
    handle = {}

    def remote(jobs):
        with lock:
            if "r" not in handle:
                import modal
                import rrm99_retrieve_modal as M

                t = time.time()
                stack.enter_context(M.app.run())
                handle["r"] = M.Retriever()
                handle["open_s"] = round(time.time() - t, 1)
        res = handle["r"].search.remote(jobs)
        return res["results"]

    retr = Retr(remote, data / "cache")
    t_round = time.time()

    def run(cand, cid):
        brief = json.loads((data / "briefs" / f"{cid}.json").read_text())
        paper = json.loads((data / "papers" / cid / "paper.json").read_text())
        ix = BriefIndex(brief)
        path = out_dir / f"{cand}{args.tag}-{cid}.json"
        if path.is_file():
            return json.loads(path.read_text())
        before = llm.LEDGER["usd"]
        try:
            res = CANDIDATES[cand](paper, brief, retr, cfg)
        except Exception as exc:  # noqa: BLE001 - un candidato roto no tumba la ronda
            print(f"{cand} {cid}: ERROR {type(exc).__name__}: {exc}", flush=True)
            return {"cand": cand, "cid": cid, "error": f"{type(exc).__name__}: {exc}"}
        if args.v1 and cand != "C0":
            res["items"], vrec = v1(ix, res["items"], _cfg(cfg))
            res["v1_cost"] = (vrec or {}).get("cost", {}).get("usd", 0)
        res["rows"] = {pid: retr.rows[pid] for it in res["items"] for pid in it.get("passages") or [] if pid in retr.rows}
        res.update({"cand": cand + args.tag, "cid": cid, "cfg": cfg})
        if not args.no_judge:
            jrec = judge(ix, res, gold.get(cid, {}).get("items", []))
            res["judge"] = {"json": jrec.get("json"), "cost": jrec["cost"], "error": jrec.get("error")}
            res["score"] = score(ix, res, gold.get(cid, {}).get("items", []), jrec)
        res["round_usd_delta"] = round(llm.LEDGER["usd"] - before, 6)
        path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        s = res.get("score") or {}
        print(f"{cand}{args.tag} {cid}: items={len(res['items'])} covI={s.get('cov_I')} covR={s.get('cov_R')} prec={s.get('precision')} "
              f"rub={s.get('rubric')} wid={s.get('widgets_demo')}/{s.get('n_widgets')} wall={res['wall_s']}s usd={res['usd']}", flush=True)
        return res

    jobs = [(c, p) for p in args.papers.split(",") for c in args.cands.split(",")]
    try:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            results = list(pool.map(lambda j: run(*j), jobs))
    finally:
        stack.close()
    summ = {"round": args.round, "tag": args.tag, "cfg": cfg, "ledger": llm.LEDGER, "wall_round_s": round(time.time() - t_round, 1),
            "modal_open_s": handle.get("open_s"), "retr_remote_s": round(retr.remote_s, 1), "retr_calls": retr.remote_calls}
    prev = out_dir / "summary.json"
    allsum = json.loads(prev.read_text()) if prev.is_file() else []
    allsum.append(summ)
    prev.write_text(json.dumps(allsum, indent=1), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("ledger", "wall_round_s", "modal_open_s", "retr_remote_s")}, indent=1))


if __name__ == "__main__":
    main()
