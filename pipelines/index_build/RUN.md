# Index build, burst search, citation recall

From the repo root. Volume `rrm-data`, release directory `/s2/2026-10-20/` (the id `pipelines/s2_download` writes). `build_cs_ids` must already have written `cs_corpusids.parquet`. Embeddings are the CS-filtered `embeddings-specter_v2` shards.

`limit` is how many `part-*.parquet` shards (0 = all). `row-limit` is how many rows to read from each shard (0 = all). `dest=index_test` writes `/s2/<release>/index_test/` so a short run does not replace `/s2/<release>/index/`. `m` must divide 768. The FAISS train set must have at least `nlist` vectors.

`cpu` and `memory` (MiB) apply to the shard containers. Do the test command for a stage, look at the printed row counts, then the full command.

Burst search reads `MODEL_API_KEY` from the environment (one chat completion, no key in the repo). The eval does not call the model. Its split is an offline cut of the query text.

## FAISS

```bash
modal run pipelines/index_build/app.py::faiss_index --release 2026-10-20 --dest index_test --limit 1 --row-limit 2000 --nlist 32 --m 48 --nbits 8 --nprobe 8 --train-size 1000 --sample-per-shard 1000 --cpu 1 --memory 4096 --train-cpu 1 --train-memory 4096
modal run --detach pipelines/index_build/app.py::faiss_index --release 2026-10-20 --dest index --limit 0 --row-limit 0 --nlist 4096 --m 96 --nbits 8 --nprobe 32 --train-size 262144 --sample-per-shard 4096 --cpu 1 --memory 8192 --train-cpu 4 --train-memory 16384
```

## Citation graph

```bash
modal run pipelines/index_build/app.py::citation_graph --release 2026-10-20 --dest index_test --limit 1 --row-limit 20000 --cpu 1 --memory 4096 --merge-memory 4096
modal run --detach pipelines/index_build/app.py::citation_graph --release 2026-10-20 --dest index --limit 0 --row-limit 0 --cpu 1 --memory 4096 --merge-memory 16384
```

## Display table

`limit` applies to papers and to tldrs separately.

```bash
modal run pipelines/index_build/app.py::display_table --release 2026-10-20 --dest index_test --limit 1 --row-limit 5000 --cpu 1 --memory 4096 --merge-memory 4096
modal run --detach pipelines/index_build/app.py::display_table --release 2026-10-20 --dest index --limit 0 --row-limit 0 --cpu 1 --memory 4096 --merge-memory 16384
```

## One query

Needs `faiss.index`, `faiss_ids.npy`, the CSR arrays, and `display.parquet` under the dest directory. The container asks for 16 GB. A DOI, arXiv id, corpus id, or exact title (lowercase, punctuation collapsed) uses that paper's stored vector and its citation neighbors, and does not call the model. Rebuild the display table so those rows include `doi`, `arxiv`, and `title_norm`. `MODEL_API_KEY` is read only when the query is not one of those papers. A paste longer than 40 words, and a title joined to an abstract with a newline, use the SPECTER2 proximity adapter. Shorter text uses `adhoc_query`.

```bash
modal run rrm/search/serve.py::main --query "How do graph neural networks use citation structure?" --release 2026-10-20 --dest index_test
modal run rrm/search/serve.py::main --query "How do graph neural networks use citation structure?" --release 2026-10-20 --dest index
```

## Citation recall

Prints mean recall for `knn`, `knn_hop`, and `split`, plus p50/p95 seconds per stage. A one-shard slice often has no paper with both an abstract and enough CS references; `n` in the printout is how many were actually scored.

```bash
modal run eval/citation_recall.py::main --release 2026-10-20 --dest index_test --n 5 --min-refs 1 --shard-limit 1 --row-limit 5000
modal run --detach eval/citation_recall.py::main --release 2026-10-20 --dest index --n 200 --min-refs 20 --shard-limit 0 --row-limit 0
```

Local check, no Modal and no model download:

```bash
python3 -m pytest tests/test_search.py -q
```
