"""Tabla de una ronda RRM-99: promedio por candidato sobre los papers + detalle por paper.

    python scripts/rrm99_table.py --round r1 [--data ...] [--detail]
"""

import argparse
import collections
import json
from pathlib import Path

NAMES = {"13756489": "Attention", "258959321": "DPO", "257219404": "LLaMA", "247778764": "Chinchilla", "249151871": "FlashAttn",
         "233307138": "RoFormer", "52967399": "BERT", "259950998": "Llama 2", "267412607": "DeepSeekMath"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True)
    ap.add_argument("--data", default=str(Path.home() / "projects/hackaton/rrm99-data"))
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    runs = sorted((Path(a.data) / "runs" / a.round).glob("C*-*.json"))
    by = collections.defaultdict(list)
    for p in runs:
        r = json.loads(p.read_text())
        if "score" not in r:
            continue
        by[r["cand"]].append(r)
    cols = ["cand", "n", "cov_I", "cov_R", "prec", "rubric", "items", "psg_items", "psg_useful", "wid_demo", "drop_v0", "usd/paper", "wall_s"]
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for cand, rs in sorted(by.items()):
        s = [r["score"] for r in rs]
        mean = lambda k: sum((x.get(k) or 0) for x in s) / len(s)
        rub = [x["rubric"] for x in s if x.get("rubric") is not None]
        row = [cand, len(rs), f"{mean('cov_I'):.2f}", f"{mean('cov_R'):.2f}", f"{mean('precision'):.2f}",
               f"{sum(rub) / len(rub):.2f}" if rub else "-", f"{mean('n_items'):.1f}", sum(x["items_with_passages"] for x in s),
               sum(x["passages_useful"] for x in s), f"{sum(x['widgets_demo'] for x in s)}/{sum(x['n_widgets'] for x in s)}",
               sum(x["dropped_v0"] for x in s), f"{sum(r['usd'] for r in rs) / len(rs):.4f}", f"{sum(r['wall_s'] for r in rs) / len(rs):.0f}"]
        print("| " + " | ".join(str(c) for c in row) + " |")
    if a.detail:
        print()
        print("| cand | paper | cov_I | cov_R | prec | rubric | items | flaws | covered |")
        print("|---|---|---|---|---|---|---|---|---|")
        for cand, rs in sorted(by.items()):
            for r in rs:
                s = r["score"]
                print(f"| {cand} | {NAMES.get(r['cid'], r['cid'])} | {s['cov_I']:.2f} | {s['cov_R']:.2f} | {s['precision']:.2f} | {s['rubric']} | {s['n_items']} | "
                      f"{', '.join(f'{k}:{v}' for k, v in s['flaws'].items() if k != 'none')} | {', '.join(s['covered'])} |")


if __name__ == "__main__":
    main()
