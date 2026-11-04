"""Llamadas a Meta con caché por hash del prompt, costo por modelo y tope.

- La clave sólo la lee `metacall.post_responses`.
- Caché: `RRM_ANALYSIS_CACHE` (carpeta). Repetir el mismo cuerpo cuesta $0.
- Libro de gastos: cada llamada real suma a `LEDGER` y, si hay carpeta, a `ledger.jsonl`.
- Tope: `RRM_ANALYSIS_MAX_USD` (por proceso). Una llamada cuyo peor caso lo rebasa no sale.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from rrm.reader.metacall import parse_json, post_responses, response_text

CONTRIBUTOR = "muse-spark-1.3-contributor"
STANDARD = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"
# USD por token: (entrada, entrada en caché, salida). MODELOS-META, 3 nov 2026.
PRICE = {
    CONTRIBUTOR: (0.10e-6, 0.002e-6, 0.20e-6),
    STANDARD: (1.25e-6, 0.15e-6, 4.25e-6),
    WONDER: (4.00e-6, 0.20e-6, 20.00e-6),
}

_LOCK = threading.Lock()
LEDGER = {"calls": 0, "cached": 0, "usd": 0.0, "by_model": {}, "by_role": {}}


def _cache_dir():
    raw = os.environ.get("RRM_ANALYSIS_CACHE", "").strip()
    return Path(raw) if raw else None


def cost(usage, model):
    usage = usage if isinstance(usage, dict) else {}
    inn = int(usage.get("input_tokens") or 0)
    det = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached = min(int(det.get("cached_tokens") or 0), inn)
    out = int(usage.get("output_tokens") or 0)
    odet = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    pin, pc, pout = PRICE.get(model, PRICE[STANDARD])
    return {
        "input_tokens": inn, "cached_tokens": cached, "output_tokens": out,
        "reasoning_tokens": int(odet.get("reasoning_tokens") or 0),
        "usd": round((inn - cached) * pin + cached * pc + out * pout, 8),
    }


def _ceiling(body):
    pin, _pc, pout = PRICE.get(body.get("model"), PRICE[STANDARD])
    chars = len(json.dumps(body.get("input") or "", ensure_ascii=False))
    return (chars / 3.5) * pin + int(body.get("max_output_tokens") or 2000) * pout


def body_for(model, system, user, *, schema=None, name="out", effort="minimal", max_out=1500, tools=None, extra_input=None):
    body = {
        "model": model,
        "store": False,
        "reasoning": {"effort": effort},
        "max_output_tokens": int(max_out),
        "input": [{"role": "developer", "content": system}, {"role": "user", "content": user}] + list(extra_input or []),
    }
    if schema is not None:
        body["text"] = {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}
    if tools:
        body["tools"] = tools
    return body


def _key(body):
    # RRM_ANALYSIS_SALT cambia la llave de caché sin tocar el prompt (corridas de estabilidad).
    salt = os.environ.get("RRM_ANALYSIS_SALT", "")
    return hashlib.sha256((salt + json.dumps(body, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def _parse(text):
    if not text:
        return None
    got = parse_json(text)
    if got is None:
        from rrm.reader.analysis.candidates import parse_lenient

        got = parse_lenient(text)
        got = got if isinstance(got, dict) else None
    return got


class BudgetExceeded(RuntimeError):
    pass


def call(body, role="", timeout=120, post=None):
    """Devuelve dict: {payload, text, json, cost, cached, wall_s, error}. Nunca reintenta."""
    key = _key(body)
    root = _cache_dir()
    if root is not None:
        path = root / key[:2] / f"{key}.json"
        if path.is_file():
            rec = json.loads(path.read_text(encoding="utf-8"))
            with _LOCK:
                LEDGER["cached"] += 1
            rec["cached"] = True
            return rec
    cap = float(os.environ.get("RRM_ANALYSIS_MAX_USD", "0") or 0)
    if cap > 0:
        with _LOCK:
            if LEDGER["usd"] + _ceiling(body) > cap:
                raise BudgetExceeded(f"tope {cap} USD: llevo {LEDGER['usd']:.4f}")
    t0 = time.perf_counter()
    err, payload = "", None
    try:
        payload = (post or post_responses)(body, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - se reporta, no se reintenta
        err = str(exc)[:300]
    wall = round(time.perf_counter() - t0, 3)
    text = response_text(payload) if payload else ""
    c = cost((payload or {}).get("usage"), body.get("model"))
    rec = {
        "key": key, "model": body.get("model"), "role": role, "wall_s": wall, "error": err,
        "status": (payload or {}).get("status", ""), "text": text, "json": _parse(text),
        "cost": c, "usage": (payload or {}).get("usage") if payload else None, "payload_output": (payload or {}).get("output") if payload else None, "cached": False,
    }
    with _LOCK:
        LEDGER["calls"] += 1
        LEDGER["usd"] = round(LEDGER["usd"] + c["usd"], 8)
        bm = LEDGER["by_model"].setdefault(body.get("model"), {"calls": 0, "usd": 0.0})
        bm["calls"] += 1
        bm["usd"] = round(bm["usd"] + c["usd"], 8)
        br = LEDGER["by_role"].setdefault(role or "-", {"calls": 0, "usd": 0.0})
        br["calls"] += 1
        br["usd"] = round(br["usd"] + c["usd"], 8)
    if root is not None and not err:
        path = root / key[:2] / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec | {"request": body}, ensure_ascii=False), encoding="utf-8")
    if root is not None:
        with (root / "ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": time.time(), "key": key[:12], "role": role, "model": body.get("model"),
                                 "usd": c["usd"], "in": c["input_tokens"], "out": c["output_tokens"],
                                 "reasoning": c["reasoning_tokens"], "wall_s": wall, "error": err}) + "\n")
    return rec


def ask_json(model, system, user, schema, *, role="", effort="minimal", max_out=1500, name="out", timeout=120):
    rec = call(body_for(model, system, user, schema=schema, name=name, effort=effort, max_out=max_out), role=role, timeout=timeout)
    return rec
