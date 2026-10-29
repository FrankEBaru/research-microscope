"""Resolve a corpus id and download the arXiv e-print or an open PDF.

arXiv: at most one request every 3 seconds, one shared clock per process
(the Modal app also serializes through a Dict). Semantic Scholar Graph API:
at most one request per second, exponential backoff on 429 and 5xx. No key.
"""

import gzip
import io
import tarfile
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


ARXIV = Limiter(3.2)
S2_LIMIT = Limiter(1.1)


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


def _get(url: str, limiter: Limiter, timeout=90) -> bytes:
    delay = 1.0
    last = None
    for _ in range(6):
        limiter.wait()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            last = err
            if err.code == 429 or err.code >= 500:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    raise RuntimeError(f"get failed: {url} ({last})")


def arxiv_eprint(arxiv_id: str) -> bytes:
    return _get(f"https://arxiv.org/e-print/{canon_arxiv(arxiv_id)}", ARXIV)


def arxiv_pdf(arxiv_id: str) -> bytes:
    return _get(f"https://arxiv.org/pdf/{canon_arxiv(arxiv_id)}.pdf", ARXIV)


def fetch_url(url: str) -> bytes:
    host_limiter = ARXIV if "arxiv.org" in url else S2_LIMIT
    return _get(url, host_limiter)


def s2_graph(corpusid: int) -> dict:
    """Free Graph API. Returns {} when the id is unknown."""
    import json
    url = f"{S2}CorpusId:{int(corpusid)}?fields={S2_FIELDS}"
    try:
        raw = _get(url, S2_LIMIT, timeout=30)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return {}
        raise
    data = json.loads(raw.decode("utf-8", "replace"))
    ext = data.get("externalIds") or {}
    oa = data.get("openAccessPdf") or {}
    tldr = data.get("tldr") or {}
    authors = [a.get("name") for a in (data.get("authors") or []) if a.get("name")]
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
