"""Cliente de arXiv para esta corrida. No es el BurstGate del lector.

Una sola conexión, nunca en paralelo entre máquinas. Al menos 3.5 s entre
el inicio de una petición y el de la siguiente. Host `export.arxiv.org`.
User-Agent con contacto en `RRM_ARXIV_CONTACT`. Ante 429 o 503 se espera
(backoff) y, si se repite, se para. No se sube la velocidad.
"""

import os
import re
import threading
import time
import urllib.error
import urllib.request

from rrm.reader.fetch import canon_arxiv

HOST = "https://export.arxiv.org"
MIN_INTERVAL = 3.5

_LICENSE_HREF = re.compile(r"<(?:[\w.-]+:)?license\b[^>]*href=\"([^\"]+)\"", re.I)
_LICENSE_TEXT = re.compile(r"<(?:[\w.-]+:)?license\b[^>]*>([^<]+)</(?:[\w.-]+:)?license>", re.I)


class ArxivStopped(RuntimeError):
    """429 o 503 repetidos. La etapa se detiene y se avisa."""


class ArxivHTTPError(RuntimeError):
    def __init__(self, code, url):
        self.code = int(code)
        self.reason = "404" if self.code == 404 else f"http {self.code}"
        super().__init__(self.reason)
        self.url = url


def user_agent():
    contact = os.environ.get("RRM_ARXIV_CONTACT", "").strip() or "https://github.com/FrankEBaru/research-microscope"
    return f"research-microscope/passages (RRM-55; contact: {contact})"


def parse_license(body) -> str:
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    body = body or ""
    match = _LICENSE_HREF.search(body)
    if match:
        return match.group(1).strip()
    match = _LICENSE_TEXT.search(body)
    if match:
        return match.group(1).strip()
    return ""


class HarvestGate:
    """Reloj de una sola conexión. El intervalo nunca baja de 3.5 s."""

    def __init__(self, interval=MIN_INTERVAL, sleep=time.sleep, now=time.time):
        self.interval = max(MIN_INTERVAL, float(interval))
        self.sleep = sleep
        self.now = now
        self.next = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            delay = self.next - self.now()
            if delay > 0:
                self.sleep(delay)
            self.next = self.now() + self.interval


def urlopen(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


class ArxivClient:
    """Una conexión. `opener(url, user_agent) -> bytes` permite mockear la red."""

    def __init__(self, opener=None, gate=None, sleep=time.sleep, tries=6, stop_after=3):
        self.opener = opener or urlopen
        self.gate = gate or HarvestGate(sleep=sleep)
        self.sleep = sleep
        self.tries = max(1, int(tries))
        self.stop_after = max(1, int(stop_after))
        self._streak = 0
        self._lock = threading.Lock()

    def get(self, url) -> bytes:
        with self._lock:
            return self._get(url)

    def _get(self, url) -> bytes:
        delay = max(self.gate.interval, MIN_INTERVAL)
        last = None
        for _attempt in range(self.tries):
            self.gate.wait()
            try:
                body = self.opener(url, user_agent())
            except urllib.error.HTTPError as err:
                last = err
            else:
                self._streak = 0
                return body
            if last.code in (429, 503):
                self._streak += 1
                if self._streak >= self.stop_after:
                    raise ArxivStopped(f"arXiv http {last.code} repeated")
                self.sleep(delay)
                delay = min(delay * 2, 120.0)
                continue
            raise ArxivHTTPError(last.code, url) from last
        code = last.code if last is not None else 0
        raise ArxivHTTPError(code, url)

    def eprint_url(self, arxiv_id) -> str:
        return f"{HOST}/e-print/{canon_arxiv(arxiv_id)}"

    def license_url(self, arxiv_id) -> str:
        return f"{HOST}/api/query?id_list={canon_arxiv(arxiv_id)}"

    def fetch_eprint(self, arxiv_id) -> bytes:
        return self.get(self.eprint_url(arxiv_id))

    def fetch_license(self, arxiv_id) -> str:
        return parse_license(self.get(self.license_url(arxiv_id)))
