#!/usr/bin/env python3
"""E2E check and timing of the deployed burst + reader (+ /panorama). Standard library only.

    RRM_DEMO_TOKEN=... BURST=https://... READER=https://... \\
      python3 scripts/e2e_bench.py --question "how does self-attention work" --approved

It spends only what the deployed services spend (Modal; Meta never, `/panorama` is simulated).
So it refuses a non-local host unless `--approved` is passed: that flag means Franklin
approved this stage and its budget. Use `--dry-run` to print the plan without any network call.

Per question: /burst, poll /status until every top id is settled (done, abstract_only, failed),
/paper for each settled paper, /file for one figure, POST /panorama, then the UI's gate in Python.
Budget guards stop the run and say why. The GPU cost is an ESTIMATE from ocr_gpu_s (L4 list price);
it leaves out CPU, memory and idle containers. The token is read from the environment and never printed
or written. The report holds timings and checks only, no URLs. This script does not stop Modal apps;
it prints the commands.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rrm.demo_e2e import SETTLED_STATUSES, ocr_cap_reached, spent_gpu_this_run
from rrm.panorama import inline_text

L4_USD_PER_S = 0.000222  # same list price as rrm/reader/serve.py (GPU only)
LOCAL = {"localhost", "127.0.0.1", "::1"}


class Stop(Exception):
    """A guard fired; the run ends with a reason."""


class Client:
    def __init__(self, burst, reader, token, budget):
        self.burst, self.reader, self.token, self.budget = burst.rstrip("/"), reader.rstrip("/"), token, budget
        self.requests = 0
        self.started = time.time()

    def call(self, base, path, params=None, body=None, timeout=30, raw=False):
        if self.requests >= self.budget["max_requests"]:
            raise Stop(f"request cap reached ({self.budget['max_requests']})")
        if time.time() - self.started > self.budget["max_minutes"] * 60:
            raise Stop(f"time cap reached ({self.budget['max_minutes']} min)")
        url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        headers = {"X-RRM-Demo": self.token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        self.requests += 1
        t0 = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as r:
                payload = r.read()
                out = payload if raw else json.loads(payload)
                return {"ok": True, "status": r.status, "s": round(time.time() - t0, 3), "data": out}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Stop("401: token rejected")
            return {"ok": False, "status": e.code, "s": round(time.time() - t0, 3), "error": f"HTTP {e.code}"}
        except Exception as e:  # timeout, connection reset, bad JSON
            return {"ok": False, "status": 0, "s": round(time.time() - t0, 3), "error": type(e).__name__}


def block_text(b):
    k = b.get("kind")
    if k in ("p", "h"):
        t = inline_text(b.get("inlines"))
    elif k == "eq":
        t = f"${b.get('tex')}$"
    elif k == "list":
        t = " ".join(inline_text(i) for i in b.get("items") or [])
    else:
        t = inline_text(b.get("caption"))
    return re.sub(r"\s+", " ", t).strip()


def gate(papers, selections):
    """Same rule as validateSelections in the UI: exactly one block holds the quote."""
    ok, rejected = 0, []
    for s in selections:
        doc = papers.get(s.get("paper"))
        q = re.sub(r"\s+", " ", s.get("quote") or "").strip()
        if not doc:
            rejected.append("paper not read")
            continue
        hits = [b for b in doc.get("blocks") or [] if q and q in block_text(b)]
        if len(hits) > 1 and sum(1 for b in hits if b.get("abs")) == 1:
            hits = [b for b in hits if b.get("abs")]
        if len(hits) == 1:
            ok += 1
        else:
            rejected.append("not found" if not hits else f"{len(hits)} times")
    return ok, rejected


def check_bundle(status, doc, reason=None):
    """Problems a bundle has for the UI. Empty list = fine. Never invents a field: a missing one is reported."""
    bad = []
    blocks = doc.get("blocks") or []
    if status == "failed":
        if not (reason or "").strip():
            bad.append("failed without reason")
        return bad
    if not blocks:
        bad.append("no blocks")
    if not any(b.get("abs") for b in blocks):
        bad.append("no abstract block")
    if any(b.get("kind") == "p" and not b.get("sents") for b in blocks):
        bad.append("paragraph without sents")
    if status == "done":
        if not doc.get("arxivId"):
            bad.append("no arxivId")
        for b in blocks:
            if b.get("kind") == "table":
                for rows, spans in ((b.get("head"), b.get("hspan")), (b.get("body"), b.get("bspan"))):
                    if spans is not None and [len(r) for r in rows or []] != [len(s) for s in spans]:
                        bad.append("table span shape differs from rows")
    return bad


def run_question(c, question, args, run_start, spent):
    rec = {"question": question, "stop": None}
    r = c.call(c.burst, "/burst", {"q": question, "n": args.max_papers}, timeout=args.burst_timeout)
    rec["burst_s"] = r["s"]
    if not r["ok"]:
        rec["stop"] = f"burst failed: {r.get('error')}"
        return rec
    papers = [p for p in (r["data"].get("papers") or []) if isinstance(p.get("corpusid"), int)][: args.max_papers]
    ids = [p["corpusid"] for p in papers]
    rec["ids"] = len(ids)
    if not ids:
        rec["stop"] = "empty burst"
        return rec
    rows, t0 = {}, time.time()
    while True:
        s = c.call(c.reader, "/status", {"ids": ",".join(map(str, ids))}, timeout=20)
        if s["ok"]:
            rows = {int(x["id"]): x for x in s["data"].get("papers") or []}
        if all(rows.get(i, {}).get("status") in SETTLED_STATUSES for i in ids):
            break
        if time.time() - t0 > args.settle_timeout:
            rec["stop"] = f"not settled after {args.settle_timeout}s"
            break
        time.sleep(args.poll_interval)
    rec["settle_s"] = round(time.time() - t0, 3)
    states = {}
    for i in ids:
        st = rows.get(i, {}).get("status") or "absent"
        states[st] = states.get(st, 0) + 1
    rec["states"] = states
    gpu_rows = [rows[i] for i in ids if i in rows]
    spent["gpu_papers"] += sum(1 for x in gpu_rows if spent_gpu_this_run(x, run_start))
    spent["gpu_s"] += sum(float(x.get("ocr_gpu_s") or 0) for x in gpu_rows if spent_gpu_this_run(x, run_start))
    docs, paper_s, problems = {}, [], []
    for i in ids:
        row = rows.get(i, {})
        if row.get("status") not in SETTLED_STATUSES:
            continue
        p = c.call(c.reader, "/paper", {"id": i}, timeout=40)
        paper_s.append(p["s"])
        if not p["ok"]:
            problems.append(f"{i}: /paper {p.get('error')}")
            continue
        doc = p["data"].get("paper") or {}
        docs[str(i)] = doc if row["status"] != "failed" else None
        problems += [f"{i}: {m}" for m in check_bundle(row["status"], doc, row.get("reason"))]
    rec["paper_s"] = paper_s
    rec["bundle_problems"] = problems
    fig = next(((i, b["images"][0]) for i, d in docs.items() if d for b in d.get("blocks") or [] if b.get("kind") == "fig" and b.get("images")), None)
    if fig:
        f = c.call(c.reader, "/file", {"id": fig[0], "name": fig[1], "k": c.token}, timeout=20, raw=True)
        rec["figure_file"] = {"ok": f["ok"], "s": f["s"], "bytes": len(f["data"]) if f["ok"] else 0}
    readable = [i for i, d in docs.items() if d]
    if args.panorama and readable:
        pr = c.call(c.reader, "/panorama", body={"question": question, "ids": readable}, timeout=20)
        rec["panorama_s"] = pr["s"]
        if pr["ok"]:
            sels = [s for cl in pr["data"] for s in cl.get("selections") or []]
            ok, rej = gate(docs, sels)
            rec["panorama"] = {"claims": len(pr["data"]), "selections": len(sels), "gate_ok": ok, "gate_rejected": rej}
        else:
            rec["panorama"] = {"error": pr.get("error")}
    return rec


def p50(xs):
    return round(statistics.median(xs), 3) if xs else None


def summarize(recs, spent, stop):
    bursts = [r["burst_s"] for r in recs if "burst_s" in r]
    papers = [x for r in recs for x in r.get("paper_s", [])]
    return {
        "questions_run": len(recs),
        "burst_s": {"p50": p50(bursts), "max": max(bursts, default=None)},
        "settle_s": {"p50": p50([r["settle_s"] for r in recs if "settle_s" in r]), "max": max([r["settle_s"] for r in recs if "settle_s" in r], default=None)},
        "paper_s": {"p50": p50(papers), "max": max(papers, default=None)},
        "panorama_s": {"p50": p50([r["panorama_s"] for r in recs if "panorama_s" in r])},
        "bundle_problems": sum(len(r.get("bundle_problems", [])) for r in recs),
        "gpu_papers_this_run": spent["gpu_papers"],
        "gpu_cost_usd_ESTIMATE": round(spent["gpu_s"] * L4_USD_PER_S, 4),
        "stopped_because": stop,
    }


def parse(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--question", action="append", default=[], help="repeat for several questions")
    a.add_argument("--max-questions", type=int, default=3)
    a.add_argument("--max-papers", type=int, default=10)
    a.add_argument("--max-requests", type=int, default=400)
    a.add_argument("--max-minutes", type=float, default=30)
    a.add_argument("--budget-usd", type=float, default=None, help="stop when the ESTIMATED GPU cost reaches this")
    a.add_argument("--ocr-cap", type=int, default=2, help="stop after this many papers OCR'd on the GPU in this run")
    a.add_argument("--poll-interval", type=float, default=2)
    a.add_argument("--settle-timeout", type=float, default=180)
    a.add_argument("--burst-timeout", type=float, default=150)
    a.add_argument("--no-panorama", dest="panorama", action="store_false")
    a.add_argument("--out", default="e2e-report.json")
    a.add_argument("--approved", action="store_true", help="Franklin approved this stage and its budget (required for non-local hosts)")
    a.add_argument("--dry-run", action="store_true")
    return a.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    burst, reader, token = os.environ.get("BURST", ""), os.environ.get("READER", ""), os.environ.get("RRM_DEMO_TOKEN", "")
    qs = args.question[: args.max_questions]
    plan = {"questions": len(qs), "max_papers": args.max_papers, "max_requests": args.max_requests, "max_minutes": args.max_minutes,
            "budget_usd_estimate_cap": args.budget_usd, "ocr_cap": args.ocr_cap, "panorama": args.panorama}
    print("plan:", json.dumps(plan))
    if not qs:
        print("no --question given", file=sys.stderr)
        return 2
    if args.dry_run:
        print("dry run: no network call made")
        return 0
    if not (burst and reader and token):
        print("set BURST, READER and RRM_DEMO_TOKEN", file=sys.stderr)
        return 2
    hosts = {urllib.parse.urlparse(u).hostname for u in (burst, reader)}
    if not hosts <= LOCAL and not args.approved:
        print("refusing a non-local host without --approved (Franklin's approval of this stage and budget)", file=sys.stderr)
        return 3
    c = Client(burst, reader, token, {"max_requests": args.max_requests, "max_minutes": args.max_minutes})
    run_start, spent, recs, stop = time.time(), {"gpu_papers": 0, "gpu_s": 0.0}, [], None
    try:
        for q in qs:
            recs.append(run_question(c, q, args, run_start, spent))
            if recs[-1].get("stop"):
                stop = f"question {len(recs)}: {recs[-1]['stop']}"
                break
            if spent["gpu_papers"] >= args.ocr_cap:
                stop = f"OCR cap reached ({spent['gpu_papers']} >= {args.ocr_cap})"
                break
            if args.budget_usd is not None and spent["gpu_s"] * L4_USD_PER_S >= args.budget_usd:
                stop = "estimated GPU budget reached"
                break
    except Stop as e:
        stop = str(e)
    report = {"summary": summarize(recs, spent, stop), "requests": c.requests, "wall_s": round(time.time() - run_start, 1), "questions": recs}
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"report: {args.out}  (timings and checks only; do not commit)")
    print("NOW SHUT DOWN what you started, then verify it is empty:")
    print("  modal app stop rrm-reader; modal app stop rrm-burst; modal app list")
    print("  and unset RRM_DEMO_KEEP_WARM / stop scripts/warm.sh if they were on")
    return 1 if (stop and "cap" not in stop and "budget" not in stop) or report["summary"]["bundle_problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
