# RRM-15: Plan for a working end-to-end demo

Status: plan only. This document is the only change on `plan/rrm-15`. No application code was edited, no branch was merged, and Modal and the Meta API were not called.

Verified against the code on 2026-10-29, tips:

| Piece | Ref | Tip |
|---|---|---|
| `main` | `origin/main` | `1c0a3e6` |
| PR #1 S2 download | `cursor/s2-bulk-download-777d` | `045a3ec` |
| PR #2 burst | `cursor/rrm-3-burst-search-440b` | `73f6692` |
| PR #3 reader | `cursor/rrm-7-reader-cee2` | `a935df8` |
| PR #4 instant reader | `cursor/rrm-12-instant-4512` | `d8944b3` |
| PR #5 stale RRM-13 | `cursor/rrm-13-reader-speed-210e` | `1f9381a` |
| PR #6 current backend | `cursor/rrm-13-reader-speed-fa6f` | `7b7883d` |
| UI (no PR) | `claude/adoring-hypatia-hd4bvs` | `a0a332a` |
| PR #7 release docs | `cursor/reader-data-release-docs-5872` | `c2756a8` |

PR #7's base is the UI branch, not `main`. Its diff against the UI tip is four files: `AGENTS.md`, `apps/reader/CHANGELOG.md`, `apps/reader/README.md`, `apps/reader/scripts/build_data.py`.

Labels: **[V]** checked in the code this session, or a number already measured in the attached QA notes. **[I]** inference. Do not treat [I] as a measurement.

## 0. Executive summary

Land every live branch on `integration/e2e` in the order in §1, then stop. Do not merge that branch to `main` until Franklin approves. The dry-run of that order had no content conflicts. PR #5 conflicts with PR #6 in seven files and is not merged.

The demo is hybrid. Curated papers stay static files. A new question calls the Modal burst and reader. The UI does not call `/subtopics` or `/crops`, so the demo does not spend the Meta API.

The backend work that is actually missing is small: serve figure files, require one shared demo token, and send CORS for a hardcoded origin list. The UI work is the `ref` inline, equation numbers, corpus-id routing, and polling. Equation numbers and `ref` stay UI-side. Block ids are already stable from sections to figures **[V]**; the stub is a different document and the UI remounts once.

Cheap tests are one command, local fixtures from a small GitHub Release, no Modal. The Modal rehearsal is a later ticket, budget ≤ $5, hard stop $10, and only after Franklin approves the spend.

Host the static Next export on Vercel. Leave the API on Modal.

## 1. Merge strategy

Owner of the merge: the RRM-16 agent. Do it on a new branch `integration/e2e` cut from `origin/main`. Do not push to `main`. Do not click Merge on the existing PRs. When `integration/e2e` later lands on `main`, GitHub will see the original commits as ancestors and can close PRs #1, #2, #3, #4, #6, and #7. That landing is not part of RRM-16.

### 1.1 Why this order

The stack is not "PR #2 contains PR #1's tip". `git merge-base` of PR #1 and PR #2 is `5484be9`. Commit `045a3ec` ("Skip a failed volume reload in a reused container") is only on PR #1 **[V]**. It edits `pipelines/s2_download/app.py` (try/except around `vol.reload()`). Later branches do not touch that hunk. Merging PR #1 first is what keeps the fix. Merging PR #6 alone onto `main` would drop it.

PR #4 already contains the merge commit `a630b7a` of the burst tip into the reader line. PR #3's tip `a935df8` is an ancestor of PR #4. PR #6's tip `7b7883d` is PR #4 plus four commits. So steps 3–5 are fast in content: each one only adds the commits the previous step does not have.

The UI and the backend do not touch the same files **[V]**. `git diff --name-only origin/main...origin/cursor/rrm-13-reader-speed-fa6f` is `rrm/`, `pipelines/`, `tests/`, `eval/`, and root `README.md`. The UI plus PR #7 is `apps/reader/` and `AGENTS.md`. The intersection is empty. Front and back really did stay apart.

### 1.2 Dry-run already done

Method: a scratch clone of this repo, `git merge --no-commit --no-ff <ref>`. A clean merge was committed only inside that clone so the next step saw the real tree. Nothing was pushed. The conflict case in §1.4 was aborted with `git merge --abort`.

Result of the order below, every step **clean**, no unmerged paths:

| Step | Command ref | Result |
|---|---|---|
| 1 | `origin/cursor/s2-bulk-download-777d` | clean |
| 2 | `origin/cursor/rrm-3-burst-search-440b` | clean |
| 3 | `origin/cursor/rrm-7-reader-cee2` | clean |
| 4 | `origin/cursor/rrm-12-instant-4512` | clean |
| 5 | `origin/cursor/rrm-13-reader-speed-fa6f` | clean |
| 6 | `origin/claude/adoring-hypatia-hd4bvs` | clean |
| 7 | `origin/cursor/reader-data-release-docs-5872` | clean |

After step 7 the scratch tree matched PR #6 everywhere except `pipelines/s2_download/app.py`, and that diff was exactly the four-line `045a3ec` hunk **[V]**. `apps/reader/` and `AGENTS.md` matched PR #7 with an empty diff **[V]**.

### 1.3 Commands for the RRM-16 agent

```bash
git fetch origin main \
  cursor/s2-bulk-download-777d \
  cursor/rrm-3-burst-search-440b \
  cursor/rrm-7-reader-cee2 \
  cursor/rrm-12-instant-4512 \
  cursor/rrm-13-reader-speed-fa6f \
  claude/adoring-hypatia-hd4bvs \
  cursor/reader-data-release-docs-5872
git checkout -B integration/e2e origin/main
git merge --no-ff origin/cursor/s2-bulk-download-777d -m "Merge PR #1 S2 bulk download"
git merge --no-ff origin/cursor/rrm-3-burst-search-440b -m "Merge PR #2 burst search"
git merge --no-ff origin/cursor/rrm-7-reader-cee2 -m "Merge PR #3 reader"
git merge --no-ff origin/cursor/rrm-12-instant-4512 -m "Merge PR #4 instant reader"
git merge --no-ff origin/cursor/rrm-13-reader-speed-fa6f -m "Merge PR #6 reader speed"
git merge --no-ff origin/claude/adoring-hypatia-hd4bvs -m "Merge reader UI"
git merge --no-ff origin/cursor/reader-data-release-docs-5872 -m "Merge PR #7 reader release docs"
```

If step 1–7 is clean, as the dry-run was, commit each merge and push `integration/e2e`. Do not merge `integration/e2e` into `main` in RRM-16.

There is no UI pull request. Step 6 merges the branch by ref.

### 1.4 Stale branch and PR #7

**PR #5 / `cursor/rrm-13-reader-speed-210e`: do not merge. Close the PR. Delete the branch** after Franklin confirms (§12). It is one commit, `1f9381a`, on top of PR #4. PR #6 started from the same parent and replaced that attempt (parallel OCR, raced downloads, LaTeX authors, MinerU only when the e-print has no LaTeX, chunk timeout 180 s, `S2_API_KEY` passed into the container).

Dry-run: merging `210e` onto PR #4 is clean. Merging PR #6 on top of that **conflicts** in:

- `rrm/reader/README.md`
- `rrm/reader/fetch.py`
- `rrm/reader/latex.py`
- `rrm/reader/ocr.py`
- `rrm/reader/pipeline.py`
- `rrm/reader/serve.py`
- `tests/test_reader.py`

Those conflicts are the two RRM-13 attempts editing the same functions (`_get`, download timeouts, `parse` publish, MinerU chunk timeout, the README's OCR paragraph). Resolution if a tree already contains both: keep the PR #6 side of all seven files. Do not hand-merge `1f9381a` into PR #6. There is no unique behavior in `210e` that the demo needs.

**PR #7: do merge**, as step 7, after the UI branch. It is the release-cache instructions for `artifacts/RRM-11-reader-data-2026-10-29`. Do not retarget it onto `main` by itself and do not skip the UI branch: its parent is `a0a332a`, and the curated app lives in that history.

## 2. Cleanup after the merge

Owner: RRM-16 agent. Only the items below. Do not bump Next, React, Modal, MinerU, or torch. Do not reformat.

### 2.1 Docs that disagree with the code

`CHUNK_TIMEOUT_S = 180` in `rrm/reader/ocr.py` **[V]**. Three texts still say 120 s and must be edited to 180 s, with no other wording change:

- `rrm/reader/ocr.py` comment above `CHUNK_TIMEOUT_S` ("killed at 120s").
- `rrm/reader/serve.py` comment on `ocr_one` ("stops an attempt at 120s"). The function timeout stays `400`.
- `rrm/reader/README.md` sentence "120s per attempt".

`GET /status` returns `{"id", "status": "missing"}` when `papers/{id}/meta.json` is absent (`rrm/reader/serve.py`, `status`) **[V]**. `rrm/reader/README.md` §Status does not list `missing`. Add `missing` to that sentence.

### 2.2 README and AGENTS.md

Root `README.md` after the merge still describes only the S2 download. Add a short "Demo" section that points at `apps/reader/README.md` and `rrm/reader/README.md` and states that the live demo is hybrid (§3). Do not copy the endpoint contract into the root README.

`AGENTS.md` on the UI branch already allows tests inside `apps/reader/`. After RRM-16, add one sentence: `bash scripts/check.sh` is the repo check; it does not call Modal, Semantic Scholar, arXiv, or Meta. The "no tests yet" line stays in force for everything that check does not cover. Do not weaken the spend rules.

### 2.3 Dependency file

There is no root requirements file. Modal images install their own packages inside `rrm/search/serve.py` (`image`) and `rrm/reader/serve.py` (`cpu_image`, `gpu_image`). Add `requirements-dev.txt` with the packages the local check imports and the images already name, unpinned: `pytest`, `numpy`, `pyarrow`, `faiss-cpu`. Do not add `torch`, `transformers`, `modal`, `mineru`, or `pymupdf`. `faiss` is imported inside `tests/test_search.py::test_faiss_search_and_merge` only.

One-time setup, written in the root README, not run by the check itself:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

Node for the UI tests is already declared: Node ≥ 22, `npm ci` in `apps/reader/`. The cheap check does not need Playwright or pandoc.

## 3. How the UI talks to the backend

Decision for the demo: **hybrid**, which is option (c) in the integration note and what the UI contract already accepts.

- Curated map, instrument, companion, Kaplan/Chinchilla slider, and the papers in `apps/reader/content/` stay static. They load from `/papers/_content.json` and `/papers/{arxivId}.json` as `Engine.tsx` does today (`fetch` in the second `useEffect`). Restore that data from Release `artifacts/RRM-11-reader-data-2026-10-29` (asset `reader-data-2026-10-29.tar.gz`, 41,505,374 bytes, sha256 `c1ac80888eec76e3c8f46f1e77431fed7739999496d9210b8453d694cc4c7b07`) **[V, release metadata]**. Do not commit it.
- A question typed in the demo calls the live API. Empty `NEXT_PUBLIC_BURST_URL` and `NEXT_PUBLIC_READER_URL` means today's mock. That is a build-time switch, not a settings screen.

Two apps stay two apps. Burst is a 32 GB CPU class (`BurstSearch` in `rrm/search/serve.py`). The reader is separate functions. Do not fold them into one Modal app.

### 3.1 URL shape

Today each `@modal.fastapi_endpoint` is its own host, path `/` **[V, code; the workspace prefix was observed in deploy logs, not re-checked here]**. A browser preflight is `OPTIONS`. Those decorators declare one method, so a custom header would fail the preflight. Replace the public HTTP surface with one FastAPI app per Modal app, `CORSMiddleware` included. Keep non-HTTP functions as they are.

`rrm/reader/serve.py`:

- Add `@app.function(...) @modal.asgi_app()` named `api`. Same `cpu_image`, volume, `timeout=60`, and `secret` as `paper`.
- Routes on that app: `GET /paper`, `GET /status`, `POST /prepare`, `GET /crops`, `GET /file`.
- Move the bodies of `paper`, `status`, `prepare`, and `crops` into plain functions the routes call. Delete the `@modal.fastapi_endpoint` wrappers so the old hosts disappear.
- Leave `prefetch`, `parse_one`, `ocr_one`, and `crops_for` as Modal functions. `rrm/search/serve.py` `_prefetch_reader` does `modal.Function.from_name("rrm-reader", "prefetch").spawn(ids)`. That name stays.

`rrm/search/serve.py`:

- Add `@modal.asgi_app()` method `api` on `BurstSearch` (the FAISS index must stay in the class; `start` already loads it).
- Routes: `GET /burst`, `GET /subtopics`. Both call the existing `_answer` and the existing `subtopics` body.
- Remove `@_endpoint` from `burst` and `subtopics`.
- The local entrypoint `main()` calls `BurstSearch().burst.remote`. Add `@modal.method() def run_burst(self, q: str, n: int = 50)` that returns `self._answer(q, n)`, and point `main()` at `run_burst.remote`. No public URL on `run_burst`.

Expected hosts, from the current slug pattern `<workspace>--<app>-<class>-<method>` **[I for the new names; the old slugs are the pattern already documented]**. The E2E run reads the real URL from `modal deploy` output. Do not hardcode the workspace in git.

```
https://<workspace>--rrm-burst-burstsearch-api.us-east.modal.run/burst
https://<workspace>--rrm-burst-burstsearch-api.us-east.modal.run/subtopics
https://<workspace>--rrm-reader-api.us-east.modal.run/paper
https://<workspace>--rrm-reader-api.us-east.modal.run/status
https://<workspace>--rrm-reader-api.us-east.modal.run/prepare
https://<workspace>--rrm-reader-api.us-east.modal.run/crops
https://<workspace>--rrm-reader-api.us-east.modal.run/file
```

`/subtopics` and `/crops` stay deployed and guarded. The UI does not call them (§3.6).

### 3.2 Demo token and CORS

New module `rrm/demo_guard.py`, imported by both serve modules. No config file, no env-based origin list.

```python
ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
)
```

Add the Vercel origin as one more literal in that tuple only after Franklin names the hostname (§12). Until then, browser calls work from those four origins only.

Token: environment variable `RRM_DEMO_TOKEN`, injected the same way as `S2_API_KEY` (`modal.Secret.from_dict` when `modal.is_local()`, in both `rrm/search/serve.py` and `rrm/reader/serve.py`). Never write the value into the repo, a log, or a Release.

`check(header, query)`:

- Read `RRM_DEMO_TOKEN`. If it is empty, return 401. A deploy without the token fails closed and cannot spend CPU, GPU, or Meta.
- Accept the token from header `X-RRM-Demo` or, for `/file` only, query `k`. Compare with `hmac.compare_digest`.
- Missing or wrong token: 401, no body from the volume, no `spawn`.
- If the request has an `Origin` header and it is not in `ALLOWED_ORIGINS`: 403.
- Requests with no `Origin` (curl, the E2E script) are allowed when the token matches. CORS is not the auth.

CORSMiddleware on both FastAPI apps: `allow_origins=list(ALLOWED_ORIGINS)`, `allow_methods=["GET", "POST", "OPTIONS"]`, `allow_headers=["X-RRM-Demo", "Content-Type"]`, `allow_credentials=False`. Echo the request origin only when it is in the tuple. Do not use `*`.

This is demo-grade. The token will be inside the static JS bundle (`NEXT_PUBLIC_RRM_DEMO_TOKEN`), so anyone who can load the site can read it. It stops a person who only has the `modal.run` URL. It does not stop someone who can read the bundle. Say that in `rrm/reader/README.md` in one sentence. Do not build accounts, rotation, or a proxy.

`/file` needs `k` on the query because an `<img src>` cannot set `X-RRM-Demo`.

Apply the guard to every route, including `/status` and `/file`. `/subtopics` and `/crops` stay guarded even though the UI will not call them.

### 3.3 `GET /file`

Owner: RRM-16, in `rrm/reader/serve.py`, function `resolve_figure(papers_root, corpusid, name) -> Path | None`. The route calls it and returns `FileResponse` or 404.

Rules, locked by the test in §4:

- `corpusid` is digits only.
- `name` matches `^[A-Za-z0-9._-]{1,180}$`. Reject empty, `/`, `\`, and `..`.
- Open `papers/{id}/figures/{name}`, else `papers/{id}/crops/{name}`. Nothing else (`meta.json`, `source.pdf`, `paper.json` are not served).
- Content-Type from the suffix: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.txt`. Anything else 404.
- `Cache-Control: public, max-age=86400`.
- 404 when the file is not on the volume yet (the UI shows a loading box during stage `sections`).

`materialize_figures` in `rrm/reader/latex.py` already writes those PNGs and replaces `images` with the file name **[V]**. At stage `sections`, `images` can still be the raw include path (`_fig_block` stores the `\includegraphics` path, and `offer()` publishes before `materialize_figures`). The UI treats a name that fails the regex, or a 404, as "cargando figura", and uses `/file` once the name is a single file name.

### 3.4 UI client

New file `apps/reader/src/lib/backend.js` (plain JS, same style as `bibtex.js`, so `node --test` can import it). `Paper.tsx` and `Engine.tsx` call it. No new npm dependency.

Exports:

- `liveEnabled()` — true when both `NEXT_PUBLIC_BURST_URL` and `NEXT_PUBLIC_READER_URL` are non-empty.
- `paperKey(paper)` — `String(paper.corpusid)` when `corpusid` is a number, otherwise `paper.arxivId`.
- `figureUrl(id, name)` — if `name` starts with `/`, return it (curated mock). If not live, return `/papers/${id}/${name}`. If live, return `${READER}/file?id=${id}&name=${encodeURIComponent(name)}&k=${token}`.
- `burst(q)` — `GET ${BURST}/burst?q&n=10` with header `X-RRM-Demo`. `n` is the literal 10.
- `status(ids)` — `GET ${READER}/status?ids=` comma-joined.
- `paper(id)` — `GET ${READER}/paper?id=`.

Do not export `subtopics` or `crops`.

Build fails in `backend.js` if `liveEnabled()` is true and `NEXT_PUBLIC_RRM_DEMO_TOKEN` is empty (throw at import). The static export inlines `NEXT_PUBLIC_*` (`apps/reader/next.config.mjs` is `output: "export"`). Changing a URL means a new Vercel build. That is acceptable for the demo.

### 3.5 What the screen does

Owner: RRM-16, mostly `Engine.tsx`, `Paper.tsx`, `MapView.tsx`.

Curated path, URLs empty: no behavior change. `npm run verify` and the existing e2e stay green.

Live path:

1. The top bar gets one text input. Submit calls `burst(q)`. While the promise is pending for more than 2 s, show the sentence `calentando el motor…`. Cold burst is 54–103 s **[V, QA]**. Do not use a silent spinner.
2. Render `papers` (title, year, venue, citationcount). Rows have `corpusid` and no `arxivId` **[V, `BurstSearch._rows`]**. Key them with `paperKey`.
3. Draw `edges` as lines. Place nodes on a circle in rank order. Caption: `aristas = citas (Semantic Scholar); el orden en el círculo es el ranking, no un mapa semántico`. Do not add a layout library and do not ask the backend for coordinates.
4. Footer on the live area: `Datos de papers y citas: Semantic Scholar`. The paper page keeps the arXiv line it already has. AGENTS.md requires the Semantic Scholar attribution on the surface that shows S2 data.
5. Poll `status` every 1.5 s for the top 10 until each row is `done`, `abstract_only`, or `failed`. `missing` and `queued` draw a grey node `en cola`. Do not block the other nodes.
6. Opening a paper calls `paper(id)` once, then again only when `stage` changes, every 2 s, until `done`, `abstract_only`, or `failed`.
7. Stage display, matching the UI contract:

| status / stage | UI |
|---|---|
| `missing`, `queued` | grey, `en cola` |
| `stub` | title, authors, abstract block `abs`, chip `solo abstract · cargando texto completo…` |
| `sections` | text; figure boxes `cargando figura` |
| `figures`, `done` | figures via `figureUrl`; no banner |
| `abstract_only` | chip `solo abstract: sin LaTeX ni PDF usable`; link to arXiv if `arxivId` is non-empty, otherwise `https://www.semanticscholar.org/paper/{corpusid}` |
| `failed` | `reason` plus the same link; the rest of the burst stays usable |
| `source === "ocr"` | band `leído por OCR: puede haber errores en ecuaciones` |

8. A control `volver a la ráfaga curada` clears the live query and returns to `content/map.json`. The curated map is not replaced by `/burst.edges`.
9. One-minute blurb for a live paper: the first abstract sentence that matches `we propose|we present|we show|we introduce`, else the first sentence. Label `frase del abstract (automática)`. `tldr` is shown under the abstract with chip `TLDR de Semantic Scholar (modelo)`, not inside that blurb.

React keys: the article uses `key={"stub" | "body"}`. The stub from `make_stub` / `abstract_paper` is a one-block document whose `b0` is the abstract **[V, `pipeline.abstract_paper`]**. The sections publish is a new block list from `finalize` **[V, `latex.finalize`]**. Remount on that transition. Do not try to keep scroll anchors from the stub.

From the first `sections` publish through `figures` and `done`, ids stay. `finalize` assigns `b0, b1, …` once; `materialize_figures` only rewrites `images` on the same objects; the figures publish calls `publish(state["best"], "figures")` on that same object **[V, `pipeline._fetch_and_parse`]**. An OCR→LaTeX upgrade replaces the object (`prefer_parsed`). The demo does not wait on OCR (§6). If `upgraded_from` appears, remount the same way as the stub. Do not add stable ids across that upgrade.

### 3.6 Calls the demo does not make

- `GET /subtopics` spends `MODEL_API_KEY` (`split_query` in `rrm/search/split.py`). The UI does not call it. Cluster titles in the curated map stay curated. The live view uses the query text as the only heading.
- `GET /crops` spends Meta ($0.0025/image, `SAM_USD_PER_IMAGE` in `rrm/reader/serve.py`). The companion does not use crops. The UI does not call it.
- The UI does not call `POST /prepare`. `/burst` already spawns `prefetch` for the first 10 corpus ids (`_prefetch_reader`).

## 4. Backlog items marked ★

| ★ item | Resolution | Owner | Code today |
|---|---|---|---|
| Figures are not served | `GET /file` in §3.3 | RRM-16 backend | `paper.json` stores file names; no route reads `papers/{id}/figures/` **[V]** |
| Paper key arXiv vs corpus id | `paperKey` prefers `corpusid`. Curated routes stay `#/p/{arxivId}`. Live routes are `#/p/{corpusid}`. `arxivId` may be `""` (`abstract_paper`) | RRM-16 UI | Burst rows have `corpusid` only. Paper JSON has both **[V]** |
| `Paper.tsx` has no `case "ref"` | Add it in `One()` | RRM-16 UI | `One` returns `null` on unknown `t`, so `ref` inlines are dropped **[V, `Paper.tsx`]** |
| Equation numbers | UI renders `\tag{n}` from `eq.number` at draw time | RRM-16 UI | Backend sets `block["number"]` and does not put `\tag` in `tex` **[V, `_eq_block`]**. UI reads `\tag` only **[V, line that builds `xref`]** |
| No CORS, no auth | §3.2 on every route | RRM-16 backend | No `CORSMiddleware`, no token check **[V]** |

### 4.1 `ref` and equation numbers, in the UI only

Do not change `latex.py` to emit `\tag` or `refLabels`. The UI contract already accepts `eq.number` and says `refLabels` is optional.

In `Paper.tsx` `One()`:

```jsx
case "ref": {
  const label = x.label || "";
  const text = x.number != null
    ? (String(label).startsWith("eq") ? `(${x.number})` : String(x.number))
    : (ctx.xref?.[label] || label);
  const href = x.target ? `#blk-${x.target}` : `#${label}`;
  return <a href={href} className="xref" data-xref={label}>{text}</a>;
}
```

In the `eq` branch of the block map, pass `tex={b.number != null ? `${b.tex}\\tag{${b.number}}` : b.tex}` into `Tex`. Do not write the tag back into the JSON.

When building `xref` for an `eq` block, if `b.number != null`, set `xref[label]` from `b.number` before looking for `\tag`. Headings: if `b.number` is set, display it and do not recompute. If it is absent, keep the current counter (curated pandoc JSON has no `number`).

`p.raw === true`: add a CSS class `raw` (monospace, dim) in `globals.css`. Still render the text. `eq.katex_ok === false`: keep the existing KaTeX failure path and add the hint `no se pudo dibujar; TeX original`.

`refLabels`: do not build. `cite` already falls back to `refIndex` order **[V]**.

### 4.2 Other backlog lines (not ★)

These are recorded so RRM-16 does not "fix" them. They are on the DO-NOT list in §8.

- Citation labels (`refLabels`): skipped, above.
- NeRF `katex_ok` and preamble leaking into paragraphs: remeasure in RRM-17. The 9/16 figure is from a cache taken before commit `771f9e6` **[attached QA note]**. Do not retune the parser for the demo.
- `diffusion models` ranking social-diffusion papers first: known behavior of the ranker **[QA]**. The demo script uses a different hero query (§5). The E2E still runs this query and records the titles. Do not change `link_rank`.
- Long-text threshold is 40 words, and any newline selects the proximity adapter (`use_proximity` in `rrm/search/encode.py`) **[V]**. Do not move it to 25.
- Papers with no embedding have an empty `similar` list. The UI shows no neighbors. No backend change.
- Cold start: `missing` for about 12 s after burst is normal **[QA]**. The UI copy in §3.5 covers it. Warm up before a recording (§5).
- OCR takes minutes when there is no LaTeX **[QA, Adam ~$0.24]**. The demo does not wait for it. No resident MinerU.
- SAM misses line diagrams. Out of the demo.
- Curated map does not read `/burst.edges`. Stays that way. Live mode draws edges separately.
- Junk titles such as `[Et al].`: no ranker change. If one appears in the hero burst during RRM-17, note it in the results table. Do not filter it in RRM-16.

## 5. Cheap tests

Owner: RRM-16. One command from the repo root:

```bash
bash scripts/check.sh
```

Acceptance: after `requirements-dev.txt` is installed and the fixture tar is already on disk, the command finishes in under 60 s on a laptop-class machine. This plan did not run pytest (`pytest` is not installed in the planning environment), so that bound is a gate, not a measurement. The existing modules already say they are seconds-long and use no network (`tests/test_reader.py`, `tests/test_search.py` module docstrings).

`scripts/check.sh` does this and nothing else:

1. If `tests/fixtures/demo/paper_sections.json` is missing, download the fixture Release (§5.1) with `gh release download` and untar it into `tests/fixtures/demo/`. If `gh` fails, exit before pytest. Pytest itself does not open a socket.
2. `python3 -m pytest -q tests/test_demo_contract.py tests/test_search.py tests/test_reader.py`
3. `node --test apps/reader/tests/contract.test.mjs apps/reader/tests/instrument.test.mjs apps/reader/tests/scaling.test.mjs apps/reader/tests/bibtex.test.mjs apps/reader/tests/companion.test.mjs`

Not in this command: `npm run data`, `npm run build`, `npm run test:e2e`, Playwright, `fidelity/run.py`, `modal`. Those stay as they are. `apps/reader` CI (`.github/workflows/reader.yml`) still runs the curated e2e on its own. Add `tests/fixtures/` to the root `.gitignore`.

### 5.1 Fixture Release

Build it with `scripts/build_demo_fixtures.py` (in git). The script writes a temp directory and prints a tar path. It does not upload. The RRM-16 agent, or Franklin, publishes once:

```bash
python3 scripts/build_demo_fixtures.py
# writes /tmp/demo-fixtures.tar.gz
gh release create artifacts/RRM-16-demo-fixtures-YYYY-MM-DD /tmp/demo-fixtures.tar.gz \
  --title "RRM-16: demo contract fixtures" \
  --notes "Synthetic JSON and a 1x1 PNG for scripts/check.sh. No papers."
```

Size target: under 50 KB. Contents, all synthetic, no paper text and no PDF:

- `paper_stub.json` — `stage: "stub"`, one block `{id: "b0", kind: "p", abs: true}`.
- `paper_sections.json` and `paper_figures.json` — the same three blocks (`h` `b0`, `p` `b1` containing a `ref`, `eq` `b2` with `number: 1` and no `\tag`, `fig` `b3`). Sections copy has `images: ["figures/plot.pdf"]` and `stage: "sections"`. Figures copy has `images: ["plot.png"]` and `stage: "figures"`. Ids match.
- `plot.png` — a 1×1 PNG generated in the script.
- `burst.json` — `mode: "short"`, three rows with `corpusid` and no `arxivId`, two `edges`, `subtopics: []`.

The generator is the source of truth. Do not commit the tar or the unpacked files.

### 5.2 Tests and the regression each one locks

New file `tests/test_demo_contract.py`. Keep it under 180 lines. New file `apps/reader/tests/contract.test.mjs`. Keep it under 80 lines.

| Test | Prevents |
|---|---|
| `test_file_name_rejects_traversal` | `resolve_figure` opening `../meta.json`, `foo/bar.png`, or `source.pdf`. The ★ "figures are not served" hole, and path traversal on the new route. |
| `test_file_name_accepts_png` | A normal `plot.png` resolving under `figures/`. |
| `test_guard_fails_closed_without_token` | A deploy with an empty `RRM_DEMO_TOKEN` answering 200. |
| `test_guard_rejects_bad_token_and_unknown_origin` | Open CORS (`*`) or a request that spends GPU without the header. |
| `test_guard_accepts_header_and_query_token` | `/file` breaking because `<img>` cannot set a header. |
| `test_fixture_ids_stable_sections_to_figures` | A later edit re-running `finalize` between the sections publish and the figures publish, which would move scroll anchors. |
| `test_display_math_is_its_own_block` | A `p` block containing `\[` or `$$`. Parses a 15-line synthetic tex through `parse_tex` / `finalize`. Also asserts the `eq` block has `number` and its `tex` has no `\tag`. |
| `test_burst_fixture_has_corpusid_not_arxiv` | The UI adapter requiring `arxivId` on a burst row. |
| `contract.test.mjs` `paperKey prefers corpusid` | Live routes still fetching `/papers/{arxivId}.json` for a backend paper. |
| `contract.test.mjs` `figureUrl points at /file` | `<img src>` set to the bare file name, which 404s on the static host. |
| `contract.test.mjs` `ref text uses number` | `case "ref"` missing, which renders `null` and drops the cross-reference. |
| `contract.test.mjs` `eq tag comes from number` | Backend equations drawing with no number. The helper that builds the TeX string is what the test calls. |

Existing tests stay in the same command. They already cover macro expansion, figure*, the prefetch queue, OCR block shape, LaTeX-beats-OCR, and the burst ranker on synthetic arrays. Do not rewrite them. Do not add a Modal test, a network test, or a Playwright test to `scripts/check.sh`.

## 6. E2E on Modal (RRM-17)

Owner of the run: the orchestrator, after Franklin approves the spend in writing. The RRM-16 agent does not deploy and does not call Modal or Meta. RRM-17 is that run plus a results note. It is not a feature change.

Budget: **≤ $5**, hard stop **$10**. The previous reader-plus-burst QA was about $3.6 of a $5 cap **[attached QA note, billing plus an estimated Meta share]**. This run avoids Meta (no `/subtopics`, no `/crops`) and caps OCR.

The in-repo price constants (`rrm/reader/serve.py`, comment "modal.com/pricing, fetched 2026-10-28") are `CPU_USD_PER_CORE_S = 0.0000131`, `L4_USD_PER_S = 0.000222`, `SAM_USD_PER_IMAGE = 0.0025`. They do not include the 32 GB of burst memory. Treat the CPU formula as a lower bound **[I]**. The real stop is the Modal billing page, checked between queries.

Cost shape **[I, from those constants and the QA times]**:

- One warm `/burst` is 0.5–0.7 s **[V]**. Twelve of those are well under $0.01 of CPU. The cold load is 54–103 s **[V]** and is the part the formula underprices because of RAM.
- Each `/burst` spawns `prefetch` of 10 ids. LaTeX `full_s` was 3–21 s **[V]**. A hundred uncached LaTeX papers at the top of that range is on the order of $1 of CPU **[I]**. Overlap across queries makes it less. Cached papers are a `/paper` read (0.7–0.97 s warm, 5.4 s cold **[V]**).
- One OCR paper of Adam's size was about $0.24 on A10G **[V]**, and the code falls back from L4 to A10G, which the README says costs more than the L4 column. Cap: if two papers have entered stage `ocr`, stop the reader app (§6.4). Do not let a third OCR start.
- SAM and Muse: $0 if the script does not call them.

Do not run `modal run rrm/reader/serve.py::bench`. `bench` calls `parse_one.remote` and parses again.

### 6.1 Before the run

From `integration/e2e`, with `RRM_DEMO_TOKEN`, `S2_API_KEY`, and `MODEL_API_KEY` in the environment (the key must be present so a paper that hits SAM by accident does not crash; the script still must not call `/crops` or `/subtopics`):

```bash
modal deploy rrm/search/serve.py
modal deploy rrm/reader/serve.py
```

Copy the two base URLs from the deploy output into `BURST` and `READER`. Do not commit them.

There is no `min_containers` in the code **[V]** and RRM-17 does not add one. Warmth is "run the queries immediately", not a container left overnight.

### 6.2 Warm-up

1. `GET $BURST/burst?q=transformers%20for%20time%20series%20forecasting&n=10` with `X-RRM-Demo`. Record wall time. Expect 54–103 s if the container is cold **[V]**, 0.5–0.7 s if it is not.
2. `GET $READER/status?ids=13756489` and `GET $READER/paper?id=13756489`. That id was `done` / `latex` in the QA status sample. It warms the reader CPU. If it is `missing`, do not treat that as a failure of the id; record it and continue.
3. Start the twelve queries within a few minutes. A long pause lets the class scale to zero **[I, not measured here]**.

### 6.3 The twelve prompts

`n=10` on every call. Record a TSV locally. Do not commit it and do not put abstracts in it.

| # | Kind | Query | What to check |
|---|---|---|---|
| 1 | short, already QA'd | `transformers for time series forecasting` | mode `short`. Hero query for the recording. Top-10 settle was 39 s cold **[V]** |
| 2 | short, known-hard | `diffusion models` | mode `short`. Top titles may be social diffusion, not generative models **[V]**. Record titles. Not a failure |
| 3 | short | `graph neural networks` | mode `short` |
| 4 | short | `neural radiance fields` | mode `short`. Distinct from the exact-id NeRF row |
| 5 | long | Title of arXiv `1706.03762`, a newline, then its abstract, both read at run time from the arXiv abs page | mode `long`, because `use_proximity` is true when the text contains a newline **[V]**. Do not paste the abstract into the repo or the results note |
| 6 | exact arXiv | `1706.03762` | mode `paper`, `first` set, if that id is in the display table |
| 7 | exact arXiv | `arXiv:2003.08934` | mode `paper`. Open `/paper` and record `katex_ok` / `equations` from `meta`. Remeasure; do not reuse the old 9/16 cache figure |
| 8 | exact arXiv, macro-heavy | `1810.04805` | mode `paper`. BERT. Record `status` and whether the parse finishes as `latex` |
| 9 | exact DOI | `https://doi.org/<doi>` where `<doi>` is the `doi` cell of corpus `1706.03762` read from the volume display table during the run | mode `paper`. If the cell is empty, write `doi_missing` and skip. Do not invent a DOI |
| 10 | exact corpus id | `corpusid:13756489` | mode `paper` |
| 11 | exact title | `Denoising Diffusion Probabilistic Models` | mode `paper` if the normalized title is in `PaperLookup.title`. The title is four or more words, so `TITLE_MIN_WORDS` does not block it **[V, `display.py`]** |
| 12 | short, must not open a paper | `speech recognition` | mode `short`, `first` null. Titles shorter than 4 words are not exact-paper matches unless they have ≥ 1000 citations, and this phrase is the comment's own example of a search **[V]** |

For each row record:

- `query`, `mode`, HTTP wall time, and the sum of `seconds` in the JSON (`encode`, `search`, `rank`, `edges`, `split`, `hydrate`). `split` should be `0` because `/burst` passes `split=None` **[V]**.
- Top-1 `corpusid` and `title`.
- Time to first content: wall time from the burst response until `/paper` on top-1 returns a stub or a later stage. Also copy `meta.first_content_s` when present.
- Time to sections: wall time until `stage` is `sections`, `figures`, or `done`. Also `meta.sections_s`.
- Top-10 settle: wall time until all 10 ids are `done`, `abstract_only`, or `failed`. Poll `/status` every 2 s, give up at 180 s and record who is left.
- For top-1, `source`, `katex_ok`, `equations`, `status`, `reason`.
- Failures: HTTP errors, `failed`, and ids still `missing` at 180 s.

Open `/paper` on top-1 only, plus one extra id in the top 10, so the run does not download twelve full texts on top of the prefetch.

### 6.4 Stop conditions

After every query, look at `/status` for that top 10.

- If two papers show stage `ocr` or `source: "ocr"`, run `modal app stop rrm-reader`, record `ocr_cap`, and do not deploy it again in this run. Burst can finish only if the billing page is still under $5.
- If the Modal billing page for the run crosses $5, stop both apps and write the table with the rows already done.
- $10 is the hard stop even if a number above was misread. Stop both apps.

### 6.5 Shutdown

```bash
modal app stop rrm-burst
modal app stop rrm-reader
```

Confirm in the Modal dashboard that both apps have zero containers. Do not set `min_containers`. Do not leave the apps up for a later recording unless Franklin accepts the idle cost in writing. A recording on another day repeats §6.2.

The results note lists the twelve rows, the warm-up wall time, the OCR count, and the dollar figure read from the billing page. Mark any dollar figure the page did not show as unknown. Do not commit the TSV.

## 7. Where the frontend is hosted

Recommendation: **Vercel Hobby, static export of `apps/reader`**. The API stays on Modal.

What the app already is **[V, `apps/reader/next.config.mjs`]**: `output: "export"`, `images.unoptimized: true`. `npm run build` writes `out/`. The README already serves that folder with `python3 -m http.server 3100 -d out`. Vercel is that folder on a CDN, with a build that runs `npm ci` and `npm run build` in `apps/reader`.

Why this and not Modal for the UI:

- API latency does not go through Vercel. The browser calls `*.modal.run` directly. A cold burst is still 54–103 s **[V]** and is a Modal cost, not a hosting cost. The UI only has to show `calentando el motor…`.
- Serving `out/` from a third Modal app would put a cold start in front of the HTML and would bill CPU. The static file does not need that.
- CORS is required because the origins differ. §3.2 is the fix. Hosting both on Modal would avoid CORS and is still the wrong trade for a demo that should open while the 32 GB class is scaled to zero.
- `NEXT_PUBLIC_BURST_URL`, `NEXT_PUBLIC_READER_URL`, and `NEXT_PUBLIC_RRM_DEMO_TOKEN` are set in the Vercel project and baked in at build. There is no runtime config. The token is visible in the bundle (§3.2).
- `output: "export"` cannot hide the token behind a Vercel Function rewrite. Do not drop the static export to build that proxy. Do not add a server.

Limits that matter, and limits this plan does not invent:

- Hobby is the free plan. Confirm on the pricing page, the day the project is created, that a non-commercial research demo is allowed to use it. This plan does not quote a bandwidth number.
- The image optimizer does not apply. `unoptimized: true` is already set and must stay, because the static export cannot use the optimizer.
- Function body size, Fluid Compute, and the 300 s function timeout do not apply to a static export. Do not turn on Vercel Functions for this demo.
- The curated `out/` includes figure PNGs from the RRM-11 Release. If a Hobby cap is actually hit, fall back to the README's `http.server` on a laptop for the recording. Do not move the UI onto Modal as the fallback.
- Node on Vercel: the app declares Node ≥ 22. Set the project to Node 22. Do not upgrade Next as part of hosting.

Build command: `npm ci && npm run build`, root directory `apps/reader`. The build does not need `npm run data` when `public/papers/` was restored from the RRM-11 Release before the build. On Vercel that restore is a build step that runs `gh release download` (needs a token with `contents: read` on this public repo) and untars into `apps/reader/`. If that token is annoying to set up, build `out/` locally after the restore and deploy the folder. Either way the papers stay out of git.

Do not put the Modal URLs or the demo token in the repository. They live in the Vercel project env and in the Modal secret.

## 8. Tickets

### RRM-16 — implementation, medium

One agent, on `integration/e2e` only. Medium means: the merge in §1, the guard and `/file`, the ASGI switch in §3.1, the UI pieces in §3.4–§4.1, the check in §5, and the doc fixes in §2. It does not mean a new ranker, a new OCR path, or a deploy.

Acceptance:

- `integration/e2e` contains the seven merges in §1.3. `pipelines/s2_download/app.py` still has the `045a3ec` try/except. PR #5 is not in the tree.
- With both public URLs empty, `apps/reader` curated behavior is unchanged. Existing `npm test` in `apps/reader` still passes when the RRM-11 cache is restored (that suite is outside the 60 s command; run it once).
- With the URLs set, a local mock (a tiny Python `http.server` that speaks the four routes, not Modal) can complete: burst list, status poll, stub, then sections, then a figure loaded from `/file`.
- `bash scripts/check.sh` exits 0 in under 60 s once the fixture is on disk. The new tests in §5.2 exist and fail if the guard, the file sandbox, the `ref` helper, or the equation tag helper is removed.
- No `RRM_DEMO_TOKEN` value, no Modal URL, and no paper file in the diff.
- `modal` does not appear in the shell history of the ticket.

### RRM-17 — E2E rehearsal

The orchestrator runs §6 after Franklin approves the spend. No product change unless a measured failure forces a follow-up ticket.

Acceptance:

- The TSV has a row for all twelve prompts, or a row that says why the run stopped (`ocr_cap` or `$5`).
- Each completed row has mode, burst wall time, time to first content, time to sections, top-10 settle, top-1 `katex_ok`/`equations`, and failures.
- Billing-page dollars ≤ $5, or the note explains the hard stop at $10.
- `/subtopics` and `/crops` were not called.
- Both apps are stopped and show zero containers.

### DO-NOT build

- `min_containers`, a warm pool, or a container left up overnight.
- A call to `/subtopics` or `/crops` from the UI.
- `refLabels`, a 2D projection endpoint, websockets, streaming, or a shared base URL that merges the two Modal apps.
- Moving the 40-word threshold, retuning `link_rank`, or special-casing `diffusion models`.
- Resident MinerU, an OCR quality pass, or a SAM pass.
- Accounts, origin lists in env vars, a token admin, or a Vercel rewrite proxy.
- Configurable `n`. The live UI sends `10`.
- Stable block ids across the stub, or across an OCR→LaTeX upgrade. Remount instead (§3.5).
- Merging PR #5.
- Committing papers, the fixture tar, `.cache/`, `public/papers/`, or secrets.
- Any Modal or Meta call inside RRM-16.
- A force-directed layout library. The circle in §3.5 is the demo map.
- Editing `main` before Franklin accepts `integration/e2e`.

### Ordered checklist

RRM-16:

1. Cut `integration/e2e` from `origin/main` and run the seven merges in §1.3.
2. Confirm `045a3ec` is present (`vol.reload()` try/except in `pipelines/s2_download/app.py`).
3. Doc fixes in §2 (180 s comments, `missing`, root README pointer, `AGENTS.md` sentence, `requirements-dev.txt`, `.gitignore` line).
4. Add `rrm/demo_guard.py` and `resolve_figure`. Unit-test them before any Modal wiring.
5. Switch reader and burst HTTP to the ASGI apps in §3.1. Keep `prefetch`'s name.
6. Add `GET /file`.
7. Add `apps/reader/src/lib/backend.js`, the `ref` case, the equation tag, `paperKey`, figure URLs, the search box, polling, and the live captions in §3.5.
8. Add the fixture script, publish the Release once, add `scripts/check.sh`, and run it.
9. Run the curated `apps/reader` suite once with the RRM-11 cache restored. Fix only regressions caused by steps 7.
10. Push `integration/e2e`. Open its PR to `main` and leave it unmerged.

RRM-17, after Franklin's spend approval:

11. Deploy both apps, warm up, run the twelve prompts, write the TSV, stop at the caps in §6.4.
12. Stop both apps and confirm zero containers.
13. Report the table and the billing-page dollars.

## 9. Decisions Franklin has to make

The engineering choices above are the plan. These items still need him:

1. **Spend.** RRM-17 may spend up to $5 on Modal (hard stop $10) and must not call the Meta API. Nothing in RRM-16 spends. Say yes before anyone deploys.
2. **PR #5.** Close it and delete `cursor/rrm-13-reader-speed-210e`. The plan is to drop it. Veto if that branch should be kept for the record.
3. **Landing on `main`.** `integration/e2e` does not merge to `main` until he accepts the demo branch. This plan's PR is only the plan.
4. **Demo token.** He picks `RRM_DEMO_TOKEN` and puts it in the Modal secret and in the Vercel env. It must not be committed. He should know it will be readable in the JS bundle.
5. **Vercel hostname.** One literal origin to add to `ALLOWED_ORIGINS`, and a Hobby account. Confirm Hobby's current non-commercial terms the day the project is created.
6. **Meta stays off.** No Muse labels and no SAM crops in the demo. Say if a recording actually needs either; that is a separate spend approval and is not in the $5 procedure.
7. **Hybrid demo.** Curated map by default, live burst only when someone types a question. This matches the UI contract. Say if the recording must be live-only.
8. **Ranker.** RRM-16 does not change the 40-word rule and does not retune `diffusion models`. Say if either is required for the recording; that would be a new ticket, not part of RRM-16.
