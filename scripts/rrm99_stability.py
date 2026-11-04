"""Estabilidad RRM-99: coincidencia de los puntos elegidos entre corridas (rondas con distinta sal).

    python scripts/rrm99_stability.py --rounds r2,s1,s2 --cand C1
Coincidencia de anclas: Jaccard con tolerancia ±1 oración; y de puntos de la referencia cubiertos.
"""

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--papers", default="13756489,258959321,257219404,247778764,249151871")
    ap.add_argument("--data", default=str(Path.home() / "projects/hackaton/rrm99-data"))
    a = ap.parse_args()
    from rrm.reader.analysis.contract import _near

    data = Path(a.data)
    rows = []
    for cid in a.papers.split(","):
        runs = []
        for rnd in a.rounds.split(","):
            p = data / "runs" / rnd / f"{a.cand}-{cid}.json"
            if p.is_file():
                runs.append(json.loads(p.read_text()))
        if len(runs) < 2:
            continue
        jac, cov = [], []
        for x, y in itertools.combinations(runs, 2):
            ax, ay = [i["anchor"] for i in x["items"]], [i["anchor"] for i in y["items"]]
            inter = sum(1 for p in ax if any(_near(p, q) for q in ay))
            jac.append(inter / max(1, len(set(ax)) + len(set(ay)) - inter))
            cx, cy = set((x.get("score") or {}).get("covered") or []), set((y.get("score") or {}).get("covered") or [])
            if cx or cy:
                cov.append(len(cx & cy) / max(1, len(cx | cy)))
        covI = [(r.get("score") or {}).get("cov_I") for r in runs]
        rows.append({"cid": cid, "runs": len(runs), "anchor_jaccard": round(sum(jac) / len(jac), 2),
                     "covered_jaccard": round(sum(cov) / len(cov), 2) if cov else None, "cov_I": covI})
    for r in rows:
        print(r)
    if rows:
        print("mean anchor_jaccard", round(sum(r["anchor_jaccard"] for r in rows) / len(rows), 2))


if __name__ == "__main__":
    main()
