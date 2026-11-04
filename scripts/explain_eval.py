"""RRM-100: evalúa los candidatos de Explain contra un set gold.

    python scripts/explain_eval.py --gold <gold.json> --papers <dir> --passages <dir> \
        --cands E0,E1,E2,E3 --runs 1 --out <resultados.json>

El gold vive en compass (privado). Llama a Meta: necesita MODEL_API_KEY y
RRM_EXPLAIN_CACHE para no pagar dos veces la misma llamada.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rrm.reader.explain import llm  # noqa: E402
from rrm.reader.explain.review import PARTS, VERDICTS, Context, review_e1, review_e2, review_e3, sentences  # noqa: E402
from rrm.reader.explain.sheet import build_sheet  # noqa: E402

SEVERITY = {"contradice": 0, "diverge": 1, "sin_respaldo": 2, "coincide": 3}


def _words(text):
    import re
    return set(w.casefold() for w in re.findall(r"[^\W\d_]{3,}", text or ""))


def _n_of(item, sents):
    if isinstance(item.get("n"), int):
        return item["n"]
    words = _words(item.get("text"))
    best, best_n = -1.0, None
    for i, s in enumerate(sents, 1):
        sw = _words(s)
        score = len(words & sw) / max(1, len(words | sw))
        if score > best:
            best, best_n = score, i
    return best_n


def per_claim(parts, sents):
    """n → veredicto más severo que salió para esa oración."""
    got = defaultdict(list)
    ptrs = defaultdict(set)
    for part in VERDICTS:
        for item in parts.get(part) or []:
            n = _n_of(item, sents)
            if n is None:
                continue
            got[n].append(part)
            for c in item.get("cites") or []:
                ptrs[n].add(c.get("ptr"))
            if item.get("ptr"):
                ptrs[n].add(item["ptr"])
    out = {}
    for n, verdicts in got.items():
        out[n] = sorted(verdicts, key=lambda v: SEVERITY[v])[0]
    return out, ptrs


def _e0(paper_dir, text, encode):
    """La caja de main: phrases.json + phrases.npy, rank_similar y las dos llamadas de feedback.py."""
    from rrm.reader.phrases import read_phrases
    from rrm.reader.similar import read_vectors, text_rows
    from rrm.reader.verify import answer

    rows = text_rows(read_phrases(paper_dir))
    for row in rows:
        row.setdefault("paper", int(paper_dir.name))
    vecs = read_vectors(paper_dir, len(rows))
    body = answer(rows, text, ids=[paper_dir.name], root=paper_dir.parent, encode=encode, vectors=vecs, stage="revisar")
    parts = {p: list(body.get("parts", {}).get(p) or []) for p in PARTS}
    for part in PARTS:
        for item in parts[part]:
            row = next((r for r in rows if item.get("cite") and " ".join(item["cite"].split()) in " ".join((r.get("text") or "").split())), None)
            item["cites"] = [{"ptr": "", "text": item.get("cite", "")}] if item.get("cite") else []
    return parts, body.get("meta") or {}


def _missed_score(parts, gold_missed, said=()):
    """Precisión: te_falto que apunta a una idea esperada. Recall: ideas esperadas cubiertas.
    Falso: te_falto que cita una frase que el lector ya explicó bien (`said`)."""
    items = parts.get("te_falto") or []
    groups = [set(g) for g in gold_missed]
    said = set(said)
    hit_items, hit_groups, false = 0, set(), 0
    for item in items:
        mine = {c.get("ptr") for c in item.get("cites") or []} | ({item.get("ptr")} if item.get("ptr") else set())
        false += bool(mine and mine <= said)
        ok = False
        for gi, g in enumerate(groups):
            if mine & g:
                ok = True
                hit_groups.add(gi)
        hit_items += ok
    return len(items), hit_items, len(hit_groups), len(groups), false


_JUDGE = (
    "You grade short explanations shown to a student who explained a paper section in their own words. "
    "Each item has the student's claim, a verdict, the explanation (`why`) and the paper sentences it relies on. "
    "correct: true if the why agrees with the quoted paper sentences and fits the verdict; false if it states something the quotes do not support or contradicts them. "
    "simple: true if a student understands it at first read: plain English, short, no stray words or garbage, no needless jargon. "
    "Grade every item, in order, by its number."
)


def judge(parts, model, salt=""):
    from rrm.reader.explain import llm as L

    items = [(p, it) for p in PARTS for it in parts.get(p) or [] if it.get("why")]
    if not items:
        return [], L.add(None, None)
    listed = "\n\n".join(
        f"{i}. verdict={p}\nclaim: {it.get('text')}\nwhy: {it.get('why')}\nquotes: " + " | ".join(c.get("text", "") for c in it.get("cites") or []) or "none"
        for i, (p, it) in enumerate(items, 1)
    )
    schema = {"type": "object", "additionalProperties": False, "required": ["grades"], "properties": {"grades": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["n", "correct", "simple"],
        "properties": {"n": {"type": "integer"}, "correct": {"type": "boolean"}, "simple": {"type": "boolean"}}}}}}
    payload = L.body(_JUDGE, listed, schema, "grades", model=model, effort="low", tokens=4000)
    resp, cost, _s, _h = L.call(payload, salt=salt)
    data = L.json_of(resp) or {}
    grades = {g.get("n"): g for g in data.get("grades") or [] if isinstance(g, dict)}
    return [grades.get(i) for i in range(1, len(items) + 1)], cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--papers", required=True)
    ap.add_argument("--passages", default="")
    ap.add_argument("--cands", default="E1,E2")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model", default=llm.CONTRIBUTOR)
    ap.add_argument("--effort", default="minimal")
    ap.add_argument("--sheet-effort", default="low")
    ap.add_argument("--sheet-model", default="")
    ap.add_argument("--only", default="", help="paper:section,… para correr un subconjunto")
    ap.add_argument("--kinds", default="", help="buena,parcial,mala")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--threads", type=int, default=6)
    args = ap.parse_args()

    from rrm.reader.similar import specter_encode

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    base = None
    if args.passages:
        from rrm.reader.explain.retrieve import PassageBase
        t0 = time.perf_counter()
        base = PassageBase(args.passages)
        print(f"passages loaded {time.perf_counter() - t0:.1f}s", file=sys.stderr)
    cands = [c.strip() for c in args.cands.split(",") if c.strip()]
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    kinds = {x.strip() for x in args.kinds.split(",") if x.strip()}
    records, sheets, jobs = [], {}, []
    total = llm.add(None, None)
    for sec in gold["sections"]:
        key = f"{sec['paper']}:{sec['section']}"
        if only and key not in only:
            continue
        pdir = Path(args.papers) / str(sec["paper"])
        paper = json.loads((pdir / "paper.json").read_text(encoding="utf-8"))
        ctx = Context(paper, sec["section"], folder=pdir, encode=specter_encode, base=base)
        _ = ctx.vecs
        sheet = None
        if any(c.startswith("E2") for c in cands):
            t0 = time.perf_counter()
            sheet = build_sheet(paper, sec["section"], base=base, encode=specter_encode,
                                model=args.sheet_model or args.model, effort=args.sheet_effort, passages=base is not None)
            sheet["wall_s"] = round(time.perf_counter() - t0, 3)
            total = llm.add(total, sheet["cost"])
            sheets[key] = sheet
        for ai, ans in enumerate(sec["answers"]):
            if kinds and ans["kind"] not in kinds:
                continue
            text = " ".join(c["text"] for c in ans["claims"])
            sents = sentences(text)
            if len(sents) != len(ans["claims"]):
                print(f"WARN split {key} {ans['kind']}: {len(sents)} vs {len(ans['claims'])}", file=sys.stderr)
            for cand in cands:
                for run in range(args.runs):
                    jobs.append((key, ai, ans, text, sents, ctx, sheet, pdir, cand, run))
        # Un hilo por revisión: Meta espera red. El encoder tiene su propio candado.
        from concurrent.futures import ThreadPoolExecutor

        def one(job):
            try:
                return one_(job)
            except Exception as err:  # una llamada caída no tumba la ronda: queda como error, sin reintento
                key, ai, ans, text, sents, ctx, sheet, pdir, cand, run = job
                print(f"{cand} r{run} {key} {ans['kind']:8s} ERROR {type(err).__name__}", file=sys.stderr, flush=True)
                claims = [{"n": n, "gold": gc["verdict"], "ok": gc["ok"], "pred": "error", "right": False, "strict": False, "cite_hit": None}
                          for n, gc in enumerate(ans["claims"], 1)]
                return {"cand": cand, "run": run, "section": key, "kind": ans["kind"], "answer": ai, "claims": claims,
                        "missed": (0, 0, 0, len(ans.get("missed") or []), 0), "others": 0, "wall_s": 0.0, "llm_s": None,
                        "cached": None, "cost": 0.0, "tool_calls": None, "parts": {}, "grades": [], "error": type(err).__name__}, llm.add(None, None), None

        def one_(job):
            key, ai, ans, text, sents, ctx, sheet, pdir, cand, run = job
            salt = f"run{run}" if run else ""
            t0 = time.perf_counter()
            info = {}
            if cand == "E0":
                parts, cost = _e0(pdir, text, specter_encode)
            elif cand == "E1":
                parts, cost, info = review_e1(ctx, text, model=args.model, effort=args.effort, salt=salt)
            elif cand == "E2":
                parts, cost, info = review_e2(ctx, text, sheet, model=args.model, effort=args.effort, salt=salt)
            elif cand == "E2m":
                parts, cost, info = review_e2(ctx, text, sheet, model=args.model, effort=args.effort, salt=salt, pick=True)
            elif cand == "E2np":
                parts, cost, info = review_e2(ctx, text, sheet, model=args.model, effort=args.effort, salt=salt, use_passages=False)
            elif cand == "E3":
                parts, cost, info = review_e3(ctx, text, model=args.model, effort=args.effort, salt=salt)
            else:
                raise SystemExit(f"unknown candidate {cand}")
            wall = time.perf_counter() - t0
            verdicts, ptrs = per_claim(parts, sents)
            claims = []
            for n, gc in enumerate(ans["claims"], 1):
                pred = verdicts.get(n, "none")
                cite_hit = bool(set(gc["ptr"]) & ptrs.get(n, set())) if gc["ptr"] else None
                claims.append({"n": n, "gold": gc["verdict"], "ok": gc["ok"], "pred": pred,
                               "right": pred in gc["ok"], "strict": pred == gc["verdict"], "cite_hit": cite_hit})
            said = {p for gc in ans["claims"] if gc["verdict"] != "sin_respaldo" for p in gc["ptr"]}
            m = _missed_score(parts, ans.get("missed") or [], said)
            grades, jcost = [], None
            if args.judge:
                grades, jcost = judge(parts, llm.CONTRIBUTOR, salt=salt)
            others = sum(len(item.get("others") or []) for p in PARTS for item in parts.get(p) or [])
            right = sum(c["right"] for c in claims)
            print(f"{cand} r{run} {key} {ans['kind']:8s} {right}/{len(claims)} missed={m} others={others} "
                  f"{wall:.1f}s ${cost.get('cost_usd', 0):.5f}", file=sys.stderr, flush=True)
            return {
                "cand": cand, "run": run, "section": key, "kind": ans["kind"], "answer": ai,
                "claims": claims, "missed": m, "others": others, "wall_s": round(wall, 3),
                "llm_s": info.get("llm_s"), "cached": info.get("cached"), "cost": cost.get("cost_usd", 0.0),
                "tool_calls": info.get("tool_calls"), "parts": parts, "grades": grades,
            }, cost, jcost

        with ThreadPoolExecutor(max_workers=args.threads) as pool:
            for rec, cost, jcost in pool.map(one, jobs):
                records.append(rec)
                total = llm.add(total, cost)
                if jcost:
                    total = llm.add(total, jcost)
        jobs = []
    out = {"tag": args.tag, "args": vars(args), "records": records, "sheets": sheets, "total": total, "summary": summarize(records, sheets)}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["summary"], indent=1))
    print(f"TOTAL ${total['cost_usd']:.5f}")


def _rate(rows, key):
    got = [g.get(key) for r in rows for g in r.get("grades") or [] if isinstance(g, dict)]
    return round(sum(1 for x in got if x) / len(got), 3) if got else None


def summarize(records, sheets):
    by = defaultdict(list)
    for r in records:
        by[r["cand"]].append(r)
    out = {}
    for cand, rows in by.items():
        claims = [c for r in rows for c in r["claims"]]
        conf = Counter((c["gold"], c["pred"]) for c in claims)
        hits = [c["cite_hit"] for c in claims if c["right"] and c["cite_hit"] is not None]
        mi = [r["missed"] for r in rows]
        partial = [r["missed"] for r in rows if r["kind"] != "buena"]
        stab = None
        runs = sorted({r["run"] for r in rows})
        if len(runs) > 1:
            grid = defaultdict(dict)
            for r in rows:
                for c in r["claims"]:
                    grid[(r["section"], r["answer"], c["n"])][r["run"]] = c["pred"]
            same = [len(set(v.values())) == 1 for v in grid.values() if len(v) == len(runs)]
            stab = round(sum(same) / max(1, len(same)), 3)
        walls = sorted(r["llm_s"] if r["llm_s"] is not None else r["wall_s"] for r in rows)
        out[cand] = {
            "claims": len(claims), "errors": sum(1 for r in rows if r.get("error")),
            "acc": round(sum(c["right"] for c in claims) / max(1, len(claims)), 3),
            "acc_strict": round(sum(c["strict"] for c in claims) / max(1, len(claims)), 3),
            "acc_by_gold": {g: round(sum(c["right"] for c in claims if c["gold"] == g) / max(1, sum(1 for c in claims if c["gold"] == g)), 3)
                            for g in VERDICTS if any(c["gold"] == g for c in claims)},
            "cite_hit": round(sum(hits) / max(1, len(hits)), 3) if hits else None,
            "missed_items": sum(m[0] for m in mi), "missed_prec": round(sum(m[1] for m in mi) / max(1, sum(m[0] for m in mi)), 3),
            "missed_recall_nonbuena": round(sum(m[2] for m in partial) / max(1, sum(m[3] for m in partial)), 3),
            "missed_false": sum(m[4] for m in mi if len(m) > 4),
            "missed_empty_rate": round(sum(1 for m in mi if m[0] == 0) / max(1, len(mi)), 3),
            "why_correct": _rate(rows, "correct"), "why_simple": _rate(rows, "simple"),
            "why_words_avg": round(sum(len(str(it.get("why") or "").split()) for r in rows for p in PARTS for it in r["parts"].get(p) or [] if it.get("why")) / max(1, sum(1 for r in rows for p in PARTS for it in r["parts"].get(p) or [] if it.get("why"))), 1),
            "others_per_answer": round(sum(r["others"] for r in rows) / max(1, len(rows)), 2),
            "stability": stab,
            "lat_p50": walls[len(walls) // 2] if walls else None, "lat_p90": walls[int(len(walls) * 0.9)] if walls else None,
            "cost": round(sum(r["cost"] for r in rows), 5),
            "confusion": {f"{g}->{p}": n for (g, p), n in sorted(conf.items()) if g != p},
        }
    if sheets:
        out["_sheets"] = {
            "n": len(sheets), "points_avg": round(sum(len(s["points"]) for s in sheets.values()) / len(sheets), 2),
            "passages_avg": round(sum(len(s["passages"]) for s in sheets.values()) / len(sheets), 2),
            "wall_s": sorted(s.get("wall_s", 0) for s in sheets.values()),
            "cost": round(sum(s["cost"]["cost_usd"] for s in sheets.values()), 5),
        }
    return out


if __name__ == "__main__":
    main()
