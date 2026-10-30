#!/usr/bin/env python3
"""DESECHABLE: humo y tiempos contra el backend desplegado. No se mantiene ni tiene pruebas; borrar cuando ya no sirva.

    BURST=... READER=... RRM_DEMO_TOKEN=... python3 scripts/smoke_timing.py "how does self-attention work"

Gasta lo que gasten los servicios (Modal). Una pregunta por corrida. Imprime tiempos, no escribe el token.
Al terminar apaga: modal app stop rrm-reader; modal app stop rrm-burst; modal app list
"""
import json, os, sys, time, urllib.parse, urllib.request

B, R, T = os.environ["BURST"].rstrip("/"), os.environ["READER"].rstrip("/"), os.environ["RRM_DEMO_TOKEN"]
DONE = {"done", "abstract_only", "failed"}


def get(base, path, timeout=60, body=None, **q):
    t0 = time.time()
    req = urllib.request.Request(f"{base}{path}?{urllib.parse.urlencode(q)}" if q else base + path,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"X-RRM-Demo": T, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except Exception as e:
        print(f"{path:10} FALLO {type(e).__name__} {time.time() - t0:.1f}s")
        return None
    print(f"{path:10} {time.time() - t0:6.1f}s")
    return out


q = sys.argv[1]
t_all = time.time()
burst = get(B, "/burst", 160, q=q, n=10)
ids = [p["corpusid"] for p in (burst or {}).get("papers", []) if isinstance(p.get("corpusid"), int)][:10]
rows, t0 = {}, time.time()
while ids and time.time() - t0 < 240:
    rows = {r["id"]: r for r in get(R, "/status", 20, ids=",".join(map(str, ids)))["papers"]}
    if all(rows.get(i, {}).get("status") in DONE for i in ids):
        break
    time.sleep(2)
print(f"todos settled en {time.time() - t0:.1f}s:", {s: sum(1 for r in rows.values() if r.get('status') == s) for s in DONE})
for i, r in rows.items():
    print(i, r.get("status"), r.get("reason") or "", "gpu_s=", r.get("ocr_gpu_s"), "full_s=", r.get("full_s"))
ok = [i for i in ids if rows.get(i, {}).get("status") in ("done", "abstract_only")]
for i in ok[:3]:
    get(R, "/paper", 40, id=i)
if ok:
    get(R, "/panorama", 20, body={"question": q, "ids": [str(i) for i in ok]})
print(f"total {time.time() - t_all:.1f}s")
