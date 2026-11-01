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


def add_error_json(web):
    """Turn an unhandled error into a JSON 500 inside CORS.

    Call it before `add_middleware(CORSMiddleware, ...)`: the last middleware
    added is the outermost, so CORS still adds its headers to this 500 and the
    browser sees the status instead of a CORS failure.
    """
    from fastapi.responses import JSONResponse

    @web.middleware("http")
    async def _json_500(request, call_next):
        try:
            return await call_next(request)
        except Exception as err:
            import traceback
            traceback.print_exc()  # sigue en el log de Modal
            return JSONResponse({"error": f"error del servidor ({type(err).__name__})"}, status_code=500)
