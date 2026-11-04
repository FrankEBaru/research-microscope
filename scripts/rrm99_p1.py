"""P1/P3 de RRM-99: ¿hay en el top-10 un pasaje útil?, por tipo de consulta; utilidad vs coseno.

Para cada punto I/R de la referencia: 5 consultas (raw, ctx, question, hyde, cited), top-10 cada una
(excluye el propio paper). Un juez contributor marca qué pasajes ayudarían a escribir la nota.

    python scripts/rrm99_p1.py --out p1.json
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

Q_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "properties": {"i": {"type": "integer"}, "question": {"type": "string"}, "draft": {"type": "string"}},
    "required": ["i", "question", "draft"]}}}, "required": ["items"]}
J_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"useful": {"type": "array", "items": {"type": "integer"}},
            "best": {"type": "integer"}}, "required": ["useful", "best"]}
J_SYS = ("A note will explain a spot of a paper to a master's student. Given the spot, what the reader needs, and numbered passages "
         "from OTHER papers, list the numbers of passages that would genuinely help write or support that note (explain the same idea, "
         "give the missing step or definition). Topic overlap alone is not enough. best: the single most useful number, or -1.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path.home() / "projects/hackaton/rrm99-data"))
    ap.add_argument("--out", default="p1.json")
    a = ap.parse_args()
    data = Path(a.data)
    os.environ.setdefault("RRM_ANALYSIS_CACHE", str(data / "cache"))
    import contextlib
    import rrm99_retrieve_modal as M
    from rrm.reader.analysis import llm
    from rrm.reader.analysis.brief import BriefIndex
    from rrm.reader.analysis.candidates import Retr, _job, _query

    gold = json.loads((data / "gold.json").read_text())
    stack = contextlib.ExitStack()
    h = {}

    def remote(jobs):
        if "r" not in h:
            stack.enter_context(M.app.run())
            h["r"] = M.Retriever()
        return h["r"].search.remote(jobs)["results"]

    retr = Retr(remote, data / "cache")
    points = []
    for cid, g in gold.items():
        brief = json.loads((data / "briefs" / f"{cid}.json").read_text())
        ix = BriefIndex(brief)
        cited = sorted({c["corpusid"] for c in brief["cites"] if c.get("in_base") and c.get("corpusid")})
        pts = [it for it in g["items"] if it["level"] in ("I", "R")]
        # Pregunta de lector y borrador HyDE: una llamada por paper (no ve la referencia: sólo el ancla).
        lines = [f"#{i} {ix.text(p['anchors'][0])[:400]}" for i, p in enumerate(pts)]
        rec = llm.call(llm.body_for(llm.CONTRIBUTOR, "For each numbered spot of a paper, write the question a master's student would ask there, "
                                    "and a 2-sentence textbook draft answer. English.", "\n".join(lines), schema=Q_SCHEMA, name="q",
                                    effort="low", max_out=6000), role="p1-q")
        qs = {int(x["i"]): x for x in (rec.get("json") or {}).get("items") or []}
        for i, p in enumerate(pts):
            anchor = p["anchors"][0]
            q = qs.get(i, {})
            points.append({"cid": cid, "id": p["id"], "level": p["level"], "need": p["need"], "anchor": anchor,
                           "anchor_text": ix.text(anchor)[:500], "cited": cited,
                           "queries": {"raw": ix.text(anchor), "ctx": _query(ix, anchor, "ctx"), "question": q.get("question") or ix.text(anchor),
                                       "hyde": q.get("draft") or ix.text(anchor), "cited": _query(ix, anchor, "ctx")}})
    jobs = []
    for p in points:
        for kind, q in p["queries"].items():
            jobs.append(_job(q, p["cid"], 10, only=p["cited"] if kind == "cited" else None) if (kind != "cited" or p["cited"]) else None)
    real = [j for j in jobs if j]
    res = iter(retr.search(real))
    hits = [next(res) if j else [] for j in jobs]
    stack.close()
    k = 0
    tasks = []
    for p in points:
        p["hits"] = {}
        for kind in p["queries"]:
            p["hits"][kind] = hits[k]
            k += 1
        # Un juicio por (punto, consulta).
        for kind, hs in p["hits"].items():
            if hs:
                tasks.append((p, kind, hs))

    def judge(t):
        p, kind, hs = t
        lines = [f"SPOT: {p['anchor_text']}", f"READER NEEDS: {p['need']}", "PASSAGES"]
        lines += [f"{i}. «{h['title'][:60]}» {(h['text'] or h['latex'])[:500]}" for i, h in enumerate(hs)]
        rec = llm.call(llm.body_for(llm.CONTRIBUTOR, J_SYS, "\n".join(lines), schema=J_SCHEMA, name="j", effort="low", max_out=2500), role="p1-judge")
        j = rec.get("json") or {}
        return p, kind, [i for i in j.get("useful") or [] if 0 <= i < len(hs)]

    with ThreadPoolExecutor(max_workers=12) as pool:
        for p, kind, useful in pool.map(judge, tasks):
            p.setdefault("useful", {})[kind] = useful
    # Resumen.
    summ = {}
    for kind in ("raw", "ctx", "question", "hyde", "cited"):
        ps = [p for p in points if p["hits"].get(kind)]
        any_u = sum(1 for p in ps if p.get("useful", {}).get(kind))
        top3 = sum(1 for p in ps if any(i < 3 for i in p.get("useful", {}).get(kind, [])))
        summ[kind] = {"points": len(ps), "any_useful_top10": any_u, "useful_top3": top3, "rate10": round(any_u / max(1, len(ps)), 3), "rate3": round(top3 / max(1, len(ps)), 3)}
    # P3: utilidad por banda de coseno (todas las consultas).
    bands = {}
    for p in points:
        for kind, hs in p["hits"].items():
            u = set(p.get("useful", {}).get(kind, []))
            for i, hh in enumerate(hs):
                b = round(int(hh["cosine"] * 50) / 50, 2)
                x = bands.setdefault(b, [0, 0])
                x[0] += 1
                x[1] += int(i in u)
    summ["by_cosine"] = {str(b): {"n": v[0], "useful": v[1], "rate": round(v[1] / v[0], 3)} for b, v in sorted(bands.items())}
    summ["ledger"] = llm.LEDGER
    for p in points:
        for kind in p["hits"]:
            p["hits"][kind] = [{k2: hh[k2] for k2 in ("pid", "corpusid", "cosine", "title")} for hh in p["hits"][kind]]
    (data / a.out).write_text(json.dumps({"summary": summ, "points": points}, ensure_ascii=False, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
