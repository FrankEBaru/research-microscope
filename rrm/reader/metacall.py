"""Una llamada a /v1/responses. La clave va en el header y no se registra."""

import json
import os
import re
import urllib.error
import urllib.request

MODEL = "muse-spark-1.3-contributor"
API_URL = "https://api.meta.ai/v1/responses"
_IN = 0.10 / 1_000_000
_CACHE = 0.002 / 1_000_000
_OUT = 0.20 / 1_000_000


def meta_status():
    flag = os.environ.get("RRM_META", "").strip().lower()
    if flag in {"0", "off", "false"}:
        return "apagado"
    if not os.environ.get("MODEL_API_KEY"):
        return "sin clave"
    return ""


def note_for(status):
    return {
        "apagado": "Sin retroalimentación: Meta está apagado.",
        "sin clave": "Sin retroalimentación: no hay clave.",
        "red": "Sin retroalimentación: no hubo red.",
        "parse": "No pude leer la respuesta. Solo quedan los extractos.",
    }.get(status, "")


def parse_json(text):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def response_text(payload):
    chunks = []
    for item in (payload or {}).get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text"):
                chunks.append(part["text"])
    return "\n".join(chunks)


def usage_cost(usage):
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    incoming = int(usage.get("input_tokens") or 0)
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    cached = min(int(details.get("cached_tokens") or 0), incoming)
    outgoing = int(usage.get("output_tokens") or 0)
    cost = (incoming - cached) * _IN + cached * _CACHE + outgoing * _OUT
    return {"input_tokens": incoming, "cached_tokens": cached, "output_tokens": outgoing, "cost_usd": round(cost, 8)}


def add_usage(left, right):
    left, right = left or usage_cost(None), right or usage_cost(None)
    return {
        "input_tokens": left["input_tokens"] + right["input_tokens"],
        "cached_tokens": left["cached_tokens"] + right["cached_tokens"],
        "output_tokens": left["output_tokens"] + right["output_tokens"],
        "cost_usd": round(left["cost_usd"] + right["cost_usd"], 8),
    }


def post_responses(body, timeout=22):
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set")
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:180]
        raise RuntimeError(f"muse http {exc.code}: {detail}") from None
