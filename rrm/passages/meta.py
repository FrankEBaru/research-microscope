"""Metadata por corpusid desde display.parquet (CS) o display_ext.parquet.

Ninguna de las dos tablas trae autores. Sin un lookup aparte, authors queda
vacío. display_ext no trae arxiv id: sin id no hay e-print y el paper aporta
cero filas.
"""

from pathlib import Path

import numpy as np

from rrm.search.display import canon_arxiv


def lookup_table(table, corpusid):
    """Una fila de una tabla ordenada por corpusid. None si no está."""
    if table is None or getattr(table, "num_rows", 0) == 0:
        return None
    ids = np.asarray(table.column("corpusid").to_numpy(zero_copy_only=False), dtype=np.int64)
    cid = int(corpusid)
    at = int(np.searchsorted(ids, cid))
    if at >= ids.size or int(ids[at]) != cid:
        return None
    row = {"corpusid": cid}
    for name in table.column_names:
        if name == "corpusid":
            continue
        row[name] = table.column(name)[at].as_py()
    return row


def abs_url(arxiv_id):
    arxiv_id = canon_arxiv(arxiv_id or "")
    if not arxiv_id:
        return ""
    return f"https://arxiv.org/abs/{arxiv_id}"


def _pack(corpusid, base, source, *, has_emb, arxiv_lookup, authors_lookup):
    base = base or {}
    arxiv_id = canon_arxiv(base.get("arxiv") or "")
    if not arxiv_id and arxiv_lookup is not None:
        arxiv_id = canon_arxiv(arxiv_lookup(int(corpusid)) or "")
    authors = list(base.get("authors") or [])
    if not authors and authors_lookup is not None:
        authors = list(authors_lookup(int(corpusid)) or [])
    count = base.get("citationcount")
    return {
        "corpusid": int(corpusid),
        "table": source,
        "title": base.get("title"),
        "year": base.get("year"),
        "venue": base.get("venue"),
        "citationcount": None if count is None else int(count),
        "arxiv_id": arxiv_id,
        "url": abs_url(arxiv_id),
        "authors": authors,
        "has_emb": None if has_emb is None else bool(has_emb),
    }


def lookup_meta(corpusid, display=None, display_ext=None, *, has_emb=None, arxiv_lookup=None, authors_lookup=None):
    """La fila de display (CS) gana si el corpusid está en las dos."""
    cs = lookup_table(display, corpusid)
    if cs is not None:
        return _pack(corpusid, cs, "display", has_emb=has_emb, arxiv_lookup=arxiv_lookup, authors_lookup=authors_lookup)
    ext = lookup_table(display_ext, corpusid)
    source = "display_ext" if ext is not None else None
    return _pack(corpusid, ext, source, has_emb=has_emb, arxiv_lookup=arxiv_lookup, authors_lookup=authors_lookup)


def meta_from_files(corpusid, display_path=None, ext_path=None, *, has_emb=None, arxiv_lookup=None, authors_lookup=None):
    """La misma metadata, leyendo un solo row group con `_parquet_row` del lector."""
    from rrm.reader.fetch import _parquet_row

    columns = ["title", "year", "venue", "citationcount", "arxiv", "doi", "tldr", "authors"]
    cid = int(corpusid)
    row = None
    source = None
    if display_path and Path(display_path).is_file():
        row = _parquet_row(Path(display_path), cid, columns)
        if row:
            source = "display"
    if row is None and ext_path and Path(ext_path).is_file():
        row = _parquet_row(Path(ext_path), cid, columns)
        if row:
            source = "display_ext"
    return _pack(cid, row, source, has_emb=has_emb, arxiv_lookup=arxiv_lookup, authors_lookup=authors_lookup)
