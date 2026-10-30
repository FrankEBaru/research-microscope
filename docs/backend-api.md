# Backend HTTP

Two Modal apps. Each one exposes a single ASGI app named `api`. The real host is the URL printed by `modal deploy`. Do not commit it.

Every route checks `RRM_DEMO_TOKEN` (`rrm/demo_guard.py`). Send it as `X-RRM-Demo`. `GET /file` also accepts the query `k`, because an `<img>` cannot set a header. An empty token is 401 and does not read the volume or spawn work. An `Origin` outside `ALLOWED_ORIGINS` is 403. A request with no `Origin` is allowed when the token matches.

Reader, app `rrm-reader`, function `api`:

- `GET /paper?id=`
- `GET /status?ids=` (comma-separated corpus ids; unknown ids are `missing`, except a top-10 id just returned by `/burst`, which is `queued` until its `meta.json` commit lands)
- `POST /prepare` with `{"ids": []}`
- `GET /crops?id=&pages=`
- `POST /panorama` with `{"question": str, "ids": [corpusid, ...]}` (at most 20 ids, question up to 500 characters). Returns `[{id, statement, selections: [{paper, quote}]}]`. It only reads papers that are `done` or `abstract_only` and never spawns work. 400 for a bad body. A quote is a sentence from that paper's `blocks[].sents`. The handler is not the UI gate: `validateSelections` still rejects a quote that does not occur exactly once in its paper.
- `GET /file?id=&name=&k=` (a file under `papers/{id}/figures/` or `papers/{id}/crops/`, or 404)

`RRM_PANORAMA_MODE` is `sim` (default) or `meta`.

`sim` ports `apps/reader/src/lib/musesim.js` and picks sentences by term overlap. It does not call a model. `meta` calls Muse Spark (`muse-spark-1.3-contributor`, the same client as `rrm/search/split.py`). The model sees numbered candidate sentences (filtered with `_sentences` and `themes_of`, capped by count and characters) and returns indexes. The server rebuilds each quote from that index, then drops a pick that is out of range, repeated, or not found exactly once in its paper. The statement is the model's. Each claim also has `mode` (`sim` or `meta`) and `fallback` (bool). A timeout, transport error, or invalid JSON falls back to `sim` with `fallback` true and does not change the list shape. `RRM_PANORAMA_TIMEOUT` is the Muse call timeout in seconds (default 40, capped at 45). The browser waits `NEXT_PUBLIC_RRM_PANORAMA_TIMEOUT_MS` (default 45000). The server cap sits under that wait so a slow Muse call still returns the sim fallback. Token counts are logged as `panorama_meta` (`prompt_tokens`, `completion_tokens`, `total_tokens`). The API key is not logged.

`meta` is not the demo default. Every panorama request would spend Meta tokens, and a cold or slow call is the wrong default for a demo that already labels this step as simulated. Set `RRM_PANORAMA_MODE=meta` on the reader deploy to turn it on.

`prefetch` stays a Modal function named `prefetch`. The UI does not call `/crops` or `/prepare`.

Burst, app `rrm-burst`, class `BurstSearch`, method `api`:

- `GET /burst?q=&n=`
- `GET /subtopics?q=`

The UI calls `/burst` with `n=10`, then `/status`, `/paper`, `/file`, and `/panorama`. It does not call `/subtopics`. `run_burst` is a Modal method with no public URL.

`/status` rows include `ocr_gpu_s` and `ocr_invoked_at` when the reader has them. `missing` means no `meta.json` yet and the id was not in the top 10 noted by the latest bursts. That note is a single dict write on the burst handler; the volume commit runs after `/burst` has returned.

## Demo window

Cold starts of the burst container were 100–131s when it scaled down between prompts. Deploy with `RRM_DEMO_KEEP_WARM=1` (shell env of `modal deploy`, not a secret) to set `scaledown_window` to 1200s on the burst class and the reader HTTP app. That is Modal's maximum. `min_containers` stays 0, including when the flag is unset. GPU OCR is not kept warm. During the window, `bash scripts/warm.sh` pings `/burst` and `/status` every 4 minutes with `RRM_DEMO_TOKEN`. Unset the flag and redeploy when the demo is over. See `scripts/warm.sh`.

The 12-prompt stop rule is `scripts/e2e_rules.py` (not the PR #9 wording). A paper counts toward the two-OCR cap only when `ocr_gpu_s > 0` and `ocr_invoked_at` is at or after the unix time recorded before the first prompt.
