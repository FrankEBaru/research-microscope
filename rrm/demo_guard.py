"""Shared demo token and CORS allow-list for the burst and reader HTTP apps.

The token is also baked into the static UI bundle. It stops a person who only
has the modal.run URL. It does not stop someone who can read the bundle.
"""

import hmac
import os

ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
)


def cors_kwargs():
    return {
        "allow_origins": list(ALLOWED_ORIGINS),
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["X-RRM-Demo", "Content-Type"],
        "allow_credentials": False,
    }


def check(header, query, origin=None):
    """Return 401 or 403, or None when the request may proceed.

    `query` is the `/file` token (`k`). Other routes pass None so a query
    string cannot authorize them. An empty `RRM_DEMO_TOKEN` fails closed.
    """
    expected = os.environ.get("RRM_DEMO_TOKEN") or ""
    if not expected:
        return 401
    supplied = header or ""
    if not supplied and query:
        supplied = query
    if not supplied:
        return 401
    try:
        ok = hmac.compare_digest(str(supplied), str(expected))
    except Exception:
        return 401
    if not ok:
        return 401
    if origin and origin not in ALLOWED_ORIGINS:
        return 403
    return None
