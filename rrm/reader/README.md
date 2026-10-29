# rrm/reader

When a burst returns, `prepare` spawns a background parse of those corpus ids. Opening one paper calls `paper`, which returns the cache or parses synchronously and (only then) asks SAM 3.1 for page positions.

## Order

1. Resolve the id from `rrm-data` `2026-10-20/index/display.parquet` (arXiv, DOI). If there is no arXiv id, the free Semantic Scholar Graph API supplies `externalIds` and `openAccessPdf` (1 req/s, backoff, no key).
2. arXiv e-print, if it contains real TeX: inline `\input`, expand math macros, emit the block schema, KaTeX-check every equation, render figures. A pdfpages wrapper (Adam) is not TeX.
3. Otherwise the arXiv PDF or the open-access PDF goes to MinerU 2.5 (`vlm-auto-engine`) on a separate L4 function. Equations come back as LaTeX with `source: "ocr"`.
4. Otherwise `abstract_only` (abstract + tldr). Failures set `failed` and a reason.

arXiv fetches share one clock: 1 request / 3.2 s.

## Status

`queued`, `parsing`, `done`, `abstract_only`, `failed` (plus `reason`). A finished paper is cached at `papers/{corpusid}/` on the volume: `paper.json`, `meta.json` (seconds per step, page count, equation and katex_ok counts), `figures/`, `crops/`.

## SAM

`sam-3.1` on `https://api.meta.ai/v1/responses`, key `MODEL_API_KEY`. Noun phrases `figure`, `table`, `equation`, first 30 pages, $0.0025/image. Used for PDF-only crops and for the single paper the user opens. No key or an API error leaves the parse in place and stores no crops. `prepare` does not call SAM.

## Bench

```bash
modal run rrm/reader/serve.py::bench --ids 13756489,2048380074
```

Columns are seconds for resolve, download, parse, katex, figures, ocr, sam, then a CPU / L4 / SAM dollar estimate from the 2026-10-28 Modal list price.
