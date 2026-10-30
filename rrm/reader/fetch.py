"""Resolve a corpus id and download the arXiv e-print or an open PDF.

arXiv e-prints come from export.arxiv.org, the host arXiv documents for
programmatic harvest (info.arxiv.org/help/bulk_data): bursts of 4 requests
in one second, then a 1 second sleep. The gate covers only the request start,
not the transfer, so one slow download does not hold the others. The S3
requester-pays bucket is not used; a single paper is packed into a ~500 MB
month tar and the requester pays for that whole object. The Modal app shares
one clock across containers. Open-access PDF hosts have no shared gate.
Semantic Scholar Graph API: at most one request per second, exponential
backoff on 429 and 5xx. Optional env S2_API_KEY is sent as x-api-key.
"""

import gzip
import io
import os
import tarfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "research-microscope-reader/0.1 (student prototype; contact via GitHub FrankEBaru)"
S2 = "https://api.semanticscholar.org/graph/v1/paper/"
S2_FIELDS = "title,abstract,tldr,externalIds,openAccessPdf,year,authors,isOpenAccess"


class Limiter:
    def __init__(self, interval, sleep=time.sleep, now=time.time):
        self.interval = interval
        self.sleep = sleep
        self.now = now
        self.next = 0.0

    def wait(self):
        delay = self.next - self.now()
        if delay > 0:
            self.sleep(delay)
        self.next = self.now() + self.interval


# 4 requests spread across 1 second, then a 1 second sleep, per arXiv's harvest note.
ARXIV_BURST = 4
ARXIV_BURST_SPAN = 1.0
ARXIV_BURST_GAP = 1.0
ARXIV_HOST = "https://export.arxiv.org"


def arxiv_slot_start(index: int) -> float:
    """Seconds from the epoch when slot `index` may start."""
    burst, pos = divmod(int(index), ARXIV_BURST)
    within = ARXIV_BURST_SPAN / ARXIV_BURST
    return burst * (ARXIV_BURST_SPAN + ARXIV_BURST_GAP) + pos * within


def arxiv_index_at(now: float) -> int:
    """Smallest slot index whose start is at or after `now`."""
    if now <= 0:
        return 0
    period = ARXIV_BURST_SPAN + ARXIV_BURST_GAP
    burst = int(now // period)
    base = burst * ARXIV_BURST
    for i in range(base, base + ARXIV_BURST + 1):
        if arxiv_slot_start(i) >= now - 1e-6:
            return i
    return base + ARXIV_BURST


class BurstGate:
    """Per-process burst clock. Modal replaces `wait` with the shared Dict gate."""

    def __init__(self, sleep=time.sleep, now=time.time):
        self.sleep = sleep
        self.now = now
        self.next_index = None

    def wait(self):
        now = self.now()
        if self.next_index is None or arxiv_slot_start(self.next_index) < now:
            self.next_index = arxiv_index_at(now)
        slot = self.next_index
        self.next_index += 1
        delay = arxiv_slot_start(slot) - self.now()
        if delay > 0:
            self.sleep(delay)


ARXIV = BurstGate()
S2_LIMIT = Limiter(1.1)

# Per-download budget for e-prints and PDFs. A stalled read falls back to the next source.
PDF_CONNECT_S = 10
PDF_TOTAL_S = 30
PDF_MAX_BYTES = 50 * 1024 * 1024


class DownloadError(Exception):
    def __init__(self, reason: str = "download failed"):
        super().__init__(reason)
        self.reason = reason
        self.timings = []


def _s2_key_header() -> dict:
    key = os.environ.get("S2_API_KEY", "").strip()
    if not key:
        return {}
    return {"x-api-key": key}


def canon_arxiv(text) -> str:
    if not text:
        return ""
    text = str(text).strip()
    lower = text.lower()
    if lower.startswith("arxiv:"):
        text = text.split(":", 1)[1].strip()
    if len(text) > 1 and text[-1].isdigit() is False:
        pass
    # drop a trailing version marker vN
    import re
    return re.sub(r"v\d+$", "", text).strip()


def _get(url: str, limiter: Limiter, timeout=90, tries: int = 6) -> bytes:
    delay = 1.0
    last = None
    attempts = max(1, int(tries))
    for attempt in range(attempts):
        limiter.wait()
        headers = {"User-Agent": UA}
        if "semanticscholar.org" in url:
            headers.update(_s2_key_header())
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            last = err
            retry = err.code == 429 or err.code >= 500
            if retry and attempt + 1 < attempts:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    raise RuntimeError(f"get failed: {url} ({last})")


def _download_reason(err: Exception) -> str:
    if isinstance(err, DownloadError):
        return err.reason
    if isinstance(err, urllib.error.HTTPError):
        return f"http {err.code}"
    text = str(err).strip() or type(err).__name__
    if isinstance(err, TimeoutError) or "timed out" in text.lower():
        return "timeout"
    return text[:200]


def _arm_socket_timeout(resp, seconds: float):
    fp = getattr(resp, "fp", None)
    raw = getattr(fp, "raw", None) if fp is not None else None
    sock = None
    if raw is not None:
        sock = getattr(raw, "_sock", None) or getattr(raw, "sock", None)
    if sock is None and fp is not None:
        sock = getattr(fp, "_sock", None)
    if sock is None:
        return
    try:
        sock.settimeout(max(0.1, float(seconds)))
    except OSError:
        pass


def _read_capped(resp, deadline: float, max_bytes: int, now, cancel) -> bytes:
    parts = []
    got = 0
    while True:
        if cancel is not None and cancel():
            raise DownloadError("cancelled")
        left = deadline - now()
        if left <= 0:
            raise DownloadError("download exceeded 30s")
        _arm_socket_timeout(resp, left)
        try:
            chunk = resp.read(65536)
        except Exception as err:
            if cancel is not None and cancel():
                raise DownloadError("cancelled") from err
            reason = _download_reason(err)
            if reason == "timeout" or isinstance(err, TimeoutError):
                raise DownloadError("download exceeded 30s") from err
            raise DownloadError(reason) from err
        if now() >= deadline:
            raise DownloadError("download exceeded 30s")
        if not chunk:
            break
        got += len(chunk)
        if got > max_bytes:
            raise DownloadError("download exceeded 50MB")
        parts.append(chunk)
    return b"".join(parts)


def download_url(
    url: str,
    limiter=None,
    *,
    opener=None,
    now=None,
    connect_timeout: float = PDF_CONNECT_S,
    total_timeout: float = PDF_TOTAL_S,
    max_bytes: int = PDF_MAX_BYTES,
    cancel=None,
) -> bytes:
    """GET `url`. The limiter runs only before the socket opens, never during the body."""
    now = now or time.time
    if limiter is not None:
        limiter.wait()
    if cancel is not None and cancel():
        raise DownloadError("cancelled")
    deadline = now() + float(total_timeout)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    open_fn = opener or urllib.request.urlopen
    try:
        resp = open_fn(req, timeout=connect_timeout)
    except DownloadError:
        raise
    except Exception as err:
        raise DownloadError(_download_reason(err)) from err
    try:
        return _read_capped(resp, deadline, int(max_bytes), now, cancel)
    finally:
        close = getattr(resp, "close", None)
        if close:
            try:
                close()
            except Exception:
                pass


def valid_pdf(blob: bytes) -> bool:
    return bool(blob) and len(blob) >= 8 and blob[:4] == b"%PDF"


def race_pdf_bytes(jobs: list, note=None, stop: threading.Event | None = None) -> dict:
    """Start every fetch and return the first valid PDF. The rest are cancelled.

    `jobs` is a list of (source, fn). fn returns bytes or raises.
    Result: {source, data, seconds, timings}. DownloadError carries `.timings` when none win.
    """
    if not jobs:
        raise DownloadError("no pdf source")
    stop = stop or threading.Event()
    timings = []
    lock = threading.Lock()
    winner = {}

    def record(row):
        with lock:
            timings.append(row)
        if note:
            note(dict(row))

    def run(name, fn):
        t0 = time.time()
        try:
            if stop.is_set():
                record({"source": name, "seconds": 0.0, "ok": False, "reason": "cancelled"})
                return
            data = fn()
            seconds = round(time.time() - t0, 3)
            if valid_pdf(data):
                record({"source": name, "seconds": seconds, "ok": True, "bytes": len(data)})
                with lock:
                    if "data" not in winner:
                        winner["source"] = name
                        winner["data"] = data
                        winner["seconds"] = seconds
                        stop.set()
            else:
                record({"source": name, "seconds": seconds, "ok": False, "reason": "not a pdf"})
        except Exception as err:
            seconds = round(time.time() - t0, 3)
            reason = err.reason if isinstance(err, DownloadError) else str(err)[:200]
            record({"source": name, "seconds": seconds, "ok": False, "reason": str(reason)[:200]})

    threads = [threading.Thread(target=run, args=(name, fn), daemon=True) for name, fn in jobs]
    for thread in threads:
        thread.start()
    while not stop.is_set() and any(thread.is_alive() for thread in threads):
        stop.wait(0.02)
    for thread in threads:
        thread.join(timeout=0.05 if stop.is_set() else 5)
    if "data" not in winner:
        reason = "; ".join(
            f"{row['source']}: {row.get('reason') or 'failed'}" for row in timings
        ) or "no pdf"
        err = DownloadError(reason)
        err.timings = list(timings)
        raise err
    winner["timings"] = timings
    return winner


def arxiv_eprint(arxiv_id: str, cancel=None) -> bytes:
    return download_url(f"{ARXIV_HOST}/e-print/{canon_arxiv(arxiv_id)}", ARXIV, cancel=cancel)


def arxiv_pdf(arxiv_id: str, cancel=None) -> bytes:
    return download_url(f"{ARXIV_HOST}/pdf/{canon_arxiv(arxiv_id)}.pdf", ARXIV, cancel=cancel)


def fetch_pdf(url: str, cancel=None) -> bytes:
    """Open PDF. arXiv hosts take a harvest slot; every other host runs with no shared gate."""
    limiter = ARXIV if "arxiv.org" in url else None
    return download_url(url, limiter, cancel=cancel)


def fetch_url(url: str) -> bytes:
    return fetch_pdf(url)


# Set by the Modal app to the papers root. s2_graph reads papers/{id}/s2.json first;
# s2_batch writes it for a whole burst in one request, so 10 parallel parses do not
# each hit the free Graph API (QA 2026-10-29: 429 backoff made the stub take ~65 s).
S2_CACHE_DIR = None


def _s2_cache(corpusid: int):
    if S2_CACHE_DIR is None:
        return None
    return Path(S2_CACHE_DIR) / str(int(corpusid)) / "s2.json"


def s2_batch(corpusids) -> dict:
    """One POST /paper/batch for many ids. Writes each hit to the s2.json cache. Never raises."""
    import json
    ids = [int(c) for c in corpusids or []]
    todo = [c for c in ids if not ((_s2_cache(c) or Path("/nonexistent")).is_file())]
    if not todo:
        return {}
    body = json.dumps({"ids": [f"CorpusId:{c}" for c in todo]}).encode()
    out = {}
    delay = 1.0
    for _ in range(3):
        S2_LIMIT.wait()
        headers = {"User-Agent": UA, "Content-Type": "application/json"}
        headers.update(_s2_key_header())
        req = urllib.request.Request(
            f"{S2}batch?fields={S2_FIELDS}", data=body,
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = json.loads(resp.read().decode("utf-8", "replace"))
            break
        except Exception:
            time.sleep(delay)
            delay *= 2
    else:
        return {}
    for cid, data in zip(todo, rows or []):
        if not isinstance(data, dict):
            continue
        out[cid] = data
        path = _s2_cache(cid)
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")
            except OSError:
                pass
    return out


def s2_graph(corpusid: int, tries: int = 1) -> dict:
    """Graph API (or the s2.json cache). `tries` defaults to 1 so a stub does not wait on backoff."""
    import json
    data = None
    path = _s2_cache(corpusid)
    if path is not None and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
    if data is None:
        url = f"{S2}CorpusId:{int(corpusid)}?fields={S2_FIELDS}"
        try:
            raw = _get(url, S2_LIMIT, timeout=10, tries=max(1, int(tries)))
        except urllib.error.HTTPError as err:
            if err.code == 404:
                return {}
            raise
        data = json.loads(raw.decode("utf-8", "replace"))
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")
            except OSError:
                pass
    ext = data.get("externalIds") or {}
    oa = data.get("openAccessPdf") or {}
    tldr = data.get("tldr") or {}
    authors = _author_names(data.get("authors"))
    return {
        "corpusid": int(corpusid),
        "title": data.get("title") or "",
        "abstract": data.get("abstract") or "",
        "tldr": (tldr.get("text") if isinstance(tldr, dict) else None) or "",
        "arxiv": canon_arxiv(ext.get("ArXiv") or ""),
        "doi": (ext.get("DOI") or "") or "",
        "oa_pdf": (oa.get("url") if isinstance(oa, dict) else "") or "",
        "year": data.get("year"),
        "authors": authors,
        "is_open_access": data.get("isOpenAccess"),
    }


def merge_s2(info: dict, remote: dict) -> dict:
    """Copy Semantic Scholar fields onto `info`. Authors from S2 win when the response has any."""
    if not remote:
        return info
    if remote.get("authors"):
        info["authors"] = list(remote["authors"])
    for key in ("abstract", "tldr", "title", "arxiv", "doi", "oa_pdf", "year", "is_open_access"):
        value = remote.get(key)
        if value not in (None, "", []) and not info.get(key):
            info[key] = value
    return info


def _display_row(path: Path, corpusid: int) -> dict | None:
    """Read only the row group whose corpusid range holds the id (file is sorted). None if not found."""
    import pyarrow.parquet as pq
    cols = ["corpusid", "title", "arxiv", "doi", "tldr"]
    pf = pq.ParquetFile(path)
    names = pf.schema_arrow.names
    cols = [c for c in cols if c in names]
    ci = names.index("corpusid")
    cid = int(corpusid)
    for rg in range(pf.metadata.num_row_groups):
        st = pf.metadata.row_group(rg).column(ci).statistics
        if st is None or not st.has_min_max:
            return None
        if st.min <= cid <= st.max:
            t = pf.read_row_group(rg, columns=cols)
            ids = t.column("corpusid").to_pylist()
            for i, v in enumerate(ids):
                if v == cid:
                    return {name: t.column(name)[i].as_py() for name in cols}
            return {}
    return {}


def lookup_display(path: Path, corpusid: int) -> dict:
    """Sorted display.parquet (corpusid, title, arxiv, doi, tldr). Missing file or id -> {}.

    Reads one row group by corpusid statistics; the full file is 2.6 GB, so a full read took 14 s.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    cid = int(corpusid)
    row = _display_row(path, cid)
    if row is None:
        import pyarrow.parquet as pq
        table = pq.read_table(path, columns=["corpusid", "title", "arxiv", "doi", "tldr"])
        ids = table.column("corpusid").fill_null(-1).to_pylist()
        lo, hi = 0, len(ids)
        while lo < hi:
            mid = (lo + hi) // 2
            if ids[mid] < cid:
                lo = mid + 1
            else:
                hi = mid
        if lo >= len(ids) or ids[lo] != cid:
            return {}
        row = {name: table.column(name)[lo].as_py() for name in table.column_names}
    if not row:
        return {}
    return {
        "corpusid": cid,
        "title": row.get("title") or "",
        "arxiv": canon_arxiv(row.get("arxiv") or ""),
        "doi": row.get("doi") or "",
        "tldr": row.get("tldr") or "",
        "abstract": "",
        "oa_pdf": "",
        "authors": [],
        "year": None,
        "is_open_access": None,
    }


def resolve_identity(corpusid: int, display_path: Path | None = None) -> dict:
    """Volume display row first. Graph API fills gaps (no arXiv id, or no OA url when there is no arXiv id)."""
    info = lookup_display(display_path, corpusid) if display_path else {}
    info.setdefault("corpusid", int(corpusid))
    if info.get("arxiv"):
        return info
    remote = s2_graph(corpusid)
    if not info:
        return remote
    for key, value in remote.items():
        if value and not info.get(key):
            info[key] = value
    return info


def _safe_extract(tf: tarfile.TarFile, dest: Path):
    dest = dest.resolve()
    for member in tf.getmembers():
        if member.issym() or member.islnk() or member.isdir():
            continue
        name = member.name
        if name.startswith("/") or ".." in Path(name).parts:
            continue
        target = (dest / name).resolve()
        if not str(target).startswith(str(dest)):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        src = tf.extractfile(member)
        if src is None:
            continue
        target.write_bytes(src.read())


def unpack_eprint(blob: bytes, dest: Path) -> str:
    """Write an e-print into dest. Return 'pdf' or 'tex'."""
    dest.mkdir(parents=True, exist_ok=True)
    if blob[:4] == b"%PDF":
        (dest / "source.pdf").write_bytes(blob)
        return "pdf"
    raw = blob
    if blob[:2] == b"\x1f\x8b":
        try:
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
                _safe_extract(tf, dest)
            if any(dest.rglob("*.tex")):
                return "tex"
            if any(dest.rglob("*.pdf")):
                return "pdf"
        except tarfile.ReadError:
            pass
        raw = gzip.decompress(blob)
    if raw[:4] == b"%PDF":
        (dest / "source.pdf").write_bytes(raw)
        return "pdf"
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tf:
            _safe_extract(tf, dest)
        if any(dest.rglob("*.tex")):
            return "tex"
    except tarfile.ReadError:
        pass
    text = raw.decode("utf-8", "replace")
    if "\\documentclass" in text or text.strip().startswith("%"):
        (dest / "main.tex").write_text(text, encoding="utf-8")
        return "tex"
    (dest / "source.bin").write_bytes(raw)
    return "pdf" if raw[:4] == b"%PDF" else "unknown"


def _author_names(value) -> list:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict):
            name = (item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            names.append(name)
    return names


def _parquet_row(path: Path, corpusid: int, columns: list[str]) -> dict | None:
    """One row whose corpusid matches, using row-group min/max so other groups are not read."""
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    names = pf.schema_arrow.names
    if "corpusid" not in names:
        return None
    cols = [c for c in columns if c in names]
    if "corpusid" not in cols:
        cols = ["corpusid", *cols]
    ci = names.index("corpusid")
    cid = int(corpusid)
    for rg in range(pf.metadata.num_row_groups):
        st = pf.metadata.row_group(rg).column(ci).statistics
        if st is not None and st.has_min_max and not (st.min <= cid <= st.max):
            continue
        table = pf.read_row_group(rg, columns=cols)
        ids = table.column("corpusid").to_pylist()
        for i, value in enumerate(ids):
            if value == cid:
                return {name: table.column(name)[i].as_py() for name in table.column_names}
    return None


def _scan_dataset(directory: Path, corpusid: int, columns: list[str], limit_files: int = 80) -> dict:
    if not directory.is_dir():
        return {}
    files = sorted(directory.glob("*.parquet"))[:limit_files]
    for path in files:
        try:
            row = _parquet_row(path, corpusid, columns)
        except Exception:
            continue
        if row:
            return row
    return {}


def graph_reference_map(index_dir: Path, corpusid: int, limit: int = 30) -> dict:
    """Cited corpus ids from the CS citation graph on the volume. Empty when the graph is absent."""
    index_dir = Path(index_dir)
    ids_path = index_dir / "graph_ids.npy"
    indptr_path = index_dir / "out_indptr.npy"
    indices_path = index_dir / "out_indices.npy"
    if not (ids_path.is_file() and indptr_path.is_file() and indices_path.is_file()):
        return {}
    import numpy as np

    ids = np.load(ids_path, mmap_mode="r")
    pos = int(np.searchsorted(ids, int(corpusid)))
    if pos >= len(ids) or int(ids[pos]) != int(corpusid):
        return {}
    indptr = np.load(indptr_path, mmap_mode="r")
    indices = np.load(indices_path, mmap_mode="r")
    start, end = int(indptr[pos]), int(indptr[pos + 1])
    cited = []
    for local in indices[start:end]:
        cited.append(int(ids[int(local)]))
        if len(cited) >= limit:
            break
    return {f"s2:{cid}": f"Semantic Scholar corpus {cid}" for cid in cited}


def s2_reference_map(corpusid: int, limit: int = 40) -> dict:
    """Graph API references. Used when the volume graph has no row for this id."""
    import json

    url = (
        f"{S2}CorpusId:{int(corpusid)}/references"
        f"?fields=title,year,authors,corpusId&limit={int(limit)}"
    )
    raw = _get(url, S2_LIMIT, timeout=30)
    data = json.loads(raw.decode("utf-8", "replace"))
    refs = {}
    for item in data.get("data") or []:
        cited = item.get("citedPaper") or {}
        cid = cited.get("corpusId") or ""
        authors = [a.get("name") for a in (cited.get("authors") or []) if isinstance(a, dict) and a.get("name")]
        bits = [", ".join(authors[:3]), str(cited.get("year") or ""), cited.get("title") or ""]
        text = ". ".join(bit for bit in bits if bit)
        if not text:
            continue
        key = f"s2:{cid}" if cid else f"s2ref:{len(refs)}"
        refs[key] = text
    return refs


def _release_root(display_path: Path | None) -> Path | None:
    if not display_path:
        return None
    path = Path(display_path)
    # papers/{release}/index/display.parquet -> the release directory holds papers/ and abstracts/
    if path.name == "display.parquet" and path.parent.name == "index":
        return path.parent.parent
    return path.parent


def reader_identity(
    corpusid: int,
    display_path: Path | None = None,
    *,
    remote: bool = True,
    refs: bool = True,
    shards: bool = True,
) -> dict:
    """Title and tldr from display.parquet. Authors and abstract from the papers and abstracts
    shards on the same release when `shards` is set. One Graph API call only for fields still
    missing. The open request skips the shard scan (`shards=False`) so it stays on the display
    row plus at most one Graph API call.
    """
    cid = int(corpusid)
    info = {"corpusid": cid}
    if display_path and Path(display_path).is_file():
        found = lookup_display(display_path, cid)
        for key, value in found.items():
            if value not in (None, "", []):
                info[key] = value
        info["corpusid"] = cid
    root = _release_root(display_path)
    if shards and root is not None:
        if not info.get("authors"):
            row = _scan_dataset(root / "papers", cid, ["authors", "title", "year"])
            names = _author_names(row.get("authors"))
            if names:
                info["authors"] = names
            if row.get("title") and not info.get("title"):
                info["title"] = row["title"]
            if row.get("year") and not info.get("year"):
                info["year"] = row["year"]
        if not (info.get("abstract") or "").strip():
            row = _scan_dataset(root / "abstracts", cid, ["abstract"])
            if row.get("abstract"):
                info["abstract"] = row["abstract"]
        if refs and not info.get("refs"):
            info["refs"] = graph_reference_map(root / "index", cid)
    elif refs and root is not None and not info.get("refs"):
        info["refs"] = graph_reference_map(root / "index", cid)
    missing_text = (
        not info.get("arxiv")
        or not info.get("authors")
        or not (info.get("abstract") or "").strip()
    )
    if remote and missing_text:
        try:
            remote_info = s2_graph(cid)
        except Exception:
            remote_info = {}
        for key, value in remote_info.items():
            if value and not info.get(key):
                info[key] = value
    if remote and refs and not info.get("refs"):
        try:
            info["refs"] = s2_reference_map(cid)
        except Exception:
            info.setdefault("refs", {})
    info.setdefault("authors", [])
    info.setdefault("abstract", "")
    info.setdefault("tldr", info.get("tldr") or "")
    info.setdefault("refs", {})
    return info
