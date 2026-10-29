# Research Reading Microscope

A reading tool that turns a research question into a navigable burst of related papers, from field overview to single paper, with every sentence linked to its sources.

Data attribution: Semantic Scholar, arXiv and OpenAlex

## Semantic Scholar bulk download

`pipelines/s2_download/` streams a Semantic Scholar Datasets release into the Modal volume `rrm-data` as Zstandard Parquet. It keeps papers, abstracts, citations, and TLDRs, plus SPECTER v2 embeddings for Computer Science corpus ids. Computer Science ids (from `s2fieldsofstudy` / `fieldsOfStudy`) are stored beside the release. Raw `.gz` shards are not kept.

Commands are in [`pipelines/s2_download/RUN.md`](pipelines/s2_download/RUN.md). From the repo root:

```bash
modal run --detach pipelines/s2_download/app.py::main --datasets papers --limit 1
```

Semantic Scholar datasets are distributed under the ODC-BY license. Attribute the source as "Semantic Scholar".
