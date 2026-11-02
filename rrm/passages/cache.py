"""Caché del lector para un paper ya parseado.

Escribe el mismo par que `parse_corpus` da por bueno: `meta.json` con status
`done` y `paper.json` con el esquema de bloques. También `phrases.json`,
porque el lector lo escribe en `_store_phrases`. No llama a BurstGate, no
hace OCR y no renderiza figuras: el e-print queda en `src/` y las figuras
quedan en `skipped`.
"""

from pathlib import Path

from rrm.reader.latex import stats
from rrm.reader.phrases import write_phrases
from rrm.reader.pipeline import _blank_timings, blank_stages, load_meta, load_paper, save_meta, save_paper


def reader_cache_ready(folder) -> bool:
    """La misma condición que `parse_corpus`: done o abstract_only, y paper.json."""
    folder = Path(folder)
    meta = load_meta(folder)
    return bool(
        meta
        and meta.get("status") in ("done", "abstract_only")
        and (folder / "paper.json").is_file()
    )


def latex_cache_ready(folder) -> bool:
    """Caché `done` con fuente latex. Un abstract_only no trae el cuerpo, así que se vuelve a bajar."""
    folder = Path(folder)
    meta = load_meta(folder)
    return bool(
        meta
        and meta.get("status") == "done"
        and meta.get("source") == "latex"
        and (folder / "paper.json").is_file()
    )


def store_reader_cache(folder, paper, *, timings=None, license_url=""):
    """Guarda el paper con las funciones del lector. Devuelve el meta escrito."""
    folder = Path(folder)
    paper = dict(paper)
    stages = blank_stages()
    stages["stub"] = "done"
    stages["sections"] = "done"
    stages["figures"] = "skipped"
    paper["status"] = "done"
    paper["stage"] = "done"
    paper["stages"] = stages
    save_paper(folder, paper)
    write_phrases(folder, paper)
    meta = {
        "corpusid": int(paper["corpusid"]),
        "status": "done",
        "stage": "done",
        "stages": stages,
        "reason": None,
        "source": paper.get("source") or "latex",
        "timings": timings or _blank_timings(),
        "arxiv": paper.get("arxivId") or "",
        "title": paper.get("title") or "",
        "license": license_url or paper.get("license") or "",
    }
    meta.update(stats(paper))
    save_meta(folder, meta)
    return meta


def cached_paper(folder):
    folder = Path(folder)
    if not reader_cache_ready(folder):
        return None
    return load_paper(folder)
