"""Lado a lado RRM-99: para cada paper y par de candidatos, el juez elige el set de notas que preferiría.
Cada par se juzga dos veces con A/B invertidos; gana quien gana ambas, si no es empate.

    python scripts/rrm99_pairs.py --round r1 --pairs C1:C2,C2:C0 [--papers ...]
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--papers", default="13756489,258959321,257219404,247778764,249151871")
    ap.add_argument("--data", default=str(Path.home() / "projects/hackaton/rrm99-data"))
    ap.add_argument("--round-b", default="", help="ronda del segundo candidato (si difiere)")
    a = ap.parse_args()
    data = Path(a.data)
    os.environ.setdefault("RRM_ANALYSIS_CACHE", str(data / "cache"))
    from rrm.reader.analysis import llm
    from rrm.reader.analysis.brief import BriefIndex
    from rrm.reader.analysis.evaluate import side_by_side

    def load(rnd, cand, cid):
        p = data / "runs" / rnd / f"{cand}-{cid}.json"
        return json.loads(p.read_text()) if p.is_file() else None

    tasks = []
    for pair in a.pairs.split(","):
        x, y = pair.split(":")
        for cid in a.papers.split(","):
            ra, rb = load(a.round, x, cid), load(a.round_b or a.round, y, cid)
            if ra and rb and "items" in ra and "items" in rb:
                tasks.append((x, y, cid, ra, rb))

    def judge(t):
        x, y, cid, ra, rb = t
        ix = BriefIndex(json.loads((data / "briefs" / f"{cid}.json").read_text()))
        r1 = side_by_side(ix, ra, rb).get("json") or {}
        r2 = side_by_side(ix, rb, ra).get("json") or {}
        w1 = {"A": x, "B": y}.get(r1.get("winner"), "tie")
        w2 = {"A": y, "B": x}.get(r2.get("winner"), "tie")
        win = w1 if w1 == w2 else "tie"
        return {"pair": f"{x}:{y}", "cid": cid, "winner": win, "votes": [w1, w2], "reasons": [r1.get("reason", ""), r2.get("reason", "")]}

    with ThreadPoolExecutor(max_workers=8) as pool:
        res = list(pool.map(judge, tasks))
    tally = {}
    for r in res:
        t = tally.setdefault(r["pair"], {})
        t[r["winner"]] = t.get(r["winner"], 0) + 1
    out = data / "runs" / a.round / "pairs.json"
    prev = json.loads(out.read_text()) if out.is_file() else []
    prev += res
    out.write_text(json.dumps(prev, ensure_ascii=False, indent=1))
    for r in res:
        print(r["pair"], r["cid"], r["winner"], r["votes"])
    print(json.dumps(tally, indent=1), "usd", llm.LEDGER["usd"])


if __name__ == "__main__":
    main()
