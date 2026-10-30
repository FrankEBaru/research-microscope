"""How many papers may call GPU OCR in one deploy. No Modal import.

`RRM_OCR_MAX` unset means no cap (the usual deploy). `0` runs no GPU OCR.
A positive cap is claimed in a shared dict. A lost write retries; if the
write never sticks, the claim fails closed so a race cannot exceed the cap.
`ocr_block` set on that dict refuses every claim (the smoke sets it when the
running estimate crosses $2.50).
"""

import os

OWNERS = "ocr_owners"
BLOCK = "ocr_block"
OCR_GPUS = ("L4", "A10G")


def ocr_gpu_from_env(environ=None):
    """GPU for ocr_one. Unset keeps L4, then A10G. One name pins that GPU."""
    env = os.environ if environ is None else environ
    raw = str(env.get("RRM_OCR_GPU", "")).strip()
    if raw == "":
        return list(OCR_GPUS)
    if raw not in OCR_GPUS:
        raise ValueError(f"RRM_OCR_GPU must be one of {OCR_GPUS}, got {raw!r}")
    return raw


def ocr_limit_from_env(environ=None):
    """None when the cap is unset. Otherwise an int >= 0."""
    env = os.environ if environ is None else environ
    raw = str(env.get("RRM_OCR_MAX", "")).strip()
    if raw == "":
        return None
    try:
        n = int(raw)
    except ValueError as err:
        raise ValueError(f"RRM_OCR_MAX must be an integer, got {raw!r}") from err
    if n < 0:
        raise ValueError(f"RRM_OCR_MAX must be >= 0, got {n}")
    return n


def _owners(store) -> list:
    try:
        raw = store[OWNERS]
    except Exception:
        return []
    out = []
    for item in list(raw or []):
        try:
            out.append(str(int(item)))
        except (TypeError, ValueError):
            continue
    return out


def _blocked(store) -> bool:
    try:
        return bool(store[BLOCK])
    except Exception:
        return False


def claim_ocr_slot(store, limit, corpusid, attempts: int = 8) -> bool:
    """True when this corpus id may call the GPU.

    `limit is None` is unlimited and does not touch the store. The same id
    keeps the slot it already holds. A full list, a block flag, or a write
    that never becomes visible returns False.
    """
    if limit is None:
        return True
    limit = int(limit)
    if limit <= 0:
        return False
    me = str(int(corpusid))
    for _ in range(max(1, int(attempts))):
        if _blocked(store):
            return False
        owners = _owners(store)
        if me in owners:
            return owners.index(me) < limit
        if len(owners) >= limit:
            return False
        store[OWNERS] = owners + [me]
        owners = _owners(store)
        if me in owners:
            return owners.index(me) < limit
    return False
