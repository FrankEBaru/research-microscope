# Backend HTTP

Two Modal apps. Each one exposes a single ASGI app named `api`. The real host is the URL printed by `modal deploy`. Do not commit it.

Every route checks `RRM_DEMO_TOKEN` (`rrm/demo_guard.py`). Send it as `X-RRM-Demo`. `GET /file` also accepts the query `k`, because an `<img>` cannot set a header. An empty token is 401 and does not read the volume or spawn work. An `Origin` outside `ALLOWED_ORIGINS` is 403. A request with no `Origin` is allowed when the token matches.

Reader, app `rrm-reader`, function `api`:

- `GET /warm`
- `GET /paper?id=`
- `GET /status?ids=` (comma-separated corpus ids; unknown ids are `missing`, except a top-10 id just returned by `/burst`, which is `queued` until its `meta.json` commit lands)
- `POST /prepare` with `{"ids": [], "front": false}`. `front: true` puts those ids at the front of the reader queue.
- `GET /crops?id=&pages=`
- `POST /panorama` with `{"question": str, "ids": [corpusid, ...]}` (at most 20 ids, question up to 500 characters). Returns `[{id, statement, selections: [{paper, quote}]}]`. It only reads papers that are `done` or `abstract_only` and never spawns work. 400 for a bad body. A quote is a sentence from that paper's `blocks[].sents`. The handler is not the UI gate: `validateSelections` still rejects a quote that does not occur exactly once in its paper.
- `GET /file?id=&name=&k=` (a file under `papers/{id}/figures/` or `papers/{id}/crops/`, or 404)

`RRM_PANORAMA_MODE` is `sim` (default) or `meta`.

`sim` ports `apps/reader/src/lib/musesim.js` and picks sentences by term overlap. It does not call a model. `meta` calls Muse Spark (`muse-spark-1.3-contributor`, the same client as `rrm/search/split.py`). The model sees numbered candidate sentences (filtered with `_sentences` and `themes_of`, capped by count and characters) and returns indexes. The server rebuilds each quote from that index, then drops a pick that is out of range, repeated, or not found exactly once in its paper. The statement is the model's. Each claim also has `mode` (`sim` or `meta`) and `fallback` (bool). A timeout, transport error, or invalid JSON falls back to `sim` with `fallback` true and does not change the list shape. `RRM_PANORAMA_TIMEOUT` is the Muse call timeout in seconds (default 40, capped at 45). The browser waits `NEXT_PUBLIC_RRM_PANORAMA_TIMEOUT_MS` (default 45000). The server cap sits under that wait so a slow Muse call still returns the sim fallback. Token counts are logged as `panorama_meta` (`prompt_tokens`, `completion_tokens`, `total_tokens`). The API key is not logged.

`meta` is not the demo default. Every panorama request would spend Meta tokens, and a cold or slow call is the wrong default for a demo that already labels this step as simulated. Set `RRM_PANORAMA_MODE=meta` on the reader deploy to turn it on.

`prefetch` stays a Modal function named `prefetch`. In `core` the UI does not call `/crops`. «quiero leer este» calls `POST /prepare` with `front: true`.

Burst, app `rrm-burst`, class `BurstSearch`, method `api`:

- `GET /warm` returns after the container has loaded the index. Body: `{"ready": true, "features": "core"|"all", "loaded": [...]}`. It does not run a search.
- `GET /burst?q=&n=`
- `GET /subtopics?q=` (in `core`, returns `subtopics: []` and `reason: "core"` and does not call Muse)

`RRM_FEATURES` is `core` (default) or `all`. `core` does not call Meta: `/subtopics` skips Muse, and the reader skips `/panorama` and SAM. `all` is the previous surface. The UI reads `NEXT_PUBLIC_RRM_FEATURES` (same values). `scripts/live.sh` uses `core` for `off` and `modal`, and `all` for `meta` and `full` when the variable is unset.

A repeated question is served from `rrm-cache/burst/<sha256>.json` on the `rrm-data` volume. The key is the question in lower case with collapsed whitespace. The file holds the burst payload and the last paper-status rows. `/status?ids=&q=` fills a `missing` id from that file and writes newer rows after the response. The browser keeps the last 10 questions in `localStorage` (`rrm.questions.v1`), and in IndexedDB (`rrm-questions`) when `localStorage` refuses the write.

`POST /prepare` accepts `{"ids": [], "front": true}`. `front` moves those ids ahead of the prefetch tail. The UI button «quiero leer este» sends that and does not wait for the parse. Top 10 still run in the background after `/burst` (LaTeX first; OCR only when there is no LaTeX).

`/burst` also returns `layout` for the papers in that response. With a stored SPECTER2 vector for every paper, `layout.method` is `specter2-pca`: x and y are a 2D PCA of those vectors (same scale on both axes), `variance` is the share of variance on each axis, `groups` join papers whose cosine is at least `cosine_min` (0.80), and `similarity` is each paper's nearest other paper when that cosine is at least `neighbor_min` (0.50). Citation `links` are only edges whose both ends are in the returned papers (`kind: "citation"`). If any paper has no vector, the method is not PCA. It is `year-citation` when at least two papers have a year and there is a citation inside the set (x is the year; a missing year sits in `gutter_x`, listed in `years.missing`), `citation-graph` when there are citations but not enough years, or `rank-circle` when there is no citation inside the set. A `nudged` point was moved so it would not sit on another point; that gap is not a distance. The question cache stores the burst without `layout`. The handler adds `layout` on the way out, including a cache hit. Offline recordings have no vectors, so they get the citation or rank layout.

Burst rows include `tldr` and `abstract` from the display table when those columns exist. The display table built for this index has `tldr`. Abstracts live in a separate dataset and are not loaded into the burst process.

`GET /file` sends `Cache-Control: public, max-age=86400`. The reader HTTP app allows 8 concurrent inputs so figure requests are not stuck behind `/status`. The offline server uses the same cache header on `/file`.

## Cold start

`BurstSearch` sets `enable_memory_snapshot=True`. `@modal.enter(snap=True)` loads FAISS, faiss ids, the citation graph, `node_meta`, `display.parquet`, `display_ext.parquet`, and the SPECTER2 query encoder, then encodes one short string. `@modal.enter(snap=False)` only reloads the volume. `min_containers` is not set. The first container after a deploy still pays that load (and writes the snapshot). Later cold starts are expected to restore the snapshot instead of reading those artifacts again. That effect is not measured in this change. Image pull and scheduling still happen. A real `modal deploy` has to confirm the snapshot is created and that a later cold `/warm` is shorter than the 100–131 s starts measured on 29 Oct.

The UI calls `/warm` on burst and on the reader when it opens, then `/burst` with `n=10`, then `/status`, `/paper`, and `/file`. In `all` it also calls `/panorama`. In `core` it does not call `/panorama`, `/subtopics`, or `/crops`. `run_burst` is a Modal method with no public URL.

`/status` rows include `ocr_gpu_s` and `ocr_invoked_at` when the reader has them. `missing` means no `meta.json` yet and the id was not in the top 10 noted by the latest bursts. That note is a single dict write on the burst handler; the volume commit runs after `/burst` has returned.

## Demo window

Cold starts of the burst container were 100–131s when it scaled down between prompts. Deploy with `RRM_DEMO_KEEP_WARM=1` (shell env of `modal deploy`, not a secret) to set `scaledown_window` to 1200s on the burst class and the reader HTTP app. That is Modal's maximum. `min_containers` stays 0, including when the flag is unset. GPU OCR is not kept warm. During the window, `bash scripts/warm.sh` pings `/burst` and `/status` every 4 minutes with `RRM_DEMO_TOKEN`. Unset the flag and redeploy when the demo is over. See `scripts/warm.sh`.

The 12-prompt stop rule is `scripts/e2e_rules.py` (not the PR #9 wording). A paper counts toward the two-OCR cap only when `ocr_gpu_s > 0` and `ocr_invoked_at` is at or after the unix time recorded before the first prompt.
