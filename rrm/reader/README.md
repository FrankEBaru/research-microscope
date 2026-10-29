# rrm/reader

When a burst returns, it spawns `prepare` for the top 10 corpus ids (fire-and-forget). Opening one paper calls `paper`, which returns in the request: the cached parse, or a stub (title, authors, abstract, tldr) while the parse continues. The opened id is marked hot, so its arXiv download takes the next harvest slot ahead of those prefetch jobs. SAM is not part of opening a paper.

## Order

1. Resolve the id from `rrm-data` `2026-10-20/index/display.parquet` (arXiv, DOI). If there is no arXiv id, the free Semantic Scholar Graph API supplies `externalIds` and `openAccessPdf` (1 req/s, backoff). Optional env `S2_API_KEY` is sent as `x-api-key`. The stub makes one attempt and does not retry; a later snapshot fills gaps. A burst still uses one batch request, cached at `papers/{id}/s2.json`.
2. arXiv e-print, if it contains real TeX: inline `\input`, expand math macros, emit the block schema, KaTeX-check every equation, render figures. A pdfpages wrapper (Adam) is not TeX.
3. Otherwise the arXiv PDF or the open-access PDF goes to MinerU 2.5 (`vlm-auto-engine`) on a separate L4 function. Equations come back as LaTeX with `source: "ocr"`.
4. Otherwise `abstract_only` (abstract + tldr). Failures set `failed` and a reason.

arXiv fetches use `export.arxiv.org` and share one clock: a burst of 4 requests in 1 second, then a 1 second sleep (the rate arXiv documents for programmatic harvest). The clock is taken only to start the request; the body is read after it returns, so a slow arXiv transfer does not block the next paper. Open-access hosts are not gated. Each download allows 10 s to connect, 30 s overall, and 50 MB. On timeout the next source is tried (e-print, then the arXiv PDF, then the open-access PDF) and otherwise the paper is `abstract_only` with the reason. The S3 requester-pays bucket is not used: one paper lives in a ~500 MB month tar, and the requester pays for the whole object.

## Status

`queued`, `parsing`, `done`, `abstract_only`, `failed` (plus `reason`, `stage`, and `stages`). `stages` is `stub`, `sections`, `figures`, `crops`, each `pending`, `running`, `done`, `skipped`, or `failed`. A paper is cached at `papers/{corpusid}/` on the volume: `paper.json` (rewritten as sections, then figures, arrive), `meta.json` (seconds per step, `first_content_s`, `sections_s`, `full_s`, page count, equation and katex_ok counts), `figures/`, `crops/`.

## SAM

`GET /crops?id=&pages=0,1` (background). `sam-3.1` on `https://api.meta.ai/v1/responses`, key `MODEL_API_KEY`. Noun phrases `diagram` and `table` only, at most 4 pages per request, page index below 30, parallel calls, retries on 404, 429, and 5xx. $0.0025/image. No key or an API error leaves the parse in place. `prepare` and `paper` do not call SAM.

## Bench

```bash
modal run rrm/reader/serve.py::bench --ids 13756489,2048380074
```

Columns are seconds for resolve, download, parse, katex, figures, ocr (wall), ocr_gpu_s (summed, this is what `ocr_usd` uses), sam, then `first` (time-to-first-content), `sections`, `full`, then a CPU / L4 / SAM dollar estimate from the 2026-10-28 Modal list price, plus per-step CPU dollars. Two extra columns: `ocr_chunks` (`start-end:seconds:engine:ok|fail:attempts`) and `downloads` (`kind:seconds:ok|fail:bytes`). `ocr_engine` is the engine MinerU logged (`vllm-engine` or `transformers`). OCR splits about 4 pages per chunk (at most 8) and spawns one container per chunk (`max_containers=8`, no input concurrency, no `min_containers`). Each chunk has a 120 s limit and one retry. A failed chunk becomes a raw block; the other chunks still return in page order. Wall time much smaller than `ocr_gpu_s` means the chunks overlapped.

## QA notes (2026-10-29, Modal)

- `mineru[core]>=2.5,<3` resolves to mineru 2.7.6 with the **transformers** VLM engine (no vLLM): ~16-22 s/page on an A10 (PLOS 18 pp 292 s, Adam 15 pp 325 s). Model download is only ~10 s, load 5-15 s. Installing vLLM is the next speed step.
- L4 had no capacity for 10+ min; the function now falls back to A10G (higher price than the L4 figure in the bench columns).
- SAM: the API returns 404 `model_not_found` on many valid calls, so the client retries. `figure` found nothing on paper pages; `diagram` found every panel. Crops moved off `paper` onto `crops?id=&pages=`, phrases `diagram` and `table` only.
