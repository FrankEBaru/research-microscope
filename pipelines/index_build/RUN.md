# Index build, burst search, citation recall

From the repo root. Volume `rrm-data`, release directory `/s2/2026-10-20/` (the id `pipelines/s2_download` writes). `build_cs_ids` must already have written `cs_corpusids.parquet`. Embeddings are the CS-filtered `embeddings-specter_v2` shards.

`limit` is how many `part-*.parquet` shards (0 = all). `row-limit` is how many rows to read from each shard (0 = all). `dest=index_test` writes `/s2/<release>/index_test/` so a short run does not replace `/s2/<release>/index/`. `m` must divide 768. The FAISS train set must have at least `nlist` vectors.

`cpu` and `memory` (MiB) apply to the shard containers. Do the test command for a stage, look at the printed row counts, then the full command.

Burst ranking reads `/s2/2026-10-20/index` (FAISS, CS display) and `/s2/2026-10-20/index_ext` (extended graph, `node_meta.npz`, `display_ext.parquet`). `MODEL_API_KEY` is read from the environment only for optional subtopic labels. The key is not stored in the repo. The eval does not call the model.

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

## Extended graph

Already on the volume under `index_ext`. Rebuild only to reproduce it. Citing papers are the CS ids in `--index-dest` (`graph_ids.npy`). Cited papers are any corpus id. The merge container asks for 96 GB. `stage` is `all`, `edges`, `merge`, or `meta`.

```bash
modal run pipelines/index_build/app.py::graph_ext --release 2026-10-20 --dest index_ext --index-dest index --limit 1 --row-limit 20000 --stage edges
modal run --detach pipelines/index_build/app.py::graph_ext --release 2026-10-20 --dest index_ext --index-dest index --limit 0 --row-limit 0
```

## One query

The container asks for 32 GB and loads the index in `enter`. `n` is the burst length (default 50, clipped to 100). The similar list is the FAISS seed neighborhood (100 or 200), separate from `n`. A DOI, arXiv id, corpus id, or exact title uses that paper's stored vector: the paper first, then up to 100 references and 100 citers by citation count, then the long-text link rank. Other queries use proximity weights when the text is long and rank weights when it is short. Subtopic labels are optional and do not change the order.

```bash
modal run rrm/search/serve.py::main --query "How do graph neural networks use citation structure?" --n 50
modal deploy rrm/search/serve.py
curl -G "https://<workspace>--rrm-burst-burstsearch-burst.modal.run" --data-urlencode "q=graph neural networks" --data-urlencode "n=10"
```

`modal deploy` prints the live URL; the host above is the usual shape for this app, class, and method.

## Citation recall

Prints mean recall at 10, 15, 20, 50, and 100 for `burst` and `knn`, plus precision@10, nDCG@10, and p50/p95 seconds. The relevant set is every `index_ext` out-neighbor of the query paper. FAISS and the CS display table come from `--dest`. The graph always comes from `/s2/<release>/index_ext`. A one-shard slice often has no paper with both an abstract and enough references; `n` in the printout is how many were actually scored.

```bash
modal run --detach eval/citation_recall.py::main --release 2026-10-20 --dest index --n 200 --min-refs 20 --shard-limit 0 --row-limit 0
```

Local check, no Modal and no model download:

```bash
python3 -m pytest tests/test_search.py -q
```
