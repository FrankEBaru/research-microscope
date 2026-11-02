"""Cliente de arXiv para esta corrida. No es el BurstGate del lector.

Una sola conexión, nunca en paralelo entre máquinas. Al menos 8 s entre
el inicio de una petición y el de la siguiente, sea e-print, API u OAI:
todas pasan por el mismo gate. Host `export.arxiv.org`. La licencia sale de
OAI-PMH GetRecord (metadataPrefix=arXiv) y está apagada por defecto.
Cada petición queda en `client.log` con hora, código y pausa real.
User-Agent con contacto en `RRM_ARXIV_CONTACT`. Se respeta `Retry-After`.
Ante 429 se espera al menos 5 min; si se repite, se para. No se sube la velocidad.
"""

import os
import re
import threading
import time
import urllib.error
import urllib.request

from rrm.reader.fetch import canon_arxiv

HOST = "https://export.arxiv.org"
MIN_INTERVAL = 8.0
# Ante 429: nunca menos de 5 min, aunque Retry-After pida menos.
RETRY_429_S = 300.0

_LICENSE_HREF = re.compile(r"<(?:[\w.-]+:)?license\b[^>]*href=\"([^\"]+)\"", re.I)
_LICENSE_TEXT = re.compile(r"<(?:[\w.-]+:)?license\b[^>]*>([^<]+)</(?:[\w.-]+:)?license>", re.I)


class ArxivStopped(RuntimeError):
    """429 o 503 repetidos. La etapa se detiene y se avisa."""


class LicenseLookupError(RuntimeError):
    """OAI respondió sin licencia o con error. El motivo va en el resultado."""


_OAI_ERROR = re.compile(r"<error\b[^>]*code=\"([^\"]+)\"[^>]*>([^<]*)</error>", re.I)


def parse_oai_license(body) -> str:
    """`<license>` del registro OAI. Error OAI o registro sin licencia: LicenseLookupError."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    body = body or ""
    err = _OAI_ERROR.search(body)
    if err:
        raise LicenseLookupError(f"oai {err.group(1)}: {err.group(2).strip()}"[:200])
    found = parse_license(body)
    if not found:
        raise LicenseLookupError("oai sin <license>")
    return found


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
    """Reloj de una sola conexión. El intervalo nunca baja de 8 s."""

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


def retry_after(headers):
    """Segundos de `Retry-After` si viene como número. None si no viene."""
    try:
        raw = headers.get("Retry-After") if headers is not None else None
        return float(raw) if raw is not None and str(raw).strip() else None
    except (TypeError, ValueError):
        return None


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
        self._streak_429 = 0
        self._backoff = MIN_INTERVAL
        self._prev_start = None
        self._lock = threading.Lock()
        self.log = []
        self.now = time.time

    def get(self, url) -> bytes:
        with self._lock:
            return self._get(url)

    def _get(self, url) -> bytes:
        last = None
        for _attempt in range(self.tries):
            self.gate.wait()
            now = self.now()
            pause = None if self._prev_start is None else round(now - self._prev_start, 3)
            self._prev_start = now
            entry = {"url": url, "start": now, "pause_s": pause}
            self.log.append(entry)
            try:
                body = self.opener(url, user_agent())
            except urllib.error.HTTPError as err:
                last = err
                entry.update(status=int(err.code), seconds=round(self.now() - now, 3))
            except Exception as err:
                entry.update(status=0, error=type(err).__name__, seconds=round(self.now() - now, 3))
                raise
            else:
                self._streak = 0
                self._streak_429 = 0
                entry.update(status=200, bytes=len(body or b""), seconds=round(self.now() - now, 3))
                return body
            if last.code == 429:
                self._streak_429 += 1
                hinted = retry_after(getattr(last, "headers", None))
                wait = max(RETRY_429_S, hinted or 0.0)
                entry["retry_after"] = hinted
                entry["backoff_s"] = wait
                if self._streak_429 >= 2:
                    raise ArxivStopped("arXiv http 429 repeated")
                self.sleep(wait)
                continue
            if last.code == 503:
                self._streak += 1
                hinted = retry_after(getattr(last, "headers", None))
                wait = max(self._backoff, hinted or 0.0)
                if hinted is not None:
                    entry["retry_after"] = hinted
                entry["backoff_s"] = wait
                if self._streak >= self.stop_after:
                    raise ArxivStopped("arXiv http 503 repeated")
                self.sleep(wait)
                self._backoff = min(wait * 2, 120.0)
                continue
            raise ArxivHTTPError(last.code, url) from last
        code = last.code if last is not None else 0
        raise ArxivHTTPError(code, url)

    def eprint_url(self, arxiv_id) -> str:
        return f"{HOST}/e-print/{canon_arxiv(arxiv_id)}"

    def license_url(self, arxiv_id) -> str:
        return (
            f"{HOST}/oai2?verb=GetRecord&metadataPrefix=arXiv"
            f"&identifier=oai:arXiv.org:{canon_arxiv(arxiv_id)}"
        )

    def fetch_eprint(self, arxiv_id) -> bytes:
        return self.get(self.eprint_url(arxiv_id))

    def fetch_license(self, arxiv_id) -> str:
        return parse_oai_license(self.get(self.license_url(arxiv_id)))

    def gaps(self):
        """Segundos entre inicios de peticiones seguidas, para probar el gate."""
        starts = [entry["start"] for entry in self.log]
        return [round(b - a, 3) for a, b in zip(starts, starts[1:])]
