"""One display table: corpusid, title, year, venue, citationcount, tldr, plus doi, arxiv, title_norm."""

import re

import numpy as np

_DOI = re.compile(r"^(?:doi:\s*)?10\.\d{4,9}/\S+$", re.I)
_ARXIV = re.compile(
    r"^(?:arxiv:\s*)?(?:[a-z][a-z.-]*(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?$",
    re.I,
)
_CORPUS = re.compile(r"^(?:(?:corpusid|s2):\s*)?\d{1,12}$", re.I)


def _keep(table, cs_sorted):
    from rrm.search.graph import int_column, locate

    ids, valid = int_column(table, "corpusid")
    hit, _pos = locate(cs_sorted, ids)
    return np.flatnonzero(valid & hit)


def norm_title(text):
    """Lowercase, punctuation and whitespace collapsed to single spaces."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def canon_doi(text):
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return re.sub(r"^doi:\s*", "", text).strip()


def canon_arxiv(text):
    if not text:
        return ""
    text = re.sub(r"^arxiv:\s*", "", text.strip().lower())
    return re.sub(r"v\d+$", "", text).strip()


def _ext_strings(table, keep, names, canon):
    n = len(keep)
    if "externalids" not in table.column_names:
        return [None] * n
    ext = table.column("externalids").take(keep)
    if hasattr(ext, "combine_chunks"):
        ext = ext.combine_chunks()
    import pyarrow as pa
    if not pa.types.is_struct(ext.type):
        return [None] * n
    present = set(ext.type.names)
    field = next((name for name in names if name in present), None)
    if field is None:
        return [None] * n
    out = []
    for value in ext.field(field).to_pylist():
        key = canon(value)
        out.append(key or None)
    return out


def filter_papers(table, cs_sorted):
    import pyarrow as pa

    keep = _keep(table, cs_sorted)
    cols = ["corpusid", "title", "year", "venue", "citationcount"]
    out = table.select(cols).take(keep)
    titles = out.column("title").to_pylist()
    norms = [norm_title(title) or None for title in titles]
    return (
        out.append_column("doi", pa.array(_ext_strings(table, keep, ("DOI", "doi"), canon_doi), pa.string()))
        .append_column("arxiv", pa.array(_ext_strings(table, keep, ("ArXiv", "Arxiv", "arxiv"), canon_arxiv), pa.string()))
        .append_column("title_norm", pa.array(norms, pa.string()))
    )


def filter_tldrs(table, cs_sorted):
    return table.select(["corpusid", "text"]).take(_keep(table, cs_sorted))


def _large_strings(table):
    """string -> large_string, so a column over 2 GB (all CS tldrs) can be sorted."""
    import pyarrow as pa

    fields = [pa.field(f.name, pa.large_string()) if pa.types.is_string(f.type) else f for f in table.schema]
    return table.cast(pa.schema(fields))


def unique_sorted(table):
    if table.num_rows == 0:
        return table
    table = _large_strings(table).sort_by("corpusid")
    ids = table.column("corpusid").fill_null(-1).to_numpy(zero_copy_only=False)
    keep = np.ones(len(ids), dtype=bool)
    keep[1:] = ids[1:] != ids[:-1]
    return table.take(np.flatnonzero(keep))


def merge_display(papers, tldrs):
    import pyarrow as pa

    papers = unique_sorted(papers)
    if tldrs is None or tldrs.num_rows == 0:
        return papers.append_column("tldr", pa.nulls(papers.num_rows, pa.string()))
    from rrm.search.graph import locate

    # A sorted lookup instead of Table.join: the Acero join aborts on ~16M rows of tldr text.
    tldrs = unique_sorted(tldrs)
    tids = tldrs.column("corpusid").fill_null(-1).to_numpy(zero_copy_only=False)
    pids = papers.column("corpusid").fill_null(-1).to_numpy(zero_copy_only=False)
    hit, pos = locate(tids, pids)
    take = pa.array(pos, type=pa.int64(), mask=~hit)
    return papers.append_column("tldr", tldrs.column("text").take(take))


def empty_papers():
    import pyarrow as pa

    return pa.table({
        "corpusid": pa.array([], type=pa.int64()),
        "title": pa.array([], type=pa.string()),
        "year": pa.array([], type=pa.int64()),
        "venue": pa.array([], type=pa.string()),
        "citationcount": pa.array([], type=pa.int64()),
        "doi": pa.array([], type=pa.string()),
        "arxiv": pa.array([], type=pa.string()),
        "title_norm": pa.array([], type=pa.string()),
    })


def empty_tldrs():
    import pyarrow as pa

    return pa.table({
        "corpusid": pa.array([], type=pa.int64()),
        "text": pa.array([], type=pa.string()),
    })


class IdTable:
    """Binary search over a display table sorted by corpusid."""

    def __init__(self, table):
        self.table = table
        self._starts = {}
        self.ids = np.zeros(0, dtype=np.int64)
        if table is not None and table.num_rows:
            self.ids = np.asarray(table.column("corpusid").to_numpy(zero_copy_only=False), dtype=np.int64)

    def row(self, cid):
        cid = int(cid)
        if self.ids.size == 0:
            return None
        at = int(np.searchsorted(self.ids, cid))
        if at >= self.ids.size or int(self.ids[at]) != cid:
            return None

        def cell(name):
            if name not in self.table.column_names:
                return None
            return self.table.column(name)[at].as_py()

        count = cell("citationcount")
        return {
            "corpusid": cid,
            "title": cell("title"),
            "year": cell("year"),
            "venue": cell("venue"),
            "citationcount": None if count is None else int(count),
        }


    def rows(self, cids):
        """row() for many ids. Cells are read from their chunk directly: indexing a
        ChunkedArray scans its chunks, and take() on it copies whole columns."""
        out = []
        for cid in cids:
            cid = int(cid)
            at = int(np.searchsorted(self.ids, cid)) if self.ids.size else 0
            if self.ids.size == 0 or at >= self.ids.size or int(self.ids[at]) != cid:
                out.append(None)
                continue
            count = self._cell("citationcount", at)
            out.append({
                "corpusid": cid,
                "title": self._cell("title", at),
                "year": self._cell("year", at),
                "venue": self._cell("venue", at),
                "citationcount": None if count is None else int(count),
            })
        return out

    def _cell(self, name, at):
        if name not in self.table.column_names:
            return None
        if name not in self._starts:
            col = self.table.column(name)
            lengths = [len(chunk) for chunk in col.chunks]
            self._starts[name] = (col, np.cumsum([0] + lengths[:-1]).astype(np.int64))
        col, starts = self._starts[name]
        c = int(np.searchsorted(starts, at, side="right")) - 1
        return col.chunk(c)[at - int(starts[c])].as_py()


def hydrate(corpusids, table):
    if table is None or table.num_rows == 0:
        return [_blank(cid) for cid in corpusids]
    ids = table.column("corpusid").to_numpy(zero_copy_only=False)
    rows = []
    for cid in corpusids:
        at = int(np.searchsorted(ids, int(cid)))
        if at < len(ids) and int(ids[at]) == int(cid):
            rows.append({
                "corpusid": int(cid),
                "title": table.column("title")[at].as_py(),
                "year": table.column("year")[at].as_py(),
                "venue": table.column("venue")[at].as_py(),
                "citationcount": table.column("citationcount")[at].as_py(),
                "tldr": table.column("tldr")[at].as_py() if "tldr" in table.column_names else None,
            })
        else:
            rows.append(_blank(cid))
    return rows


def _blank(cid):
    return {"corpusid": int(cid), "title": None, "year": None, "venue": None, "citationcount": None, "tldr": None}


TITLE_MIN_WORDS = 4  # "speech recognition" must search, not open a 1998 paper of that name
TITLE_MIN_CITES = 1000  # ...but "Layer Normalization" still opens the paper


class PaperLookup:
    """Exact DOI, arXiv, corpus id, or normalized title. First row wins."""

    def __init__(self, table):
        self.doi = {}
        self.arxiv = {}
        self.title = {}
        self.ids = set()
        if table is None or table.num_rows == 0:
            return
        ids = table.column("corpusid").to_pylist()
        self.ids = {int(cid) for cid in ids if cid is not None}
        self._fill(self.doi, ids, table, "doi")
        self._fill(self.arxiv, ids, table, "arxiv")
        self._fill_titles(ids, table)

    def _fill_titles(self, ids, table):
        """Most-cited row per title. A short title needs TITLE_MIN_CITES to count."""
        if "title_norm" not in table.column_names:
            return
        if "citationcount" in table.column_names:
            counts = table.column("citationcount").to_pylist()
        else:
            counts = [None] * len(ids)
        best = {}
        for cid, raw, count in zip(ids, table.column("title_norm").to_pylist(), counts):
            if cid is None or not raw:
                continue
            count = int(count or 0)
            if len(raw.split()) < TITLE_MIN_WORDS and count < TITLE_MIN_CITES:
                continue
            if raw not in best or count > best[raw][0]:
                best[raw] = (count, int(cid))
        self.title = {raw: cid for raw, (_count, cid) in best.items()}

    def _fill(self, dest, ids, table, column):
        if column not in table.column_names:
            return
        for cid, raw in zip(ids, table.column(column).to_pylist()):
            if cid is not None and raw and raw not in dest:
                dest[raw] = int(cid)

    def resolve(self, query):
        text = " ".join(query.split())
        if not text:
            return None
        doi = canon_doi(text)
        if _DOI.match(text) or _DOI.match(doi) or "doi.org/" in text.lower():
            return self.doi.get(doi)
        if _ARXIV.match(text):
            return self.arxiv.get(canon_arxiv(text))
        if _CORPUS.match(text):
            cid = int(re.search(r"\d+", text).group())
            return cid if cid in self.ids else None
        return self.title.get(norm_title(text))
