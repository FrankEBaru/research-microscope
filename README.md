# Research Reading Microscope

A reading tool that turns a research question into a navigable burst of related papers, from field overview to single paper, with every sentence linked to its sources.

Data attribution: Semantic Scholar, arXiv and OpenAlex

## Modo offline (WSL)

Tres consultas grabadas, para explorar la UI en una laptop sin Modal ni Meta. Hace falta Python 3, Node ≥ 22 y `gh` con sesión (`gh auth login`). Desde esta rama:

```bash
bash scripts/offline.sh
```

Ese comando baja el Release `offline-fixtures-v1`, abre la API en `http://127.0.0.1:8787` y la UI en `http://localhost:3000`. El token es opcional (el script manda `local`; el servidor también responde sin token).

Preguntas grabadas, cópialas tal cual: `how does self-attention replace recurrence in sequence translation`, `neural radiance fields view synthesis`, `scaling laws compute dataset size language model loss`.

Cualquier otra pregunta responde `consulta no grabada`. En esas tres funcionan la ráfaga, el estado, el paper, las figuras guardadas, los recortes de las páginas grabadas, los subtemas y el panorama de esa misma pregunta. No hay búsqueda nueva, ni papers fuera de esas ráfagas, ni panorama si reescribes la pregunta, ni OCR. Ctrl+C apaga la UI y el servidor. Atribución: Semantic Scholar.

## Demo

The live demo is hybrid. The curated map, instrument, and papers stay static files (see [`apps/reader/README.md`](apps/reader/README.md)). A question typed in the demo calls the burst and the reader (see [`rrm/reader/README.md`](rrm/reader/README.md)). Empty `NEXT_PUBLIC_BURST_URL` and `NEXT_PUBLIC_READER_URL` keep today's curated mock.

One-time local setup for `bash scripts/check.sh` (the check does not install these itself):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

Node for the UI is Node ≥ 22 and `npm ci` in `apps/reader/`. The front is a static Next export (`output: "export"` in `apps/reader`). On Vercel Hobby, set the project root to `apps/reader`, Node 22, and build `npm ci && npm run build`. Put `NEXT_PUBLIC_BURST_URL`, `NEXT_PUBLIC_READER_URL`, and `NEXT_PUBLIC_RRM_DEMO_TOKEN` in the Vercel project, not in git. Restore `public/papers/` from Release `artifacts/RRM-11-reader-data-2026-10-29` before that build. This repo does not deploy.

## Semantic Scholar bulk download

`pipelines/s2_download/` streams a Semantic Scholar Datasets release into the Modal volume `rrm-data` as Zstandard Parquet. It keeps papers, abstracts, citations, and TLDRs, plus SPECTER v2 embeddings for Computer Science corpus ids. Computer Science ids (from `s2fieldsofstudy` / `fieldsOfStudy`) are stored beside the release. Raw `.gz` shards are not kept.

Download commands are in [`pipelines/s2_download/RUN.md`](pipelines/s2_download/RUN.md). The FAISS index, citation graph, and burst search commands are in [`pipelines/index_build/RUN.md`](pipelines/index_build/RUN.md). From the repo root:

```bash
modal run --detach pipelines/s2_download/app.py::main --datasets papers --limit 1
```

Semantic Scholar datasets are distributed under the ODC-BY license. Attribute the source as "Semantic Scholar".
