# rrm/reader

When a burst returns, it spawns `prepare` for the top 10 corpus ids (fire-and-forget). Opening one paper calls `paper`, which returns in the request: the cached parse, or a stub (title, authors, abstract, tldr) while the parse continues. The opened id is marked hot, so its arXiv download takes the next harvest slot ahead of those prefetch jobs. SAM is not part of opening a paper.

## Order

1. Resolve the id from `rrm-data` `2026-10-20/index/display.parquet` (arXiv, DOI). The free Semantic Scholar Graph API supplies gaps (`externalIds`, `openAccessPdf`, authors). One request per second, backoff, optional `S2_API_KEY` (`x-api-key`). The stub is written before any S2 retry; a retry fills the stub afterwards. Without a key the batch request and `papers/{id}/s2.json` cache are unchanged.
2. arXiv e-print and the PDF route start together. Real TeX is parsed (inline `\input`, math macros, KaTeX, figures). A pdfpages wrapper (Adam) is not TeX. The PDF route races the arXiv PDF against the S2 `openAccessPdf` URL (first valid PDF, the other cancelled) and runs MinerU. Whichever parse finishes first is published (`source` is `latex` or `ocr`). A later LaTeX parse replaces OCR (`upgraded_from` names the previous source). OCR never replaces LaTeX.
3. MinerU 2.5 (`vlm-auto-engine`) runs on its own GPU container per ~4 pages, up to 8 containers, 120s per attempt and one retry. A failed chunk is a raw block; the other pages return in order. The container log line is `mineru chunk=start-end engine=vllm|transformers seconds=…`.
4. Otherwise `abstract_only` (abstract + tldr). Failures set `failed` and a reason.

arXiv fetches use `export.arxiv.org` and share one clock: a burst of 4 requests in 1 second, then a 1 second sleep (the rate arXiv documents for programmatic harvest). The clock is taken only to open the request, not while the body transfers, and it does not apply to non-arXiv PDF hosts. Each download gives up after 10s connect / 30s total or 50MB and the parse falls back to the next source. The S3 requester-pays bucket is not used: one paper lives in a ~500 MB month tar, and the requester pays for the whole object.

## Status

`queued`, `parsing`, `done`, `abstract_only`, `failed` (plus `reason`, `stage`, and `stages`). `stages` is `stub`, `sections`, `figures`, `crops`, each `pending`, `running`, `done`, `skipped`, or `failed`. A paper is cached at `papers/{corpusid}/` on the volume: `paper.json` (rewritten as sections, then figures, arrive), `meta.json` (seconds per step, `first_content_s`, `sections_s`, `full_s`, page count, equation and katex_ok counts), `figures/`, `crops/`.

## SAM

`GET /crops?id=&pages=0,1` (background). `sam-3.1` on `https://api.meta.ai/v1/responses`, key `MODEL_API_KEY`. Noun phrases `diagram` and `table` only, at most 4 pages per request, page index below 30, parallel calls, retries on 404, 429, and 5xx. $0.0025/image. No key or an API error leaves the parse in place. `prepare` and `paper` do not call SAM.

## Bench

```bash
modal run rrm/reader/serve.py::bench --ids 13756489,2048380074
```

Columns are seconds for resolve, download, parse, katex, figures, ocr (wall), ocr_gpu_s (summed, this is what `ocr_usd` uses), sam, then `first` (time-to-first-content), `sections`, `full`, then a CPU / L4 / SAM dollar estimate from the 2026-10-28 Modal list price, plus per-step CPU dollars. `ocr_chunks` is `start-end:seconds:engine:ok` per chunk (engine is `vllm` or `transformers`). `downloads` is `source:seconds:ok` per fetch (e-print, arxiv_pdf, oa_pdf). OCR is one container per chunk of about 4 pages, at most 8, merged in page order.

## QA notes (2026-10-29, Modal)

- `mineru[core]>=2.5,<3` resolves to mineru 2.7.6 with the **transformers** VLM engine (no vLLM): ~16-22 s/page on an A10 (PLOS 18 pp 292 s, Adam 15 pp 325 s). Model download is only ~10 s, load 5-15 s. Installing vLLM is the next speed step.
- L4 had no capacity for 10+ min; the function now falls back to A10G (higher price than the L4 figure in the bench columns).
- SAM: the API returns 404 `model_not_found` on many valid calls, so the client retries. `figure` found nothing on paper pages; `diagram` found every panel. Crops moved off `paper` onto `crops?id=&pages=`, phrases `diagram` and `table` only.
