"""The only Semantic Scholar API caller.

Every datasets and graph request goes through ``S2Client.get``. Calls are
spaced by at least 1.1 seconds and 429 responses use exponential backoff.
Presigned shard URLs are not fetched here.
"""

from __future__ import annotations

import email.utils
from typing import Callable, MutableMapping

MIN_INTERVAL_SECONDS = 1.1
MAX_ATTEMPTS = 6
MAX_BACKOFF_SECONDS = 60.0

DATASETS_BASE = "https://api.semanticscholar.org/datasets/v1"
GRAPH_ARXIV_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/ARXIV:1706.03762"
    "?fields=paperId,corpusId"
)


class S2ClientError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class S2Response:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body


def _retry_after_seconds(value: str | None, now: float) -> float | None:
    if not value:
        return None
    text = value.strip()
    try:
        return max(float(text), 0.0)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    return max(when - now, 0.0)


class S2Client:
    def __init__(
        self,
        api_key: str,
        *,
        min_interval: float = MIN_INTERVAL_SECONDS,
        session=None,
        sleep: Callable[[float], None] | None = None,
        now: Callable[[], float] | None = None,
        clock_store: MutableMapping | None = None,
        clock_key: str = "s2_last_request_at",
    ):
        if not api_key:
            raise S2ClientError("S2 API key is empty")
        self._api_key = api_key
        self.min_interval = min_interval
        self._session = session
        self._sleep = sleep
        self._now = now
        self._clock_store = clock_store
        self._clock_key = clock_key
        self._next_at = 0.0

    def _clock(self) -> float:
        if self._now is not None:
            return float(self._now())
        import time

        return time.time()

    def _pause(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._sleep is not None:
            self._sleep(seconds)
            return
        import time

        time.sleep(seconds)

    def _session_get(self, url: str, params: dict | None, timeout: float):
        session = self._session
        if session is None:
            import requests

            session = requests.Session()
            self._session = session
        return session.get(
            url,
            params=params,
            headers={"x-api-key": self._api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    def _wait_turn(self) -> None:
        now = self._clock()
        if self._clock_store is not None:
            last = self._clock_store.get(self._clock_key)
            if last is not None:
                self._next_at = max(self._next_at, float(last) + self.min_interval)
        delay = self._next_at - now
        if delay > 0:
            self._pause(delay)
        stamp = self._clock()
        self._next_at = stamp + self.min_interval
        if self._clock_store is not None:
            self._clock_store[self._clock_key] = stamp

    def get(self, url: str, params: dict | None = None, timeout: float = 60.0) -> S2Response:
        backoff = 1.0
        last_status = 0
        for attempt in range(MAX_ATTEMPTS):
            self._wait_turn()
            try:
                response = self._session_get(url, params, timeout)
            except S2ClientError:
                raise
            except Exception as exc:
                last_status = 0
                if attempt + 1 == MAX_ATTEMPTS:
                    raise S2ClientError(
                        f"S2 request failed ({type(exc).__name__})",
                        status=0,
                    ) from None
                self._pause(min(backoff, MAX_BACKOFF_SECONDS))
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue

            last_status = int(response.status_code)
            if last_status == 429 or last_status >= 500:
                if attempt + 1 == MAX_ATTEMPTS:
                    break
                header = None
                headers = getattr(response, "headers", None)
                if headers is not None:
                    header = headers.get("Retry-After")
                retry_after = _retry_after_seconds(header, self._clock())
                delay = backoff if retry_after is None else max(backoff, retry_after)
                self._pause(min(delay, MAX_BACKOFF_SECONDS))
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue

            body = response.content if isinstance(response.content, bytes) else bytes(response.content)
            return S2Response(last_status, body)

        return S2Response(last_status, b"")
