"""Local synthetic check. No Modal, no Semantic Scholar network.

Run from the repo root:

    python -m pipelines.s2_download.sanity
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.s2_download.cost_guard import (
    ABORT_USD,
    Ledger,
    cost_usd,
    plan_wave,
    project_full_run,
    shard_over_ceiling,
    usd_per_second,
)
from pipelines.s2_download.fetch import length_from_headers, redact_url
from pipelines.s2_download.s2_client import S2Client, S2ClientError
from pipelines.s2_download.transform import (
    CSIndex,
    build_cs_index,
    load_cs,
    merge_cs,
    process_gzip_path,
    shard_complete,
    verify_tree,
)

RELEASE = "2099-01-01"


class CheckError(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def _gz_writer(path: str, rows: list[dict], pad: int = 0) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.GzipFile(path, "wb") as handle:
        for row in rows:
            if pad:
                row = dict(row)
                row["title"] = row.get("title", "") + ("x" * pad)
            handle.write(json.dumps(row, separators=(",", ":")).encode() + b"\n")
        handle.write(b"not-json\n")


def _papers() -> tuple[list[dict], list[dict]]:
    shard0 = [
        {
            "corpusid": 10,
            "externalids": {"ArXiv": "1706.03762v1", "DOI": "10.1/attn", "MAG": None},
            "title": "Attention",
            "authors": [{"authorId": "1", "name": "Vaswani"}],
            "year": 2017,
            "venue": "NeurIPS",
            "s2fieldsofstudy": [{"category": "Computer Science", "source": "external"}],
            "isopenaccess": True,
            "citationcount": 100,
            "journal": {"name": None, "pages": None, "volume": None},
            "unexpected": {"keep": True},
        },
        {
            "corpusid": 11,
            "title": "Only external field",
            "fieldsOfStudy": ["Computer Science"],
            "year": 2020,
        },
        {
            "corpusid": 12,
            "title": "Medicine paper",
            "externalids": {"ArXiv": "1234.5678"},
            "s2fieldsofstudy": [{"category": "Medicine", "source": "s2-fos-model"}],
            "year": 2015,
        },
    ]
    shard1 = [
        {
            "corpusid": 13,
            "title": "Old arxiv",
            "externalids": {"ArXiv": "hep-ex/0106091v2"},
            "s2fieldsofstudy": [
                {"category": "Computer Science", "source": "s2-fos-model"},
                {"category": "Medicine", "source": "external"},
            ],
            "year": 2001,
        },
        {
            "corpusid": 14,
            "title": "No field",
            "year": 1999,
        },
    ]
    return shard0, shard1


def _vector(seed: int, dim: int = 4) -> str:
    values = [((seed + i) % 7) / 7 for i in range(dim)]
    return json.dumps(values)


def check_bitmap() -> None:
    ids = np.array([0, 1, 7, 8, 9, 9, 1000], dtype=np.int64)
    index, stored = build_cs_index(ids)
    check(list(stored.tolist()) == [0, 1, 7, 8, 9, 1000], "sorted unique ids")
    for corpus_id in (0, 1, 7, 8, 9, 1000):
        check(index.contains(corpus_id), f"missing {corpus_id}")
    for corpus_id in (2, 3, 6, 10, 999, 1001, -1):
        check(not index.contains(corpus_id), f"false positive {corpus_id}")
    check(index.count == 6, "count")
    from pipelines.s2_download.transform import popcount

    check(popcount(index.bits) == 6, "bitmap popcount")
    many = index.contains_many(np.array([0, 2, 8, 1001]))
    check(list(many.tolist()) == [True, False, True, False], "contains_many")
    # Several ids in one byte must all stick.
    packed, _ = build_cs_index(np.arange(0, 16))
    check(all(packed.contains(i) for i in range(16)), "same-byte bits")


def check_cost_and_projection() -> None:
    rate = usd_per_second(2, 4096)
    check(abs(rate - (2 * 0.0473 + 4 * 0.008) / 3600) < 1e-15, "rate")
    store: dict = {}
    ledger = Ledger(store, limit=ABORT_USD)
    one = cost_usd(100_000, 2, 4096)
    ledger.begin("a", one)
    ledger.begin("b", one)
    check(ledger.total() < ABORT_USD, "two reservations fit")
    check(plan_wave(ledger.total(), [one], multiplier=1) == 0, "third does not fit")
    ledger.finish("a", one)
    ledger.finish("b", one)
    check(not ledger.over_budget(), "actuals still under the cap")
    ledger.begin("c", one)
    check(ledger.over_budget(), "third reservation crosses $9")
    # A crashed reservation is kept when the key is reserved again.
    ledger.finish("c", one * 0.1)
    before = ledger.total()
    ledger.begin("c", 0.01)
    check(ledger.total() > before, "retry keeps prior spend")

    check(plan_wave(8.0, [0.2, 0.2, 0.2], multiplier=2, max_wave=10) == 2, "wave size")
    check(plan_wave(8.9, [0.1], multiplier=2) == 0, "wave stops at the cap")
    check(shard_over_ceiling(10, 1.0, 4.0, multiplier=3) is False, "under ceiling")
    check(shard_over_ceiling(13, 1.0, 4.0, multiplier=3) is True, "over ceiling")

    projection = project_full_run(
        papers_seconds_per_byte=100 / 1e9,
        papers_shards=30,
        papers_bytes=30 * 1_000_000_000,
        embeddings_seconds_per_byte=200 / 2e9,
        embeddings_shards=400,
        embeddings_bytes=400 * 2_000_000_000,
        other_bytes={"abstracts": 50_000_000_000},
        other_shards={"abstracts": 40},
        cpu=2,
        memory_mib=4096,
        concurrency=100,
        overhead_seconds=0,
    )
    papers_s = 100 * 30
    emb_s = 200 * 400
    abstracts_s = 50_000_000_000 * (100 / 1e9)
    expected_seconds = papers_s + emb_s + abstracts_s
    check(abs(projection["container_seconds"] - expected_seconds) < 1e-6, "projected seconds")
    check(abs(projection["cost_usd"] - expected_seconds * rate) < 1e-6, "projected dollars")
    expected_wall = papers_s / 30 + (emb_s + abstracts_s) / 100
    check(abs(projection["wall_seconds"] - expected_wall) < 1e-6, "projected wall")
    check(projection["proceed"] is True, "sample projection proceeds")
    blocked = project_full_run(
        papers_seconds_per_byte=1.0,
        papers_shards=2,
        papers_bytes=10_000_000_000,
        embeddings_seconds_per_byte=1.0,
        embeddings_shards=2,
        embeddings_bytes=10_000_000_000,
        other_bytes={},
        other_shards={},
        cpu=2,
        memory_mib=4096,
        concurrency=1,
        overhead_seconds=0,
    )
    check(blocked["proceed"] is False, "huge projection stops")


def check_s2_client() -> None:
    clock = {"t": 0.0}
    calls = []

    class Response:
        def __init__(self, status, headers=None, content=b"{}"):
            self.status_code = status
            self.headers = headers or {}
            self.content = content

    class Session:
        def __init__(self):
            self.responses = [
                Response(429, {"Retry-After": "1"}),
                Response(200, content=b'{"ok":true}'),
            ]

        def get(self, url, params=None, headers=None, timeout=None):
            calls.append(clock["t"])
            check(headers.get("x-api-key") == "synthetic-key", "key header")
            check("semanticscholar" in url, "s2 url")
            return self.responses.pop(0)

    def sleep(seconds):
        clock["t"] += seconds

    client = S2Client(
        "synthetic-key",
        session=Session(),
        sleep=sleep,
        now=lambda: clock["t"],
        clock_store={},
    )
    response = client.get("https://api.semanticscholar.org/datasets/v1/release/latest")
    check(response.status == 200, "retry then 200")
    check(response.body == b'{"ok":true}', "body")
    check(len(calls) == 2, "two attempts")
    check(calls[1] - calls[0] >= 1.1, "spacing after 429")

    class Boom(Exception):
        pass

    class Broken:
        def get(self, url, params=None, headers=None, timeout=None):
            raise Boom("leaked synthetic-key")

    broken = S2Client(
        "synthetic-key",
        session=Broken(),
        sleep=lambda _s: None,
        now=lambda: 0.0,
        min_interval=0,
    )
    try:
        broken.get("https://api.semanticscholar.org/datasets/v1/release/latest")
    except S2ClientError as exc:
        check("synthetic-key" not in str(exc), "key leaked into the error")
        check("leaked" not in str(exc), "upstream message leaked")
    else:
        raise CheckError("transport error was swallowed")


def check_headers() -> None:
    check(length_from_headers({"Content-Length": "42"}, 200) == 42, "content length")
    check(length_from_headers({"Content-Range": "bytes 0-0/99"}, 206) == 99, "content range")
    check(length_from_headers({}, 403) is None, "no length")
    check(redact_url("https://bucket.example/a.gz?X-Amz-Signature=abc") == "https://bucket.example/a.gz", "redact")


def check_pipeline() -> dict:
    with tempfile.TemporaryDirectory() as root:
        raw = os.path.join(root, "_raw")
        shard0, shard1 = _papers()
        papers0 = os.path.join(raw, "papers-0.gz")
        papers1 = os.path.join(raw, "papers-1.gz")
        _gz_writer(papers0, shard0)
        _gz_writer(papers1, shard1)
        abstracts = [
            {"corpusid": corpus_id, "abstract": f"abs {corpus_id}", "openaccessinfo": {"license": "odc", "status": "GOLD"}}
            for corpus_id in (10, 11, 12, 13, 14)
        ]
        tldrs = [
            {"corpusid": 10, "model": "tldr@v2.0.0", "text": "Attention is all you need."},
            {"corpusid": 12, "model": "tldr@v2.0.0", "text": "Not CS."},
        ]
        citations = [
            {
                "citationid": 1,
                "citingcorpusid": 10,
                "citedcorpusid": 13,
                "isinfluential": True,
                "contexts": ["used the architecture"],
                "intents": ["methodology"],
            },
            {
                "citationid": 2,
                "citingcorpusid": 10,
                "citedcorpusid": 12,
                "isinfluential": False,
                "contexts": None,
                "intents": None,
            },
            {
                "citationid": 3,
                "citingcorpusid": 12,
                "citedcorpusid": 10,
                "isinfluential": False,
                "contexts": ["background mention"],
                "intents": [["background"]],
            },
            {
                "citationid": 4,
                "citingcorpusid": 12,
                "citedcorpusid": 14,
                "isinfluential": False,
                "contexts": None,
                "intents": None,
            },
            {
                "citationid": 5,
                "citingcorpusid": 14,
                "citedcorpusid": 11,
                "isinfluential": False,
                "contexts": ["see also"],
                "intents": ["background"],
            },
        ]
        embeddings = [
            {"corpusid": 10, "model": "specter_v2", "vector": _vector(10)},
            {"corpusid": 12, "model": "specter_v2", "vector": _vector(12)},
            {"corpusid": 13, "model": "specter_v2", "vector": _vector(13)},
            {"corpusid": 11, "model": "specter_v2", "vector": _vector(11)},
            {"corpusid": 99, "model": "specter_v2", "vector": _vector(99)},
            {"corpusid": 13, "model": "specter_v2", "vector": "not-a-vector"},
        ]
        paths = {
            "abstracts": os.path.join(raw, "abstracts.gz"),
            "tldrs": os.path.join(raw, "tldrs.gz"),
            "citations": os.path.join(raw, "citations.gz"),
            "embeddings": os.path.join(raw, "embeddings.gz"),
        }
        _gz_writer(paths["abstracts"], abstracts)
        _gz_writer(paths["tldrs"], tldrs)
        _gz_writer(paths["citations"], citations)
        _gz_writer(paths["embeddings"], embeddings)

        # Streaming: many padded records, small batches, gzip reads stay bounded.
        padded = [
            {
                "corpusid": 1000 + i,
                "title": f"pad-{i}-" + os.urandom(8000).hex(),
                "s2fieldsofstudy": [{"category": "Medicine", "source": "external"}],
                "year": 2000,
            }
            for i in range(30)
        ]
        padded_path = os.path.join(raw, "padded.gz")
        _gz_writer(padded_path, padded)
        check(os.path.getsize(padded_path) > 128 * 1024, "synthetic gzip is larger than one gzip read")
        streamed = process_gzip_path(
            "papers",
            padded_path,
            root=root,
            release=RELEASE,
            index=7,
            batch_size=4,
        )
        check(streamed["max_buffered"] <= 4, f"batch held {streamed['max_buffered']} rows")
        check(streamed["stream_read_all"] is False, "reader asked for the whole file")
        check(streamed["stream_bytes"] > streamed["stream_max_read"], "more than one read")
        check(streamed["rows"] == 30, "padded rows")
        check(streamed["bad_lines"] == 1, "padded bad line")

        first = process_gzip_path("papers", papers0, root=root, release=RELEASE, index=0, batch_size=2)
        second = process_gzip_path("papers", papers1, root=root, release=RELEASE, index=1, batch_size=2)
        check(first["rows"] == 3 and second["rows"] == 2, "paper rows")
        check(first["bad_lines"] == 1 and second["bad_lines"] == 1, "bad lines skipped")
        check(first["max_buffered"] <= 2, "papers batch bound")
        check(first["cs_rows"] == 2 and second["cs_rows"] == 1, "per-shard CS rows")
        merged = merge_cs(root, RELEASE, partial=False)
        check(merged["cs_papers"] == 3, "CS papers")
        check(merged["arxiv_rows"] == 3, "arxiv rows")
        check(merged["partial"] is False, "full merge flag")
        meta_path = os.path.join(root, RELEASE, "_cs", "meta.json")
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        check(meta["partial"] is False, "meta partial flag")
        flagged = merge_cs(root, RELEASE, partial=True)
        check(flagged["partial"] is True, "sample merge stays partial")
        merged = merge_cs(root, RELEASE, partial=False)
        check(merged["partial"] is False, "rebuild clears the partial flag")
        index = load_cs(os.path.join(root, RELEASE, "_cs"))
        check(isinstance(index, CSIndex), "index type")
        for corpus_id in (10, 11, 13):
            check(index.contains(corpus_id), f"CS {corpus_id}")
        check(not index.contains(12) and not index.contains(14), "non-CS excluded")

        papers_table = pq.read_table(os.path.join(root, RELEASE, "papers", "shard-00000.parquet"))
        check(papers_table.column("title")[0].as_py() == "Attention", "title kept")
        check(papers_table.column("extra")[0].as_py() is not None, "unknown field kept")
        check(papers_table.column("year")[0].as_py() == 2017, "year kept")

        abstracts_result = process_gzip_path(
            "abstracts", paths["abstracts"], root=root, release=RELEASE, index=0, batch_size=2
        )
        tldr_result = process_gzip_path("tldrs", paths["tldrs"], root=root, release=RELEASE, index=0, batch_size=2)
        citation_result = process_gzip_path(
            "citations",
            paths["citations"],
            root=root,
            release=RELEASE,
            index=0,
            cs=index,
            batch_size=2,
        )
        embedding_result = process_gzip_path(
            "embeddings-specter_v2",
            paths["embeddings"],
            root=root,
            release=RELEASE,
            index=0,
            cs=index,
            batch_size=2,
        )
        check(abstracts_result["rows"] == 5, "abstract rows")
        check(tldr_result["rows"] == 2, "tldr rows")
        check(citation_result["rows"] == 5, "citation rows")
        check(citation_result["cs_rows"] == 4, "CS edges")
        check(citation_result["both_cs"] == 1, "both-CS flag")
        check(embedding_result["rows"] == 3, "CS embeddings kept")
        check(embedding_result["vector_dim"] == 4, "vector dim")
        check(embedding_result["bad_lines"] == 2, "bad embedding line and trailing junk")

        vectors = pq.read_table(os.path.join(root, RELEASE, "embeddings-specter_v2", "shard-00000.parquet"))
        check(vectors.schema.field("vector").type == pa.list_(pa.float16(), 4), "fp16 list")
        kept = vectors.column("corpusid").to_pylist()
        check(kept == [10, 13, 11], "embedding order")
        first_vec = vectors.column("vector")[0].as_py()
        check(len(first_vec) == 4, "vector width")
        check(abs(first_vec[0] - json.loads(_vector(10))[0]) < 0.02, "fp16 value")

        cs_edges = pq.read_table(os.path.join(root, RELEASE, "citations-cs", "shard-00000.parquet"))
        both = [row for row in cs_edges.to_pylist() if row["both_cs"]]
        check(len(both) == 1 and both[0]["citationid"] == 1, "both-CS row")
        nested = [row for row in cs_edges.to_pylist() if row["citationid"] == 3][0]
        check(json.loads(nested["intents"]) == [["background"]], "nested intents preserved")

        # A budget stop must not leave a shard that looks complete.
        def stop() -> str:
            return "budget"

        try:
            process_gzip_path(
                "abstracts",
                paths["abstracts"],
                root=root,
                release=RELEASE,
                index=3,
                batch_size=1,
                should_stop=stop,
            )
        except Exception as exc:
            check(type(exc).__name__ == "StopShard", "stop type")
        else:
            raise CheckError("budget stop did not raise")
        check(not shard_complete(root, RELEASE, "abstracts", 3), "partial shard removed")

        report = verify_tree(root, RELEASE)
        check(report["ok"], "verify ok")
        check(report["cs_papers"] == 3, "verify CS papers")
        check(report["cs_index_consistent"], "index consistent")
        check(report["cs_embeddings"] == 3, "verify embeddings")
        empty_path = os.path.join(raw, "embeddings-empty.gz")
        _gz_writer(empty_path, [{"corpusid": 14, "model": "specter_v2", "vector": _vector(14)}])
        empty_embeddings = process_gzip_path(
            "embeddings-specter_v2",
            empty_path,
            root=root,
            release=RELEASE,
            index=1,
            cs=index,
            batch_size=2,
        )
        check(empty_embeddings["rows"] == 0, "non-CS embedding shard is empty")
        empty_table = pq.read_table(
            os.path.join(root, RELEASE, "embeddings-specter_v2", "shard-00001.parquet")
        )
        check(empty_table.num_rows == 0, "empty embedding parquet")
        check(empty_table.schema.field("vector").type == pa.list_(pa.float16(), 768), "empty dim")

        check(report["datasets"]["papers"]["rows"] == 5 + 30, "verify paper rows")
        check(report["datasets"]["abstracts"]["rows"] == 5, "verify abstracts")
        check(report["datasets"]["tldrs"]["rows"] == 2, "verify tldrs")
        check(report["datasets"]["citations"]["rows"] == 5, "verify citations")
        check(report["datasets"]["citations-cs"]["rows"] == 4, "verify CS edges")
        check(report["datasets"]["citations-cs"]["both_cs"] == 1, "verify both-CS")
        check(report["arxiv_rows"] == 3, "verify arxiv rows")
        check(report["cs_papers_with_arxiv"] == 2, "CS papers with arxiv")
        check(report["total_gb"] > 0, "total GB")
        return {
            "papers_rows": report["datasets"]["papers"]["rows"],
            "cs_papers": report["cs_papers"],
            "cs_embeddings": report["cs_embeddings"],
            "citation_rows": report["datasets"]["citations"]["rows"],
            "cs_edges": report["datasets"]["citations-cs"]["rows"],
            "both_cs": report["datasets"]["citations-cs"]["both_cs"],
            "arxiv_rows": report["arxiv_rows"],
            "cs_papers_with_arxiv": report["cs_papers_with_arxiv"],
            "stream_max_read": streamed["stream_max_read"],
            "stream_bytes": streamed["stream_bytes"],
            "max_buffered": streamed["max_buffered"],
        }


def main() -> None:
    check_bitmap()
    check_cost_and_projection()
    check_s2_client()
    check_headers()
    summary = check_pipeline()
    print(json.dumps({"sanity": "pass", "synthetic": summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
