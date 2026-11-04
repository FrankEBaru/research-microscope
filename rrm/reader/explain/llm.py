"""Una llamada a Muse con caché opcional en disco y costo por modelo.

`RRM_EXPLAIN_CACHE=<dir>` guarda cada respuesta por hash del cuerpo: repetir
sin cambios cuesta $0. `salt` separa corridas que deben ser independientes
(estabilidad) sin tocar el prompt.
"""

import hashlib
import json
import os
import time
from pathlib import Path

from rrm.reader.metacall import parse_json, post_responses, response_text

CONTRIBUTOR = "muse-spark-1.3-contributor"
WONDER = "muse-wonder-1.0"
# USD por token (entrada, entrada en caché, salida). Contributor: metacall.py.
# Wonder estándar: MODELOS-META, 3 nov 2026 (el mismo de scripts_live.py de RRM-96).
_PRICE = {
    CONTRIBUTOR: (0.10e-6, 0.002e-6, 0.20e-6),
    WONDER: (4.00e-6, 0.20e-6, 20.00e-6),
}


def price(model, usage):
    usage = usage if isinstance(usage, dict) else {}
    rate_in, rate_cache, rate_out = _PRICE.get(model, _PRICE[CONTRIBUTOR])
    incoming = int(usage.get("input_tokens") or 0)
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached = min(int(details.get("cached_tokens") or 0), incoming)
    outgoing = int(usage.get("output_tokens") or 0)
    cost = (incoming - cached) * rate_in + cached * rate_cache + outgoing * rate_out
    return {"input_tokens": incoming, "cached_tokens": cached, "output_tokens": outgoing, "cost_usd": round(cost, 8)}


def add(left, right):
    keys = ("input_tokens", "cached_tokens", "output_tokens", "cost_usd")
    left, right = left or {}, right or {}
    out = {key: (left.get(key) or 0) + (right.get(key) or 0) for key in keys}
    out["cost_usd"] = round(out["cost_usd"], 8)
    return out


def _cache_dir():
    raw = os.environ.get("RRM_EXPLAIN_CACHE", "").strip()
    return Path(raw) if raw else None


def body(prompt, user, schema=None, name="out", model=None, effort="minimal", tokens=2000, tools=None):
    out = {
        "model": model or CONTRIBUTOR, "store": False, "max_output_tokens": tokens,
        "input": [{"role": "developer", "content": prompt}, {"role": "user", "content": user}],
    }
    if effort:
        out["reasoning"] = {"effort": effort}
    if schema is not None:
        out["text"] = {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}
    if tools:
        out["tools"] = tools
    return out


def call(payload, *, salt="", timeout=60, post=None):
    """→ (respuesta cruda, costo, segundos, de_caché)."""
    folder = _cache_dir()
    key = hashlib.sha256((salt + json.dumps(payload, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:32]
    path = folder / f"{key}.json" if folder else None
    if path is not None and path.is_file():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            return saved["response"], price(payload.get("model"), saved["response"].get("usage")), saved.get("seconds", 0.0), True
        except (OSError, ValueError, KeyError):
            pass
    started = time.perf_counter()
    response = (post or post_responses)(payload, timeout=timeout)
    seconds = round(time.perf_counter() - started, 3)
    if path is not None:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"response": response, "seconds": seconds}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    return response, price(payload.get("model"), response.get("usage") if isinstance(response, dict) else None), seconds, False


def json_of(response):
    return parse_json(response_text(response))
