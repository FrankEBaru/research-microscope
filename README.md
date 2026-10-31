# Research Reading Microscope

En la máquina Frank (WSL), después de arrancar, con el venv y Node en el PATH:

```bash
source ~/projects/hackaton/activate.sh
cd ~/projects/hackaton/research-microscope && git checkout main && git pull && ./scripts/offline.sh
```

Eso baja el Release `offline-fixtures-v1` si falta, instala la UI si falta, y arranca sin Modal ni Meta. Ábrelo en el navegador de Windows: `http://localhost:3000`. Preguntas grabadas, tal cual: `how does self-attention replace recurrence in sequence translation`, `neural radiance fields view synthesis`, `scaling laws compute dataset size language model loss`. Otra pregunta responde `consulta no grabada`. El panorama de esas tres es el de Muse ya grabado. Ctrl+C apaga la UI y el servidor. Atribución: Semantic Scholar.

## Modo en vivo: scripts/live.sh

En la misma máquina, con las llaves ya cargadas. El script no imprime ni guarda el token.

```bash
source ~/projects/hackaton/activate.sh
cd ~/projects/hackaton/research-microscope
RRM_LIVE=off bash scripts/live.sh
```

`RRM_LIVE` elige el modo. Si no está, es `off`. `RRM_MAX_MINUTES` (default 30, entero ≥ 1) corta la sesión. Al salir por Ctrl+C, por un error o por ese tope, `modal`, `meta` y `full` corren `modal app stop rrm-burst`, `modal app stop rrm-reader` y `modal app list`. `off` no usa ese trap: es `scripts/offline.sh`. No se activa `RRM_DEMO_KEEP_WARM`.

| Modo | Comando | Qué hace |
|---|---|---|
| off | `RRM_LIVE=off bash scripts/live.sh` | Igual que `scripts/offline.sh`. Sin Modal ni Meta. |
| modal | `RRM_LIVE=modal bash scripts/live.sh` | `modal deploy rrm/search/serve.py` y `modal deploy rrm/reader/serve.py`. Ráfaga y lector reales. `RRM_PANORAMA_MODE=sim`. `RRM_SAM=off`: `/crops` no llama a SAM. |
| meta | `RRM_LIVE=meta bash scripts/live.sh` | Sin deploy. Datos grabados. `RRM_OFFLINE_PANORAMA=meta`: `POST /panorama` llama a Muse. `/crops` sigue grabado. |
| full | `RRM_LIVE=full bash scripts/live.sh` | Los dos deploy, con `RRM_PANORAMA_MODE=meta` y `RRM_SAM=on`. |

En `modal` y `full` hace falta `RRM_DEMO_TOKEN` en el entorno. La UI toma `NEXT_PUBLIC_BURST_URL`, `NEXT_PUBLIC_READER_URL` y ese token de la salida del deploy. En `meta` el token público queda en `local`, como el offline. Al terminar imprime el modo, los segundos y qué servicio pudo haber cobrado. No calcula dólares.

Límite de `meta`: no hay PDF en la grabación, así que los recortes no llaman a SAM. El panorama en vivo usa los `blocks` ya guardados en `papers/`. Una pregunta que no esté grabada sigue sin ráfaga (`consulta no grabada`).

A reading tool that turns a research question into a navigable burst of related papers, from field overview to single paper, with every sentence linked to its sources.

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
