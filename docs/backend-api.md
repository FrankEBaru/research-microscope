# Backend HTTP

Two Modal apps. Each one exposes a single ASGI app named `api`. The real host is the URL printed by `modal deploy`. Do not commit it.

Every route checks `RRM_DEMO_TOKEN` (`rrm/demo_guard.py`). Send it as `X-RRM-Demo`. `GET /file` also accepts the query `k`, because an `<img>` cannot set a header. An empty token is 401 and does not read the volume or spawn work. An `Origin` outside `ALLOWED_ORIGINS` is 403. A request with no `Origin` is allowed when the token matches.

Reader, app `rrm-reader`, function `api`:

- `GET /paper?id=`
- `GET /status?ids=` (comma-separated corpus ids; unknown ids are `missing`)
- `POST /prepare` with `{"ids": []}`
- `GET /crops?id=&pages=`
- `GET /file?id=&name=&k=` (a file under `papers/{id}/figures/` or `papers/{id}/crops/`, or 404)

`prefetch` stays a Modal function named `prefetch`. The UI does not call `/crops` or `/prepare`.

Burst, app `rrm-burst`, class `BurstSearch`, method `api`:

- `GET /burst?q=&n=`
- `GET /subtopics?q=`

The UI calls `/burst` with `n=10`, then `/status`, `/paper`, and `/file`. It does not call `/subtopics`. `run_burst` is a Modal method with no public URL.
