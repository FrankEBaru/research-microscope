"""One display table: corpusid, title, year, venue, citationcount, tldr."""

import numpy as np


def _keep(table, cs_sorted):
    from rrm.search.graph import int_column, locate

    ids, valid = int_column(table, "corpusid")
    hit, _pos = locate(cs_sorted, ids)
    return np.flatnonzero(valid & hit)


def filter_papers(table, cs_sorted):
    cols = ["corpusid", "title", "year", "venue", "citationcount"]
    return table.select(cols).take(_keep(table, cs_sorted))


def filter_tldrs(table, cs_sorted):
    return table.select(["corpusid", "text"]).take(_keep(table, cs_sorted))


def unique_sorted(table):
    if table.num_rows == 0:
        return table
    table = table.sort_by("corpusid")
    ids = table.column("corpusid").fill_null(-1).to_numpy(zero_copy_only=False)
    keep = np.ones(len(ids), dtype=bool)
    keep[1:] = ids[1:] != ids[:-1]
    return table.take(np.flatnonzero(keep))


def merge_display(papers, tldrs):
    import pyarrow as pa

    papers = unique_sorted(papers)
    if tldrs is None or tldrs.num_rows == 0:
        return papers.append_column("tldr", pa.nulls(papers.num_rows, pa.string()))
    tldrs = unique_sorted(tldrs)
    side = pa.table({"corpusid": tldrs.column("corpusid"), "tldr": tldrs.column("text")})
    return papers.join(side, keys="corpusid", join_type="left outer").sort_by("corpusid")


def empty_papers():
    import pyarrow as pa

    return pa.table({
        "corpusid": pa.array([], type=pa.int64()),
        "title": pa.array([], type=pa.string()),
        "year": pa.array([], type=pa.int64()),
        "venue": pa.array([], type=pa.string()),
        "citationcount": pa.array([], type=pa.int64()),
    })


def empty_tldrs():
    import pyarrow as pa

    return pa.table({
        "corpusid": pa.array([], type=pa.int64()),
        "text": pa.array([], type=pa.string()),
    })


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
