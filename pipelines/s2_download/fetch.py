"""HTTP helpers for presigned shard objects. Not the Semantic Scholar API."""

from __future__ import annotations

import io
from typing import Mapping

USER_AGENT = "research-microscope-s2-download"


class PresignExpired(RuntimeError):
    pass


class DownloadError(RuntimeError):
    def __init__(self, status: int):
        super().__init__(f"shard download status {status}")
        self.status = status


def length_from_headers(headers: Mapping[str, str], status: int) -> int | None:
    """Object size from a GET or a Range response. Does not read a body."""
    content_length = headers.get("Content-Length") or headers.get("content-length")
    if status == 200 and content_length:
        try:
            return int(content_length)
        except ValueError:
            return None
    if status in (200, 206):
        content_range = headers.get("Content-Range") or headers.get("content-range")
        if content_range and "/" in content_range:
            total = content_range.rsplit("/", 1)[-1].strip()
            if total.isdigit():
                return int(total)
    return None


def redact_url(url: str) -> str:
    if "?" in url:
        return url.split("?", 1)[0]
    return url


class CountingReader(io.RawIOBase):
    """Streaming body wrapper that gzip and isal can read.

    isal's gzip reader calls ``readinto``. A bare object with only ``read``
    raises ``AttributeError`` before any row is parsed. Counts stay on this
    object so callers can prove the body was not loaded in one read.
    """

    def __init__(self, raw):
        super().__init__()
        self._raw = raw
        self.bytes_read = 0
        self.max_read = 0
        self.read_all = False
        self.readinto_calls = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def writable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("read of closed file")
        if size is None or size < 0:
            self.read_all = True
            data = self._raw.read()
        elif size == 0:
            return b""
        else:
            self.max_read = max(self.max_read, int(size))
            data = self._raw.read(int(size))
        if not data:
            return b""
        self.bytes_read += len(data)
        return data

    def readinto(self, buffer) -> int:
        if self.closed:
            raise ValueError("read of closed file")
        size = len(buffer)
        self.readinto_calls += 1
        if size == 0:
            return 0
        self.max_read = max(self.max_read, size)
        data = self._raw.read(size)
        if not data:
            return 0
        count = len(data)
        buffer[:count] = data
        self.bytes_read += count
        return count

    def close(self) -> None:
        if self.closed:
            return
        close = getattr(self._raw, "close", None)
        if close:
            close()
        super().close()


def gzip_stream(fileobj):
    """Gzip reader. Uses isal/igzip when it is installed."""
    try:
        import isal.igzip as igzip

        return igzip.GzipFile(fileobj=fileobj)
    except Exception:
        import gzip

        return gzip.GzipFile(fileobj=fileobj)


def open_url_stream(url: str, timeout: tuple[float, float] = (30.0, 300.0)):
    """Start a streaming GET of a presigned object.

    Returns ``(gzip_reader, response, counter, content_length)``.
    The caller closes the gzip reader and the response. The body is never
    buffered as a single bytes object.
    """
    import requests

    response = requests.get(
        url,
        stream=True,
        timeout=timeout,
        headers={"Accept-Encoding": "identity", "User-Agent": USER_AGENT},
    )
    status = int(response.status_code)
    if status in (400, 401, 403):
        response.close()
        raise PresignExpired(str(status))
    if status >= 400:
        response.close()
        raise DownloadError(status)
    length = length_from_headers(response.headers, status)
    raw = response.raw
    raw.decode_content = False
    counter = CountingReader(raw)
    return gzip_stream(counter), response, counter, length


def probe_content_length(url: str, timeout: float = 30.0) -> int | None:
    """Size of a presigned object via a 1-byte range, without reading a shard.

    A server that ignores Range and answers 200 is closed without reading
    the body. Content-Length is used in that case when the server sent it.
    """
    import requests

    response = requests.get(
        url,
        headers={"Range": "bytes=0-0", "Accept-Encoding": "identity", "User-Agent": USER_AGENT},
        timeout=timeout,
        stream=True,
    )
    try:
        status = int(response.status_code)
        if status in (400, 401, 403):
            raise PresignExpired(str(status))
        return length_from_headers(response.headers, status)
    finally:
        response.close()
