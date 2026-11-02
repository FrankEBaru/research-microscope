"""Descarga y parseo reanudables. Una máquina, una conexión.

La licencia no hace falta para construir. Solo se pide (OAI-PMH, una petición
más por paper con el mismo gate) con `license_lookup=True`
(`RRM_PASSAGES_LICENSE=1` en Modal). Apagada, `license` queda vacío.

Salta un corpusid que ya tiene filas o una falla anotada. Si el caché del
lector está `done` con fuente latex, no vuelve a bajar; si faltan filas,
las saca de paper.json. Un abstract_only no trae el cuerpo, así que sí se
baja. Sin arxiv id o sin TeX anota la falla y no inventa el pasaje.
"""

import json
import os
import time
from pathlib import Path

from rrm.passages.arxiv import ArxivHTTPError, ArxivStopped
from rrm.passages.cache import cached_paper, latex_cache_ready, store_reader_cache
from rrm.passages.rows import extract_rows
from rrm.passages.store import failure_dir, paper_dir, save_failure, save_paper_rows
from rrm.reader.fetch import unpack_eprint
from rrm.reader.latex import parse_tree
from rrm.reader.pipeline import load_meta


class StageBudget(RuntimeError):
    """La etapa llegó al tope de dólares y se detiene."""


def acquire_harvest_lock(dest, break_lock=False):
    path = Path(dest) / "harvest.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and not break_lock:
        raise RuntimeError("harvest.lock presente: una sola máquina, nunca en paralelo")
    if path.is_file():
        path.unlink()
    path.write_text(
        json.dumps({"pid": os.getpid(), "host": os.environ.get("HOSTNAME", "")}),
        encoding="utf-8",
    )
    return path


def release_harvest_lock(dest):
    path = Path(dest) / "harvest.lock"
    if path.is_file():
        path.unlink()


def _license(client, arxiv_id):
    """(licencia, motivo de falla). No se traga el error: el motivo va al resultado y al log."""
    try:
        return client.fetch_license(arxiv_id), None
    except ArxivStopped:
        raise
    except Exception as err:
        reason = _reason(err)
        print(f"licencia {arxiv_id}: {reason}", flush=True)
        return "", reason


def _reason(err) -> str:
    if isinstance(err, ArxivHTTPError):
        return err.reason
    text = str(err).strip() or type(err).__name__
    return text[:200]


def harvest_one(meta, *, client, papers_root, dest, retry=False, license_lookup=False):
    """Un paper. `meta` trae corpusid y, si se conoce, arxiv_id, título y licencia."""
    cid = int(meta["corpusid"])
    row_path = paper_dir(dest) / f"{cid}.json"
    fail_path = failure_dir(dest) / f"{cid}.json"
    if row_path.is_file() and not retry:
        return {"corpusid": cid, "skipped": True, "reason": "rows"}
    if fail_path.is_file() and not retry:
        return {"corpusid": cid, "skipped": True, "reason": "failed"}

    folder = Path(papers_root) / str(cid)
    arxiv_id = meta.get("arxiv_id") or ""
    license_url = meta.get("license") or ""
    license_error = None
    eprint = None
    downloaded = False
    if latex_cache_ready(folder):
        paper = cached_paper(folder)
        if not arxiv_id:
            arxiv_id = (paper or {}).get("arxivId") or ""
        if not license_url:
            # El caché viejo del lector no guarda licencia. Se pide a la API de
            # arXiv (misma conexión, mismo gate de 3.5 s); el e-print no se baja.
            license_url = (load_meta(folder) or {}).get("license") or (paper or {}).get("license") or ""
        if license_lookup and not license_url and arxiv_id:
            license_url, license_error = _license(client, arxiv_id)
    else:
        if not arxiv_id:
            save_failure(dest, cid, "sin arxiv id")
            return {"corpusid": cid, "skipped": False, "reason": "sin arxiv id", "rows": 0}
        if license_lookup and not license_url:
            license_url, license_error = _license(client, arxiv_id)
        started = time.time()
        try:
            blob = client.fetch_eprint(arxiv_id)
        except ArxivStopped:
            raise
        except Exception as err:
            reason = _reason(err)
            save_failure(dest, cid, reason)
            return {"corpusid": cid, "skipped": False, "reason": reason, "rows": 0,
                    "license": license_url, "license_error": license_error}
        downloaded = True
        eprint = {"bytes": len(blob or b""), "seconds": round(time.time() - started, 3)}
        kind = unpack_eprint(blob, folder / "src")
        if kind != "tex":
            save_failure(dest, cid, "sin TeX")
            return {"corpusid": cid, "skipped": False, "reason": "sin TeX", "rows": 0,
                    "eprint": eprint, "eprint_kind": kind, "license": license_url, "license_error": license_error}
        parsed = parse_tree(folder / "src", arxiv_id=arxiv_id)
        paper = parsed.get("paper") if parsed.get("route") == "latex" else None
        if not paper:
            reason = "sin TeX" if parsed.get("route") != "latex" else "parseo"
            detail = parsed.get("reason")
            if detail and reason == "parseo":
                reason = f"parseo: {detail}"[:200]
            save_failure(dest, cid, reason)
            return {"corpusid": cid, "skipped": False, "reason": reason, "rows": 0,
                    "eprint": eprint, "license": license_url, "license_error": license_error}
        paper["corpusid"] = cid
        paper["arxivId"] = arxiv_id
        store_reader_cache(folder, paper, license_url=license_url)

    if not paper:
        save_failure(dest, cid, "parseo")
        return {"corpusid": cid, "skipped": False, "reason": "parseo", "rows": 0}
    url = meta.get("url") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")
    filled = dict(meta)
    filled["arxiv_id"] = arxiv_id
    filled["license"] = license_url
    filled["url"] = url
    title = meta.get("title") or (paper or {}).get("title") or ""
    rows = extract_rows(paper, arxiv_id=arxiv_id, license=license_url, url=url, title=title)
    save_paper_rows(dest, filled, rows)
    by = {"eq": 0, "p": 0, "def": 0}
    for row in rows:
        by[row["kind"]] = by.get(row["kind"], 0) + 1
    return {
        "corpusid": cid,
        "skipped": False,
        "downloaded": downloaded,
        "reason": None,
        "rows": len(rows),
        "by_kind": by,
        "eq_with_refs": sum(1 for row in rows if row["kind"] == "eq" and row.get("ctx_refs")),
        "title": filled.get("title") or (paper or {}).get("title"),
        "arxiv_id": arxiv_id,
        "license": license_url,
        "license_error": license_error,
        "eprint": eprint,
    }


def harvest_ids(ids, metas, *, client, papers_root, dest, retry=False, break_lock=False, on_paper=None,
                license_lookup=False):
    """En serie. `metas` es un dict corpusid → metadata. Para al primer 429 repetido."""
    acquire_harvest_lock(dest, break_lock=break_lock)
    done = []
    try:
        for raw in ids or []:
            cid = int(raw)
            meta = dict((metas or {}).get(cid) or (metas or {}).get(str(cid)) or {"corpusid": cid})
            meta["corpusid"] = cid
            result = harvest_one(
                meta, client=client, papers_root=papers_root, dest=dest, retry=retry,
                license_lookup=license_lookup,
            )
            done.append(result)
            if on_paper:
                on_paper(result)
    finally:
        release_harvest_lock(dest)
    return done
