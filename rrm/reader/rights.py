"""Clase de licencia arXiv y compuerta del cuerpo. Puro, salvo la lectura del mapa."""

import copy
import json
import os
import re
from pathlib import Path

_NEW = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?$", re.I)
_OLD = re.compile(r"((?:[a-z-]+(?:\.[a-z]{2})?)/\d{7})(v\d+)?$", re.I)
_BY_SA = re.compile(r"\bcc[-\s]?by-sa\b", re.I)
_BY = re.compile(r"\bcc[-\s]?by\b", re.I)
_EMPTY = {"by_arxiv": {}, "by_corpus": {}}
_CACHE = {}
_DROP = (
    "figures", "images", "tables", "oaPdf", "pdf", "crops",
    "tex", "source_tex", "raw", "body", "sections", "paragraphs",
    "fulltext", "html", "markdown", "refs", "citeMap", "graphRefs",
)
_META_BITS = ("pdf", "path", "file", "tex", "figure", "crop", "eprint")


_GATE_OFF = {"0", "off", "false", "no"}


def gate_on():
    """Compuerta activa salvo RRM_LICENSE_GATE=off (también 0, false, no).

    Sin la variable sigue activa: el demo la apaga en scripts/run.sh.
    """
    raw = os.environ.get("RRM_LICENSE_GATE")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() not in _GATE_OFF


def fixture_render(row):
    """Full text for one offline fixture row. Live does not set RRM_LICENSE_FIXTURE.

    The license class stays whatever the URL says. This only skips the body
    strip, and only for a row that itself says fixture_open.
    """
    return bool(row and row.get("fixture_open")) and os.environ.get("RRM_LICENSE_FIXTURE") == "1"


def license_class(url):
    """open o closed. Vacío, desconocido, ND, NC y la default de arXiv son closed."""
    raw = (url or "").strip().lower()
    if not raw or "nonexclusive-distrib" in raw:
        return "closed"
    if "cc0" in raw or "publicdomain/zero" in raw or "licenses/publicdomain/" in raw:
        return "open"
    if "by-nc" in raw or "by-nd" in raw:
        return "closed"
    if "creativecommons.org/licenses/by-sa/" in raw or _BY_SA.search(raw):
        return "open"
    if "creativecommons.org/licenses/by/" in raw or _BY.search(raw):
        return "open"
    return "closed"


def share_alike(url):
    if license_class(url) != "open":
        return False
    raw = (url or "").lower()
    return "creativecommons.org/licenses/by-sa/" in raw or bool(_BY_SA.search(raw))


def _ver_num(raw):
    match = re.search(r"(\d+\.\d+)", raw or "")
    return match.group(1) if match else ""


def license_label(url):
    raw = (url or "").strip()
    low = raw.lower()
    if not low:
        return "License unknown"
    if "nonexclusive-distrib" in low:
        return "arXiv license"
    ver = _ver_num(low)
    named = (lambda name: f"{name} {ver}".strip() if ver else name)
    for needle, name in (("by-nc-nd", "CC BY-NC-ND"), ("by-nc-sa", "CC BY-NC-SA"), ("by-nd", "CC BY-ND"), ("by-nc", "CC BY-NC"), ("by-sa", "CC BY-SA")):
        if needle in low:
            return named(name)
    if "publicdomain/zero" in low or re.search(r"\bcc0\b", low):
        return named("CC0") if ver else "CC0 1.0"
    if "licenses/publicdomain/" in low:
        return "Public domain"
    if license_class(raw) == "open":
        return named("CC BY")
    return "License unknown"


def split_arxiv(raw):
    text = re.sub(r"^arxiv:", "", str(raw or "").strip(), flags=re.I)
    text = text.split("abs/")[-1].strip()
    match = _NEW.search(text) or _OLD.search(text)
    if not match:
        return "", ""
    return match.group(1), (match.group(2) or "").lower()


def _norm_ver(raw):
    if raw is None or raw == "":
        return ""
    text = str(raw).strip()
    if text.isdigit():
        return "v" + text
    if len(text) > 1 and text[0] in "vV" and text[1:].isdigit():
        return "v" + text[1:]
    return text


def _cid(raw):
    if raw is None or raw == "":
        return ""
    text = str(raw).strip()
    if text.lstrip("-").isdigit():
        return str(int(text))
    return text


def map_path(root=None):
    """RRM_LICENSE_MAP, si no el directorio offline, si no /data/licenses.json."""
    env = (os.environ.get("RRM_LICENSE_MAP") or "").strip()
    if env:
        return env
    if root:
        return str(Path(root) / "licenses.json")
    data = Path("/data/licenses.json")
    return str(data) if data.is_file() else ""


def _index(data):
    by_arxiv, by_corpus = {}, {}
    if not isinstance(data, dict):
        return {"by_arxiv": by_arxiv, "by_corpus": by_corpus}
    for key, val in data.items():
        if str(key).startswith("_") or not isinstance(val, dict):
            continue
        base, _in_key = split_arxiv(key)
        row = {
            "license": val.get("license") or "",
            "version": _norm_ver(val.get("version")),
            "corpusid": val.get("corpusid"),
            "arxiv": base,
            # Ignored unless RRM_LICENSE_FIXTURE=1. Live never sets that env.
            "fixture_open": val.get("fixture_open") is True,
        }
        if base:
            by_arxiv[base] = row
        cid = _cid(val.get("corpusid"))
        if cid:
            by_corpus[cid] = row
    return {"by_arxiv": by_arxiv, "by_corpus": by_corpus}


def load_map(path):
    """Índice por arXiv id (sin vN) y por corpusid. Sin archivo → mapa vacío."""
    if not path:
        return _EMPTY
    file = Path(path)
    try:
        st = file.stat()
    except OSError:
        return _EMPTY
    if not file.is_file():
        return _EMPTY
    key = str(file.resolve())
    hit = _CACHE.get(key)
    if hit and hit[0] == st.st_mtime_ns:
        return hit[1]
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _EMPTY
    built = _index(data)
    _CACHE[key] = (st.st_mtime_ns, built)
    return built


def map_size(m):
    """Papers indexed by arXiv id, by corpusid, or by both."""
    if not isinstance(m, dict):
        return 0
    rows = list((m.get("by_arxiv") or {}).values()) + list((m.get("by_corpus") or {}).values())
    return len({id(row) for row in rows})


def warn_map(path, m):
    """Print when the map is missing, unreadable, or empty. Returns the count."""
    n = map_size(m)
    if n:
        return n
    where = path or "no licenses.json"
    print(f"WARNING: license map missing or unreadable ({where}); every paper is treated as closed", flush=True)
    return 0


def _ident(src):
    if isinstance(src, dict):
        paper = src["paper"] if isinstance(src.get("paper"), dict) else src
        meta = src["meta"] if isinstance(src.get("meta"), dict) else {}
        arxiv = paper.get("arxivId") or paper.get("arxiv") or meta.get("arxiv") or ""
        cid = paper.get("corpusid")
        if cid is None:
            cid = meta.get("corpusid")
        if cid is None:
            cid = src.get("id")
        return str(arxiv or ""), cid
    if isinstance(src, int) or (isinstance(src, str) and str(src).strip().lstrip("-").isdigit()):
        return "", int(str(src).strip())
    return str(src or ""), None


def rights_for(paper_or_ids, m):
    arxiv, cid = _ident(paper_or_ids)
    base, in_id = split_arxiv(arxiv)
    index = m or _EMPTY
    row = index["by_arxiv"].get(base) if base else None
    if row is None:
        key = _cid(cid)
        row = index["by_corpus"].get(key) if key else None
    url = (row or {}).get("license") or ""
    if row is None:
        url = ""
    version = (row or {}).get("version") or _norm_ver(in_id)
    ax = (row or {}).get("arxiv") or base
    cls = license_class(url) if row is not None else "closed"
    fixture = fixture_render(row)
    return {
        "license": url,
        "url": url,
        "label": license_label(url) if url else "License unknown",
        "cls": cls,
        "sa": bool(url) and share_alike(url),
        "version": version,
        "arxiv": ax,
        "fixture": fixture,
        "gated": cls == "closed" and gate_on() and not fixture,
    }


def _strip(paper, meta):
    blocks = paper.get("blocks") if isinstance(paper.get("blocks"), list) else []
    paper["blocks"] = [b for b in blocks if isinstance(b, dict) and b.get("abs") is True]
    paper["full"] = False
    for key in _DROP:
        paper.pop(key, None)
    if isinstance(meta, dict):
        for key in list(meta):
            low = str(key).lower()
            if any(bit in low for bit in _META_BITS):
                meta.pop(key, None)


def gate_paper_response(resp, m):
    """Añade paper.rights. Con compuerta, el cerrado conserva solo el abstract."""
    if not isinstance(resp, dict) or not isinstance(resp.get("paper"), dict):
        return resp
    out = copy.deepcopy(resp)
    rights = rights_for(out, m)
    out["paper"]["rights"] = rights
    if rights["gated"]:
        meta = out.get("meta") if isinstance(out.get("meta"), dict) else None
        _strip(out["paper"], meta)
    return out


def gate_status_row(row, m):
    if not isinstance(row, dict):
        return row
    out = dict(row)
    rights = rights_for(out, m)
    out["license"] = rights["label"]
    out["gated"] = rights["gated"]
    if rights["gated"]:
        out["text"] = False
    return out


def gate_file(cid, m):
    """True si /file y /crops deben negarse."""
    return bool(rights_for(cid, m)["gated"])


def clip_text(text, limit=300):
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    window = flat[:limit]
    end = -1
    for i, ch in enumerate(window):
        if ch in ".!?" and (i + 1 == len(window) or window[i + 1] == " "):
            end = i
    if end >= 40:
        return window[: end + 1]
    cut = window.rsplit(" ", 1)[0] if " " in window else window
    return cut[: limit - 1].rstrip() + "…"


def gate_ask(payload, m):
    """Recorta el extracto de un paper cerrado. Con la compuerta apagada, no cambia nada."""
    if not gate_on() or not isinstance(payload, dict):
        return payload
    extracts = payload.get("extracts")
    if not isinstance(extracts, list):
        return payload
    gated = [isinstance(ex, dict) and rights_for(ex.get("paper"), m)["gated"] for ex in extracts]
    if not any(gated):
        return payload
    out = copy.deepcopy(payload)
    for ex, closed in zip(out.get("extracts") or [], gated):
        if not closed or not isinstance(ex, dict):
            continue
        rights = rights_for(ex.get("paper"), m)
        ex["text"] = clip_text(ex.get("text") or "")
        ex.pop("contexts", None)
        ex["license"] = rights["label"]
        ex["arxiv"] = rights["arxiv"]
    return out
