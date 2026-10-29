# S2 bulk download

Run these from the repository root, in order. Each command starts one Modal app
(`rrm-s2-download`) and returns after that stage. `--detach` keeps the remote
orchestrator running if the local client disconnects. Do not chain the stages
in one command.

The Semantic Scholar key is the Modal secret `s2-api-key` (env `S2_API_KEY`
inside Modal). It is not read from the local environment.

`modal run` loads this file in the container as `/root/app.py`. The `pipelines`
package is copied into the image at `/root/pipelines`, which is on `PYTHONPATH`,
so the imports do not depend on the repo layout. A container that dies during
import is limited to a 120 second startup. `keycheck`, `calibrate`, `full`,
`verify`, the API class, and the CS merge do not retry. A shard still retries
twice after it has started.

```bash
modal run --detach pipelines/s2_download/app.py::keycheck
modal run --detach pipelines/s2_download/app.py::calibrate
modal run --detach pipelines/s2_download/app.py::full
modal run --detach pipelines/s2_download/app.py::verify
```

`::app.keycheck` (and the same for the other three) is the same entrypoint.

Stop if keycheck exits non-zero, or if calibrate exits 2 (or the JSON record
has `"proceed": false`). `full` refuses to start unless that record says
proceed. `--force` overrides only that gate. It does not override the $9 stop.

## What each stage prints

Numbers below are the fields, not sample measurements. With `--detach`, the
JSON on the volume is the result that remains if the local process is gone.
Stdout repeats the same summary.

**keycheck** (exit 0 when both calls are HTTP 200, else 1)

```text
stage keycheck
graph status 200
release status 200
release_id <release id>
dataset <name> status <http status> shards <count>
ok true
cumulative $<ledger>
volume record /_runs/latest-keycheck.json
```

Only status codes and shard counts are printed. Response bodies and presigned
URLs are not.

**calibrate** (exit 0 when papers, citations, and embeddings all finished and
the projection is inside the gate, exit 2 when that measurement succeeded but
the projection says stop, exit 1 when a required shard or the release listing
failed)

Samples, in order, under a **$0.10** cap for this stage (separate from the $9
ledger): papers shard 0, the smallest citations shard, the smallest abstracts
shard, embeddings shard 0. Each line is always printed. A shard that is not
started ends with `error not started: ...`. A shard killed before it finishes
is not a throughput measurement.

Papers, abstracts, citations, and tldrs are parsed with `pyarrow.json` on
newline-aligned blocks (64 MiB decompressed, threaded). Decompression uses
`isal` when it is installed. Unknown JSON keys are dropped. Embeddings stay
on a line parser. The citations and embeddings parquet from this stage are
deleted: both were filtered with only the calibration papers shard's Computer
Science ids. A finished abstracts shard is kept. Papers shard 0 is kept.

```text
stage calibrate
release_id <release id>
papers shard <n>: wall <s>s, <MB/s> MB/s, peak RAM <MiB> MiB, output <GB> GB, <container-s> container-s -> $<usd>
citations shard <n>: wall <s>s, <MB/s> MB/s, peak RAM <MiB> MiB, output <GB> GB, <container-s> container-s -> $<usd>
abstracts shard <n>: wall <s>s, <MB/s> MB/s, peak RAM <MiB> MiB, output <GB> GB, <container-s> container-s -> $<usd>
embeddings-specter_v2 shard <n>: wall <s>s, <MB/s> MB/s, peak RAM <MiB> MiB, output <GB> GB, <container-s> container-s -> $<usd>
projection (estimated): <container-s> container-s, $<usd>, wall <hours> h, proceed=<true|false>
cpu=1 estimate: $<usd>, wall <hours> h, proceed=<true|false>
cpu=2 estimate: $<usd>, wall <hours> h, proceed=<true|false>
recommended_cpu <1|2>
input papers: <GB> GB, <shards> shards, rate measured
input abstracts: <GB> GB, <shards> shards, rate measured|papers
input tldrs: <GB> GB, <shards> shards, rate abstracts|papers
input citations: <GB> GB, <shards> shards, rate measured|unmeasured
input embeddings-specter_v2: <GB> GB, <shards> shards, rate measured
cumulative $<ledger>
volume record /_runs/latest-calibrate.json
```

The projection is marked `"estimated": true` in the JSON. It is container-seconds
times $0.0473 per core-hour and $0.008 per GiB-hour, at the cpu and memory for
the run (default 2 cores and 4096 MiB). Citations use the citations sample
only. Abstracts use their own sample when it finished, otherwise the papers
rate. Tldrs follow that abstracts rate. Embeddings use their own rate.

`by_cpu` prices the same bytes at 1 and at 2 cores. Two cores are treated as
1.4× the JSON throughput of one core (local synthetic timing of this parser,
not a Modal result), not 2×. Embeddings seconds/byte is not scaled. The gate
uses the cpu you passed. `recommended_cpu` is the cheaper of the two
estimates. At 4 GiB that is often 1 core, because the second core costs more
than the 1.4× speedup returns. Pass that value as `--cpu` on the next
calibrate if you want the gate to use it. cpu=2 still finishes the wall clock
sooner. Papers are
assumed to finish first; the other datasets then share one pool of containers.
A 600 second single-container allowance is included. Image build and queue
wait are not.

Proceed is false when the projected cost is above $8 or the projected wall time
is above 3 hours, or when papers, citations, or embeddings has no measured
rate. The stage then exits 2 only if the required samples finished and the
projection says stop. A missing citations rate is exit 1.

**full** (exit 0 when the requested datasets finished, exit 4 when the
calibration gate blocked it, exit 3 when the running ledger reached $9,
exit 1 on any other failure)

```text
stage full
release_id <release id>
ok true aborted false blocked false
papers: rows <n> output <GB> GB shards ok <n> failed <n> skipped <n> <container-s> container-s -> $<usd>
cs index: papers <n> arxiv rows <n>
abstracts: ...
tldrs: ...
citations: ...
embeddings-specter_v2: ...
cumulative $<ledger>
volume record /_runs/latest-full.json
```

Order is papers, then the Computer Science id bitmap, then abstracts, tldrs,
citations, and embeddings sharing one pool. Citations also write a Computer
Science edge shard. Embeddings keep only Computer Science corpus ids, as fp16.

**verify** (exit 0 when the release directory exists and the report was written,
else 1). A filtered run can be ok with only some datasets present.

```text
stage verify
release_id <release id>
ok true
papers: rows <n> files <n> <GB> GB
abstracts: ...
tldrs: ...
citations: ...
embeddings-specter_v2: ...
citations-cs: ...
citations-cs both_cs <n>
cs_papers <n> consistent <true|false>
cs_embeddings <n>
arxiv rows <n> in CS <n> CS papers with arxiv <n> coverage <fraction>
total <GB> GB
volume record /_runs/latest-verify.json
```

`consistent` is true when the corpus-id array length, the bitmap popcount, and
`meta.json` count agree.

## Options

```bash
modal run --detach pipelines/s2_download/app.py::calibrate --cpu 2 --memory 4096 --concurrency 100
modal run --detach pipelines/s2_download/app.py::full --cpu 2 --memory 4096 --concurrency 100
modal run --detach pipelines/s2_download/app.py::full --datasets papers,abstracts
modal run --detach pipelines/s2_download/app.py::full --datasets embeddings
modal run --detach pipelines/s2_download/app.py::full --force
modal run --detach pipelines/s2_download/app.py::full --reprocess
```

`--datasets` accepts `papers`, `abstracts`, `tldrs`, `citations`,
`embeddings-specter_v2`, plus the aliases `embeddings` and `specter_v2`.
Empty means all five. `--concurrency` is clamped to 1..100. `--memory` is MiB,
at least 512. `--reprocess` ignores shards already on the volume. Existing
Parquet shards are skipped otherwise.

Citations and embeddings need a Computer Science index built from the papers
dataset of this release. The index written by calibrate is marked partial and
cannot be used for those datasets. Run `papers` in `full` first (the default
dataset list does this).

## Reading the records

In the container the files are `/s2/_runs/latest-<stage>.json`. `modal volume get`
paths are relative to the volume root:

```bash
modal volume ls rrm-data /_runs
modal volume get rrm-data /_runs/latest-keycheck.json .
modal volume get rrm-data /_runs/latest-calibrate.json .
modal volume get rrm-data /_runs/latest-full.json .
modal volume get rrm-data /_runs/latest-verify.json .
```

Stamped copies are `/_runs/<stage>-<UTC>.json`.

## Stop rules

The ledger is cumulative across stages (container-seconds times the rates
above), including the orchestrator and the API container. At $9 it stops
scheduling and in-flight shards exit. A shard also exits if it passes three
times its own estimate. `--force` does not bypass $9. Calibrate also keeps
its own samples inside about $0.10; that cap does not raise the $9 stop and
does not lower it.

Parquet (zstd) lands at `/s2/<release>/<dataset>/shard-NNNNN.parquet` on the
`rrm-data` volume, mounted at `/s2`. Raw `.gz` shards are not kept. The
Computer Science bitmap is `/s2/<release>/_cs/`.

## Local synthetic check

This does not call Modal or Semantic Scholar:

```bash
python3 -m pipelines.s2_download.sanity
```

It needs `numpy` and `pyarrow` (NumPy 2 with current pyarrow). A passing run
prints one JSON object with `"sanity": "pass"` and a `synthetic` object.
Those counts are from tiny gzip files in a temp directory.

Dataset license: Semantic Scholar is ODC-BY. Attribute "Semantic Scholar".
