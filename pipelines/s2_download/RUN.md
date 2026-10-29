# S2 bulk download

Secret `s2-api-key` (env `S2_API_KEY`), volume `rrm-data`. From the repo root.
`limit` is per dataset (`0` = all). `max_mb` > 0 stops after that many compressed MiB and writes `/s2/_test/` (not marked done).
```bash
modal run --detach pipelines/s2_download/app.py::main --datasets papers --limit 1 --max-mb 64
modal run --detach pipelines/s2_download/app.py::main --datasets papers
modal run --detach pipelines/s2_download/app.py::build_cs_ids --release latest
modal run --detach pipelines/s2_download/app.py::main --datasets papers,abstracts,tldrs,citations,embeddings-specter_v2 --concurrency 100
```
One line per shard, then `total in_mb out_mb rows container_s`. Run papers, then `build_cs_ids`, then embeddings.
