"""Modal app for the Semantic Scholar bulk download (RRM-2).

One app, four entrypoints:

    modal run --detach pipelines/s2_download/app.py::keycheck
    modal run --detach pipelines/s2_download/app.py::calibrate
    modal run --detach pipelines/s2_download/app.py::full
    modal run --detach pipelines/s2_download/app.py::verify

Shard bodies are streamed from presigned object URLs. Every Semantic Scholar
API call goes through ``S2API.call``, which is a single container.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# `modal run pipelines/s2_download/app.py` puts this directory on sys.path.
# The package root is two levels up; the container image also has it via
# add_local_python_source.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import modal

from pipelines.s2_download.cost_guard import (
    ABORT_USD,
    DEFAULT_CONCURRENCY,
    DEFAULT_CPU,
    DEFAULT_MEMORY_MIB,
    Ledger,
    cost_usd,
    estimate_seconds,
    plan_wave,
    project_full_run,
    shard_over_ceiling,
    usd_per_second,
)
from pipelines.s2_download.fetch import (
    DownloadError,
    PresignExpired,
    open_url_stream,
    probe_content_length,
    redact_url,
)
from pipelines.s2_download.s2_client import DATASETS_BASE, GRAPH_ARXIV_URL, S2Client, S2ClientError
from pipelines.s2_download.transform import (
    DATASETS,
    NEEDS_CS,
    StopShard,
    cs_dir,
    iter_records,
    load_cs,
    merge_cs,
    process_records,
    shard_complete,
    shard_path,
    verify_tree,
    write_run_record,
)

APP_NAME = "rrm-s2-download"
VOLUME_NAME = "rrm-data"
MOUNT = "/s2"
_RELEASE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_ALIASES = {
    "papers": "papers",
    "abstracts": "abstracts",
    "tldrs": "tldrs",
    "citations": "citations",
    "embeddings": "embeddings-specter_v2",
    "embeddings-specter_v2": "embeddings-specter_v2",
    "specter_v2": "embeddings-specter_v2",
}
_TRANSIENT = {
    "DownloadError",
    "PresignExpired",
    "ConnectionError",
    "Timeout",
    "TimeoutError",
    "ReadTimeout",
    "ConnectTimeout",
    "ChunkedEncodingError",
    "ProtocolError",
    "OSError",
}

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "numpy>=1.26",
        "pyarrow>=18",
        "requests>=2.31",
        "orjson>=3.10",
        "isal>=1.6",
    )
    .add_local_python_source("pipelines")
)

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
cost_dict = modal.Dict.from_name("rrm-s2-cost", create_if_missing=True)


def _safe_release(release_id: str) -> str:
    if not release_id or not _RELEASE_ID.match(release_id):
        raise RuntimeError("release id is not a safe path component")
    return release_id


def _clamp_resources(cpu: float, memory: int, concurrency: int) -> tuple[float, int, int]:
    cpu_value = float(cpu)
    memory_value = int(memory)
    workers = int(concurrency)
    if cpu_value <= 0:
        raise RuntimeError("cpu must be positive")
    if memory_value < 512:
        raise RuntimeError("memory must be at least 512 MiB")
    if workers < 1:
        workers = 1
    if workers > DEFAULT_CONCURRENCY:
        workers = DEFAULT_CONCURRENCY
    return cpu_value, memory_value, workers


def _public_error(exc: BaseException) -> str:
    message = str(exc)
    if "api-key" in message.lower() or "S2_API_KEY" in message:
        return type(exc).__name__
    message = re.sub(r"https?://\S+", lambda match: redact_url(match.group(0)), message)
    text = f"{type(exc).__name__}: {message}".strip()
    return text[:300]


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, (DownloadError, PresignExpired, OSError, TimeoutError)) or type(exc).__name__ in _TRANSIENT


def _read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def _latest_path(stage: str) -> str:
    return os.path.join(MOUNT, "_runs", f"latest-{stage}.json")


def _ledger() -> Ledger:
    return Ledger(cost_dict)


def _note_s2_time(op: str, started: float) -> None:
    elapsed = time.perf_counter() - started
    _ledger().finish(f"s2api|{op}", elapsed * usd_per_second(0.5, 512))


def _over_budget() -> bool:
    if cost_dict.get("abort"):
        return True
    if _ledger().total() >= ABORT_USD:
        cost_dict["abort"] = True
        return True
    return False


@app.cls(
    image=image,
    secrets=[modal.Secret.from_name("s2-api-key")],
    max_containers=1,
    cpu=0.5,
    memory=512,
    timeout=60 * 60,
    retries=0,
    scaledown_window=30,
)
@modal.concurrent(max_inputs=1)
class S2API:
    """Single-container Semantic Scholar client. All API calls enter here."""

    @modal.enter()
    def _enter(self) -> None:
        key = os.environ.get("S2_API_KEY", "")
        if not key:
            raise RuntimeError("S2_API_KEY is not set in the Modal secret")
        self.client = S2Client(key, clock_store=cost_dict)
        self.cache: dict = {}

    @modal.method()
    def call(self, op: str, payload: dict | None = None) -> dict:
        started = time.perf_counter()
        try:
            payload = payload or {}
            if op == "graph":
                return self._status_only(GRAPH_ARXIV_URL)
            if op == "release_latest":
                return self._release(f"{DATASETS_BASE}/release/latest")
            if op == "dataset_files":
                return self._files(
                    str(payload["release_id"]),
                    str(payload["dataset"]),
                    bool(payload.get("force")),
                )
            return {"status": 0, "error": "unknown op"}
        finally:
            _note_s2_time(op, started)

    def _fetch(self, url: str) -> tuple[int, bytes]:
        try:
            response = self.client.get(url)
        except S2ClientError as exc:
            return int(exc.status), b""
        return int(response.status), response.body

    def _status_only(self, url: str) -> dict:
        status, _body = self._fetch(url)
        return {"status": status}

    def _release(self, url: str) -> dict:
        status, body = self._fetch(url)
        if status != 200 or not body:
            return {"status": status, "release_id": None, "datasets": []}
        data = json.loads(body)
        names = []
        for item in data.get("datasets") or []:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
            elif isinstance(item, str):
                names.append(item)
        return {
            "status": status,
            "release_id": data.get("release_id"),
            "datasets": names,
        }

    def _files(self, release_id: str, dataset: str, force: bool) -> dict:
        release_id = _safe_release(release_id)
        cache_key = (release_id, dataset)
        now = time.monotonic()
        cached = self.cache.get(cache_key)
        if not force and cached and now - cached[0] < 60:
            return cached[1]
        status, body = self._fetch(f"{DATASETS_BASE}/release/{release_id}/dataset/{dataset}")
        files: list[str] = []
        if status == 200 and body:
            data = json.loads(body)
            files = [str(item) for item in (data.get("files") or [])]
        payload = {"status": status, "shards": len(files), "files": files}
        if status == 200:
            self.cache[cache_key] = (now, payload)
        return payload


def _api(op: str, payload: dict | None = None) -> dict:
    return S2API().call.remote(op, payload or {})


def _probe_one(url: str) -> int | None:
    try:
        return probe_content_length(url)
    except Exception:
        return None


def _probe_all(urls: list[str]) -> list[int | None]:
    if not urls:
        return []
    sizes: list[int | None] = [None] * len(urls)
    workers = min(32, len(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe_one, url): index for index, url in enumerate(urls)}
        for future in as_completed(futures):
            sizes[futures[future]] = future.result()
    return sizes


def _sum_bytes(sizes: list[int | None]) -> tuple[int, bool]:
    """Return (total_bytes, estimated). Missing sizes use the mean of the known ones."""
    known = [int(size) for size in sizes if size]
    if not sizes:
        return 0, True
    if len(known) == len(sizes):
        return sum(known), False
    if not known:
        return 0, True
    mean = sum(known) / len(known)
    total = 0
    for size in sizes:
        total += int(size) if size else int(mean)
    return total, True


def _parse_datasets(raw: str) -> list[str]:
    if not raw.strip():
        return list(DATASETS)
    chosen = []
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        canon = _ALIASES.get(name)
        if canon is None:
            known = ", ".join(DATASETS)
            raise RuntimeError(f"unknown dataset {name}; expected one of {known}")
        if canon not in chosen:
            chosen.append(canon)
    return [name for name in DATASETS if name in chosen]


def _workers(cpu: float, memory: int, concurrency: int):
    return process_shard.with_options(cpu=cpu, memory=memory, max_containers=concurrency)


def _blank_shard(job: dict, **extra) -> dict:
    return {
        "ok": False,
        "dataset": job["dataset"],
        "index": int(job["index"]),
        "rows": 0,
        "rows_in": 0,
        "bad_lines": 0,
        "input_bytes": int(job.get("input_bytes") or 0),
        "output_bytes": 0,
        "output_gb": 0.0,
        "wall_seconds": 0.0,
        "container_seconds": 0.0,
        "cost_usd": 0.0,
        "mb_per_s": 0.0,
        "peak_ram_mib": 0.0,
        "cs_rows": 0,
        "both_cs": 0,
        "arxiv_rows": 0,
        "vector_dim": None,
        "skipped_existing": False,
        "stopped_early": False,
        "aborted": False,
        **extra,
    }


def _download_once(url: str, job: dict, cs, should_stop) -> dict:
    gzip_reader, response, counter, length = open_url_stream(url)
    try:
        result = process_records(
            job["dataset"],
            iter_records(gzip_reader),
            root=MOUNT,
            release=job["release"],
            index=int(job["index"]),
            cs=cs,
            should_stop=should_stop,
        )
    finally:
        gzip_reader.close()
        response.close()
    input_bytes = int(length or counter.bytes_read or 0)
    result["input_bytes"] = input_bytes
    elapsed = float(result["wall_seconds"])
    result["mb_per_s"] = (input_bytes / 1e6) / elapsed if elapsed > 0 and input_bytes else 0.0
    result["output_gb"] = result["output_bytes"] / 1e9
    result["skipped_existing"] = False
    result["stopped_early"] = False
    result["aborted"] = False
    return result


@app.function(
    image=image,
    volumes={MOUNT: volume},
    cpu=DEFAULT_CPU,
    memory=DEFAULT_MEMORY_MIB,
    timeout=90 * 60,
    retries=2,
    max_containers=DEFAULT_CONCURRENCY,
    scaledown_window=5,
)
def process_shard(job: dict) -> dict:
    """Stream one shard to Parquet. Returns measurements; never returns the URL."""
    dataset = str(job["dataset"])
    index = int(job["index"])
    release = _safe_release(str(job["release"]))
    cpu = float(job.get("cpu") or DEFAULT_CPU)
    memory = int(job.get("memory_mib") or DEFAULT_MEMORY_MIB)
    rate = usd_per_second(cpu, memory)
    estimate = float(job.get("estimate_usd") or 0.0)
    started = time.perf_counter()
    result: dict | None = None
    ledger = _ledger()
    key = f"shard|{dataset}|{index}"
    reserve = 0.0
    if not cost_dict.get("abort") and not job.get("skip_existing"):
        reserve = estimate
    ledger.begin(key, reserve)
    try:
        volume.reload()
        if cost_dict.get("abort"):
            result = _blank_shard(job, aborted=True, reason="budget", error="budget")
            return result
        if job.get("skip_existing") and shard_complete(MOUNT, release, dataset, index):
            import pyarrow.parquet as pq

            rows = pq.read_metadata(shard_path(MOUNT, release, dataset, index)).num_rows
            result = _blank_shard(job, ok=True, skipped_existing=True, rows=rows)
            return result
        cs = None
        if dataset in NEEDS_CS:
            directory = cs_dir(MOUNT, release)
            if not os.path.exists(os.path.join(directory, "meta.json")):
                result = _blank_shard(job, error="CS index is missing")
                return result
            cs = load_cs(directory)

        def should_stop() -> str | None:
            elapsed = time.perf_counter() - started
            if cost_dict.get("abort"):
                return "budget"
            if shard_over_ceiling(elapsed, rate, estimate):
                return "shard_ceiling"
            return None

        url = str(job["url"])
        try:
            result = _download_once(url, job, cs, should_stop)
        except PresignExpired:
            refreshed = _api(
                "dataset_files",
                {"release_id": release, "dataset": dataset, "force": True},
            )
            files = refreshed.get("files") or []
            if refreshed.get("status") != 200 or index >= len(files):
                raise
            result = _download_once(files[index], job, cs, should_stop)
        volume.commit()
        return result
    except StopShard as exc:
        result = _blank_shard(
            job,
            stopped_early=True,
            aborted=exc.reason == "budget",
            reason=exc.reason,
            error=exc.reason,
        )
        return result
    except Exception as exc:
        if _transient(exc):
            raise
        result = _blank_shard(job, error=_public_error(exc))
        return result
    finally:
        elapsed = time.perf_counter() - started
        actual = elapsed * rate
        ledger.finish(key, actual)
        if isinstance(result, dict):
            result["container_seconds"] = elapsed
            result["cost_usd"] = actual
            if not result.get("wall_seconds"):
                result["wall_seconds"] = elapsed
            if result.get("input_bytes") and elapsed > 0 and not result.get("mb_per_s"):
                result["mb_per_s"] = (result["input_bytes"] / 1e6) / elapsed


@app.function(
    image=image,
    volumes={MOUNT: volume},
    cpu=2,
    memory=DEFAULT_MEMORY_MIB,
    timeout=60 * 60,
    retries=1,
)
def run_merge(release: str) -> dict:
    release = _safe_release(release)
    started = time.perf_counter()
    ledger = _ledger()
    ledger.begin("merge|cs", 0.0)
    try:
        volume.reload()
        result = merge_cs(MOUNT, release)
        volume.commit()
        return result
    finally:
        ledger.finish("merge|cs", (time.perf_counter() - started) * usd_per_second(2, DEFAULT_MEMORY_MIB))


def _mb_per_s(dataset: str, measured: dict[str, float]) -> float:
    if dataset == "embeddings-specter_v2":
        rate = measured.get("embeddings-specter_v2") or measured.get("papers") or 0.0
    else:
        rate = measured.get("papers") or measured.get("embeddings-specter_v2") or 0.0
    return float(rate)


def _build_jobs(
    dataset: str,
    release: str,
    urls: list[str],
    sizes: list[int | None],
    mb_per_s: float,
    cpu: float,
    memory: int,
    skip_existing: bool,
) -> tuple[list[dict], list[dict]]:
    jobs = []
    skipped = []
    for index, url in enumerate(urls):
        if skip_existing and shard_complete(MOUNT, release, dataset, index):
            import pyarrow.parquet as pq

            rows = pq.read_metadata(shard_path(MOUNT, release, dataset, index)).num_rows
            skipped.append(
                _blank_shard(
                    {"dataset": dataset, "index": index, "input_bytes": sizes[index] if index < len(sizes) else 0},
                    ok=True,
                    skipped_existing=True,
                    rows=int(rows),
                )
            )
            continue
        nbytes = sizes[index] if index < len(sizes) and sizes[index] else 0
        seconds = estimate_seconds(int(nbytes), mb_per_s) if nbytes else 1800.0
        jobs.append(
            {
                "dataset": dataset,
                "index": index,
                "url": url,
                "release": release,
                "cpu": cpu,
                "memory_mib": memory,
                "input_bytes": int(nbytes) if nbytes else None,
                "estimate_usd": cost_usd(seconds, cpu, memory),
                "skip_existing": False,
            }
        )
    return jobs, skipped


def _interleave(groups: list[list[dict]]) -> list[dict]:
    pools = [list(group) for group in groups if group]
    ordered = []
    while any(pools):
        for pool in pools:
            if pool:
                ordered.append(pool.pop(0))
    return ordered


def _run_waves(jobs: list[dict], cpu: float, memory: int, concurrency: int) -> tuple[list[dict], bool]:
    if not jobs:
        return [], False
    worker = _workers(cpu, memory, concurrency)
    outcomes: list[dict] = []
    offset = 0
    aborted = False
    wave_index = 0
    while offset < len(jobs):
        if _over_budget():
            aborted = True
            break
        spent = _ledger().total()
        remaining = jobs[offset:]
        count = plan_wave(spent, [float(job["estimate_usd"]) for job in remaining], max_wave=concurrency)
        if count <= 0:
            cost_dict["abort"] = True
            aborted = True
            print(f"budget stop before next wave; cumulative ${spent:.4f}", flush=True)
            break
        wave = remaining[:count]
        offset += count
        wave_index += 1
        print(
            f"wave {wave_index}: {len(wave)} shards, cumulative ${spent:.4f}",
            flush=True,
        )
        for item in worker.map(wave, order_outputs=False, return_exceptions=True):
            if isinstance(item, BaseException):
                outcomes.append({"ok": False, "error": _public_error(item), "dataset": None, "index": None})
            else:
                outcomes.append(item)
                if item.get("aborted") or item.get("reason") == "budget":
                    cost_dict["abort"] = True
                    aborted = True
        if _over_budget():
            aborted = True
            break
    return outcomes, aborted


def _aggregate(results: list[dict]) -> dict:
    summary = {
        "rows": 0,
        "bad_lines": 0,
        "output_bytes": 0,
        "output_gb": 0.0,
        "input_bytes": 0,
        "container_seconds": 0.0,
        "cost_usd": 0.0,
        "shards_ok": 0,
        "shards_failed": 0,
        "shards_skipped": 0,
        "peak_ram_mib": 0.0,
        "mb_per_s": 0.0,
        "errors": [],
    }
    weighed_bytes = 0
    weighed_seconds = 0.0
    for item in results:
        if not isinstance(item, dict):
            summary["shards_failed"] += 1
            continue
        summary["rows"] += int(item.get("rows") or 0)
        summary["bad_lines"] += int(item.get("bad_lines") or 0)
        summary["output_bytes"] += int(item.get("output_bytes") or 0)
        summary["input_bytes"] += int(item.get("input_bytes") or 0)
        summary["container_seconds"] += float(item.get("container_seconds") or 0.0)
        summary["cost_usd"] += float(item.get("cost_usd") or 0.0)
        summary["peak_ram_mib"] = max(summary["peak_ram_mib"], float(item.get("peak_ram_mib") or 0.0))
        if item.get("skipped_existing"):
            summary["shards_skipped"] += 1
        elif item.get("ok"):
            summary["shards_ok"] += 1
            seconds = float(item.get("container_seconds") or item.get("wall_seconds") or 0.0)
            nbytes = int(item.get("input_bytes") or 0)
            if seconds > 0 and nbytes > 0:
                weighed_bytes += nbytes
                weighed_seconds += seconds
        else:
            summary["shards_failed"] += 1
            if item.get("error") and len(summary["errors"]) < 20:
                summary["errors"].append({"index": item.get("index"), "error": item.get("error")})
    summary["output_gb"] = summary["output_bytes"] / 1e9
    if weighed_seconds > 0:
        summary["mb_per_s"] = (weighed_bytes / 1e6) / weighed_seconds
    return summary


def _finish_stage(stage: str, payload: dict, started: float, cpu: float, memory: int) -> dict:
    elapsed = time.perf_counter() - started
    _ledger().finish(f"orch|{stage}", elapsed * usd_per_second(cpu, memory))
    payload["stage_wall_seconds"] = elapsed
    payload["cumulative_cost_usd"] = _ledger().total()
    payload["stage"] = stage
    payload["measured"] = True
    path = write_run_record(MOUNT, stage, payload)
    volume.commit()
    payload["record_path"] = path
    payload["volume_record"] = f"/_runs/latest-{stage}.json"
    print(_format_stage(payload), flush=True)
    return payload


def _budget_payload(stage: str, started: float, cpu: float, memory: int) -> dict:
    payload = {
        "ok": False,
        "aborted": True,
        "proceed": False,
        "blocked": False,
        "stop_reason": f"cumulative cost reached ${ABORT_USD:.0f}",
        "cumulative_cost_usd": _ledger().total(),
    }
    return _finish_stage(stage, payload, started, cpu, memory)


@app.function(
    image=image,
    volumes={MOUNT: volume},
    cpu=1,
    memory=1024,
    timeout=60 * 60,
)
def run_keycheck() -> dict:
    started = time.perf_counter()
    _ledger().begin("orch|keycheck", 0.0)
    try:
        volume.reload()
        if _over_budget():
            return _budget_payload("keycheck", started, 1, 1024)
        graph = _api("graph")
        release = _api("release_latest")
        print(f"graph status {graph.get('status')}", flush=True)
        print(f"release status {release.get('status')}", flush=True)
        ok = graph.get("status") == 200 and release.get("status") == 200 and bool(release.get("release_id"))
        datasets = []
        release_id = release.get("release_id")
        if ok:
            release_id = _safe_release(str(release_id))
            for name in release.get("datasets") or []:
                meta = _api("dataset_files", {"release_id": release_id, "dataset": name})
                row = {"name": name, "status": meta.get("status"), "shards": meta.get("shards")}
                datasets.append(row)
                print(f"dataset {name} status {row['status']} shards {row['shards']}", flush=True)
                if name in DATASETS and meta.get("status") != 200:
                    ok = False
        payload = {
            "ok": ok,
            "graph_status": graph.get("status"),
            "release_status": release.get("status"),
            "release_id": release_id,
            "datasets": datasets,
            "aborted": False,
        }
        if not ok:
            payload["stop_reason"] = "graph or release status was not 200, or a required dataset listing failed"
        return _finish_stage("keycheck", payload, started, 1, 1024)
    except Exception as exc:
        payload = {"ok": False, "error": _public_error(exc), "aborted": False}
        return _finish_stage("keycheck", payload, started, 1, 1024)


def _shard_view(item: dict) -> dict:
    return {
        "ok": bool(item.get("ok")),
        "index": item.get("index"),
        "wall_seconds": item.get("wall_seconds"),
        "container_seconds": item.get("container_seconds"),
        "mb_per_s": item.get("mb_per_s"),
        "peak_ram_mib": item.get("peak_ram_mib"),
        "output_gb": item.get("output_gb"),
        "output_bytes": item.get("output_bytes"),
        "input_bytes": item.get("input_bytes"),
        "rows": item.get("rows"),
        "bad_lines": item.get("bad_lines"),
        "cost_usd": item.get("cost_usd"),
        "vector_dim": item.get("vector_dim"),
        "error": item.get("error"),
    }


@app.function(
    image=image,
    volumes={MOUNT: volume},
    cpu=1,
    memory=2048,
    timeout=4 * 60 * 60,
)
def run_calibrate(cpu: float, memory: int, concurrency: int) -> dict:
    cpu, memory, concurrency = _clamp_resources(cpu, memory, concurrency)
    started = time.perf_counter()
    _ledger().begin("orch|calibrate", 0.0)
    try:
        volume.reload()
        if _over_budget():
            return _budget_payload("calibrate", started, 1, 2048)
        release = _api("release_latest")
        print(f"release status {release.get('status')}", flush=True)
        if release.get("status") != 200 or not release.get("release_id"):
            payload = {
                "ok": False,
                "proceed": False,
                "stop_reason": "release listing was not 200",
                "release_status": release.get("status"),
            }
            return _finish_stage("calibrate", payload, started, 1, 2048)
        release_id = _safe_release(str(release["release_id"]))
        lists: dict[str, list[str]] = {}
        size_map: dict[str, list[int | None]] = {}
        byte_totals: dict[str, int] = {}
        byte_estimated: dict[str, bool] = {}
        shard_counts: dict[str, int] = {}
        for name in DATASETS:
            meta = _api("dataset_files", {"release_id": release_id, "dataset": name})
            print(f"dataset {name} status {meta.get('status')} shards {meta.get('shards')}", flush=True)
            if meta.get("status") != 200:
                payload = {
                    "ok": False,
                    "proceed": False,
                    "release_id": release_id,
                    "stop_reason": f"{name} listing status {meta.get('status')}",
                }
                return _finish_stage("calibrate", payload, started, 1, 2048)
            urls = list(meta.get("files") or [])
            lists[name] = urls
            shard_counts[name] = len(urls)
            sizes = _probe_all(urls)
            size_map[name] = sizes
            total, estimated = _sum_bytes(sizes)
            byte_totals[name] = total
            byte_estimated[name] = estimated

        jobs = []
        for name in ("papers", "embeddings-specter_v2"):
            if not lists[name]:
                payload = {
                    "ok": False,
                    "proceed": False,
                    "release_id": release_id,
                    "stop_reason": f"{name} has no shards",
                }
                return _finish_stage("calibrate", payload, started, 1, 2048)
            nbytes = size_map[name][0] or 0
            jobs.append(
                {
                    "dataset": name,
                    "index": 0,
                    "url": lists[name][0],
                    "release": release_id,
                    "cpu": cpu,
                    "memory_mib": memory,
                    "input_bytes": int(nbytes) if nbytes else None,
                    # Ceiling sits past the shard timeout so a slow sample is measured,
                    # not killed for missing the guessed rate.
                    "estimate_usd": cost_usd(90 * 60, cpu, memory),
                    "skip_existing": False,
                }
            )
        paper_job = [job for job in jobs if job["dataset"] == "papers"]
        embedding_job = [job for job in jobs if job["dataset"] == "embeddings-specter_v2"]
        paper_results, aborted = _run_waves(paper_job, cpu, memory, concurrency)
        merged = None
        if not aborted and paper_results and paper_results[0].get("ok"):
            # The papers worker committed the shard. Reload before reading it.
            volume.reload()
            merged = merge_cs(MOUNT, release_id, partial=True)
            volume.commit()
        embedding_results: list[dict] = []
        if merged and not aborted and not _over_budget():
            embedding_results, emb_aborted = _run_waves(embedding_job, cpu, memory, concurrency)
            aborted = aborted or emb_aborted
        results = paper_results + embedding_results
        by_name = {}
        for item in results:
            if isinstance(item, dict) and item.get("dataset"):
                by_name[item["dataset"]] = item
        papers = by_name.get("papers") or {}
        embeddings = by_name.get("embeddings-specter_v2") or {}
        ok = bool(papers.get("ok") and embeddings.get("ok")) and not aborted

        def seconds_per_byte(item: dict) -> float:
            nbytes = int(item.get("input_bytes") or 0)
            seconds = float(item.get("container_seconds") or item.get("wall_seconds") or 0.0)
            if nbytes <= 0 or seconds <= 0:
                return 0.0
            return seconds / nbytes

        papers_rate = seconds_per_byte(papers)
        embeddings_rate = seconds_per_byte(embeddings)
        # Probing can fail. Fall back to sample_bytes * shard_count, which is an estimate.
        for name, sample in (
            ("papers", papers.get("input_bytes")),
            ("embeddings-specter_v2", embeddings.get("input_bytes")),
        ):
            if byte_totals.get(name, 0) <= 0 and sample:
                byte_totals[name] = int(sample) * shard_counts[name]
                byte_estimated[name] = True
        sample_bytes = int(papers.get("input_bytes") or embeddings.get("input_bytes") or 0)
        for name in DATASETS:
            if name in ("papers", "embeddings-specter_v2"):
                continue
            if byte_totals.get(name, 0) <= 0 and sample_bytes:
                byte_totals[name] = sample_bytes * shard_counts[name]
                byte_estimated[name] = True
        # The calibration embeddings shard was filtered with a one-shard CS set.
        # Drop it so the full run does not treat that file as complete.
        volume.reload()
        scratch = shard_path(MOUNT, release_id, "embeddings-specter_v2", 0)
        if os.path.exists(scratch):
            os.remove(scratch)
        other_bytes = {name: byte_totals[name] for name in DATASETS if name not in ("papers", "embeddings-specter_v2")}
        other_shards = {name: shard_counts[name] for name in other_bytes}
        projection = project_full_run(
            papers_seconds_per_byte=papers_rate,
            papers_shards=shard_counts["papers"],
            papers_bytes=byte_totals["papers"],
            embeddings_seconds_per_byte=embeddings_rate,
            embeddings_shards=shard_counts["embeddings-specter_v2"],
            embeddings_bytes=byte_totals["embeddings-specter_v2"],
            other_bytes=other_bytes,
            other_shards=other_shards,
            cpu=cpu,
            memory_mib=memory,
            concurrency=concurrency,
        )
        if aborted:
            projection["proceed"] = False
            projection["stop_reason"] = projection.get("stop_reason") or f"cumulative cost reached ${ABORT_USD:.0f}"
        payload = {
            "ok": ok,
            "proceed": bool(ok and projection.get("proceed")),
            "stop_reason": None if ok and projection.get("proceed") else projection.get("stop_reason"),
            "aborted": aborted,
            "release_id": release_id,
            "cpu": cpu,
            "memory_mib": memory,
            "concurrency": concurrency,
            "shard_counts": shard_counts,
            "input_bytes": byte_totals,
            "input_bytes_estimated": byte_estimated,
            "mb_per_s": {
                "papers": papers.get("mb_per_s"),
                "embeddings-specter_v2": embeddings.get("mb_per_s"),
            },
            "papers": _shard_view(papers) if papers else None,
            "embeddings-specter_v2": _shard_view(embeddings) if embeddings else None,
            "embeddings_filter": "cs ids from the calibration papers shard only; output GB is not a keep-rate; parquet shard was not kept",
            "cs_index_partial": True,
            "projection": projection,
        }
        if not ok and not payload["stop_reason"]:
            payload["stop_reason"] = "calibration shard failed"
            payload["proceed"] = False
        return _finish_stage("calibrate", payload, started, 1, 2048)
    except Exception as exc:
        payload = {"ok": False, "proceed": False, "error": _public_error(exc), "aborted": False}
        return _finish_stage("calibrate", payload, started, 1, 2048)


@app.function(
    image=image,
    volumes={MOUNT: volume},
    cpu=1,
    memory=2048,
    timeout=4 * 60 * 60,
)
def run_full(
    datasets: str,
    cpu: float,
    memory: int,
    concurrency: int,
    force: bool,
    reprocess: bool,
) -> dict:
    cpu, memory, concurrency = _clamp_resources(cpu, memory, concurrency)
    started = time.perf_counter()
    _ledger().begin("orch|full", 0.0)
    try:
        volume.reload()
        if _over_budget():
            return _budget_payload("full", started, 1, 2048)
        calibration = _read_json(_latest_path("calibrate"))
        if not calibration or not calibration.get("release_id"):
            payload = {
                "ok": False,
                "blocked": True,
                "aborted": False,
                "stop_reason": "calibration record is missing",
            }
            return _finish_stage("full", payload, started, 1, 2048)
        if not calibration.get("proceed") and not force:
            payload = {
                "ok": False,
                "blocked": True,
                "aborted": False,
                "release_id": calibration.get("release_id"),
                "stop_reason": calibration.get("stop_reason") or "calibration gate did not pass",
            }
            return _finish_stage("full", payload, started, 1, 2048)
        release_id = _safe_release(str(calibration["release_id"]))
        selected = _parse_datasets(datasets)
        measured = calibration.get("mb_per_s") or {}
        skip_existing = not reprocess
        per_dataset: dict[str, dict] = {}
        aborted = False
        blocked = False
        papers_failed = False

        if "papers" in selected:
            meta = _api("dataset_files", {"release_id": release_id, "dataset": "papers"})
            if meta.get("status") != 200:
                payload = {
                    "ok": False,
                    "blocked": False,
                    "aborted": False,
                    "release_id": release_id,
                    "stop_reason": f"papers listing status {meta.get('status')}",
                }
                return _finish_stage("full", payload, started, 1, 2048)
            urls = list(meta.get("files") or [])
            sizes = _probe_all(urls)
            volume.reload()
            jobs, skipped = _build_jobs(
                "papers",
                release_id,
                urls,
                sizes,
                _mb_per_s("papers", measured),
                cpu,
                memory,
                skip_existing,
            )
            ran, aborted = _run_waves(jobs, cpu, memory, concurrency)
            papers_summary = _aggregate(skipped + ran)
            per_dataset["papers"] = papers_summary
            papers_failed = int(papers_summary["shards_failed"]) > 0
            # A failed papers shard must not be published as the complete CS set.
            if not aborted and not papers_failed:
                merged = run_merge.remote(release_id)
                per_dataset["cs_index"] = {
                    "cs_papers": merged.get("cs_papers"),
                    "arxiv_rows": merged.get("arxiv_rows"),
                    "partial": merged.get("partial"),
                    "ok": merged.get("ok"),
                }
                if not merged.get("ok") or merged.get("partial"):
                    papers_failed = True
            elif papers_failed and not aborted:
                per_dataset["cs_index"] = {
                    "ok": False,
                    "partial": True,
                    "error": "papers shards failed; CS index was not rebuilt",
                }

        rest = [name for name in selected if name != "papers"]
        if rest and not aborted and not papers_failed:
            if any(name in NEEDS_CS for name in rest):
                meta_path = os.path.join(cs_dir(MOUNT, release_id), "meta.json")
                volume.reload()
                cs_meta = _read_json(meta_path)
                if not cs_meta:
                    payload = {
                        "ok": False,
                        "blocked": True,
                        "aborted": False,
                        "release_id": release_id,
                        "stop_reason": "CS index is missing; run papers before citations or embeddings",
                    }
                    return _finish_stage("full", payload, started, 1, 2048)
                if cs_meta.get("partial") and "papers" not in selected:
                    payload = {
                        "ok": False,
                        "blocked": True,
                        "aborted": False,
                        "release_id": release_id,
                        "stop_reason": "CS index only contains the calibration shard; run papers before citations or embeddings",
                    }
                    return _finish_stage("full", payload, started, 1, 2048)
            groups = []
            skipped_all: list[dict] = []
            listing_failed = False
            for name in rest:
                meta = _api("dataset_files", {"release_id": release_id, "dataset": name})
                if meta.get("status") != 200:
                    per_dataset[name] = {
                        "shards_failed": 1,
                        "errors": [{"error": f"listing status {meta.get('status')}"}],
                    }
                    listing_failed = True
                    break
                urls = list(meta.get("files") or [])
                sizes = _probe_all(urls)
                volume.reload()
                jobs, skipped = _build_jobs(
                    name,
                    release_id,
                    urls,
                    sizes,
                    _mb_per_s(name, measured),
                    cpu,
                    memory,
                    skip_existing,
                )
                groups.append(jobs)
                skipped_all.extend(skipped)
            if not listing_failed:
                ran, aborted = _run_waves(_interleave(groups), cpu, memory, concurrency)
                for name in rest:
                    subset = [item for item in skipped_all + ran if item.get("dataset") == name]
                    per_dataset[name] = _aggregate(subset)

        failed = papers_failed or any(
            int((per_dataset.get(name) or {}).get("shards_failed") or 0) > 0 for name in selected
        )
        if aborted:
            stop_reason = f"cumulative cost reached ${ABORT_USD:.0f}"
        elif papers_failed:
            stop_reason = "papers shards failed; citations and embeddings were not started"
        elif failed:
            stop_reason = "one or more shards failed"
        else:
            stop_reason = None
        payload = {
            "ok": not aborted and not failed,
            "aborted": aborted,
            "blocked": blocked,
            "forced": bool(force and not calibration.get("proceed")),
            "release_id": release_id,
            "datasets_requested": selected,
            "reprocess": bool(reprocess),
            "cpu": cpu,
            "memory_mib": memory,
            "concurrency": concurrency,
            "by_dataset": per_dataset,
            "stop_reason": stop_reason,
        }
        return _finish_stage("full", payload, started, 1, 2048)
    except Exception as exc:
        payload = {"ok": False, "aborted": False, "blocked": False, "error": _public_error(exc)}
        return _finish_stage("full", payload, started, 1, 2048)


def _choose_release() -> str | None:
    for stage in ("full", "calibrate", "keycheck"):
        data = _read_json(_latest_path(stage))
        release_id = data.get("release_id") if data else None
        if release_id and _RELEASE_ID.match(str(release_id)):
            if os.path.isdir(os.path.join(MOUNT, str(release_id))):
                return str(release_id)
    names = []
    if os.path.isdir(MOUNT):
        for name in os.listdir(MOUNT):
            if name.startswith("_"):
                continue
            if os.path.isdir(os.path.join(MOUNT, name)) and _RELEASE_ID.match(name):
                names.append(name)
    if not names:
        return None
    return sorted(names)[-1]


@app.function(
    image=image,
    volumes={MOUNT: volume},
    cpu=1,
    memory=DEFAULT_MEMORY_MIB,
    timeout=2 * 60 * 60,
)
def run_verify() -> dict:
    started = time.perf_counter()
    _ledger().begin("orch|verify", 0.0)
    try:
        volume.reload()
        release_id = _choose_release()
        if not release_id:
            payload = {"ok": False, "stop_reason": "no release directory on the volume"}
            return _finish_stage("verify", payload, started, 1, DEFAULT_MEMORY_MIB)
        report = verify_tree(MOUNT, release_id)
        report["aborted"] = False
        return _finish_stage("verify", report, started, 1, DEFAULT_MEMORY_MIB)
    except Exception as exc:
        payload = {"ok": False, "error": _public_error(exc)}
        return _finish_stage("verify", payload, started, 1, DEFAULT_MEMORY_MIB)


def _fmt_num(value, digits=2):
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _format_stage(payload: dict) -> str:
    stage = payload.get("stage")
    if stage == "keycheck":
        return _format_keycheck(payload)
    if stage == "calibrate":
        return _format_calibrate(payload)
    if stage == "full":
        return _format_full(payload)
    if stage == "verify":
        return _format_verify(payload)
    return json.dumps({key: payload.get(key) for key in ("stage", "ok", "record_path")})


def _format_keycheck(payload: dict) -> str:
    lines = [
        "stage keycheck",
        f"graph status {payload.get('graph_status')}",
        f"release status {payload.get('release_status')}",
        f"release_id {payload.get('release_id')}",
    ]
    for row in payload.get("datasets") or []:
        lines.append(f"dataset {row.get('name')} status {row.get('status')} shards {row.get('shards')}")
    lines.append(f"ok {payload.get('ok')}")
    if payload.get("stop_reason"):
        lines.append(f"STOP: {payload['stop_reason']}")
    lines.append(f"cumulative ${_fmt_num(payload.get('cumulative_cost_usd'), 4)}")
    lines.append(f"volume record {payload.get('volume_record')}")
    return "\n".join(lines)


def _format_shard_line(label: str, item: dict | None) -> str:
    item = item or {}
    return (
        f"{label}: wall {_fmt_num(item.get('wall_seconds'), 1)}s, "
        f"{_fmt_num(item.get('mb_per_s'), 2)} MB/s, "
        f"peak RAM {_fmt_num(item.get('peak_ram_mib'), 0)} MiB, "
        f"output {_fmt_num(item.get('output_gb'), 4)} GB, "
        f"{_fmt_num(item.get('container_seconds'), 1)} container-s -> "
        f"${_fmt_num(item.get('cost_usd'), 4)}"
    )


def _format_calibrate(payload: dict) -> str:
    projection = payload.get("projection") or {}
    lines = [
        "stage calibrate",
        f"release_id {payload.get('release_id')}",
        _format_shard_line("papers", payload.get("papers")),
        _format_shard_line("embeddings-specter_v2", payload.get("embeddings-specter_v2")),
        (
            "projection (estimated): "
            f"{_fmt_num(projection.get('container_seconds'), 0)} container-s, "
            f"${_fmt_num(projection.get('cost_usd'), 2)}, "
            f"wall {_fmt_num(projection.get('wall_hours'), 2)} h, "
            f"proceed={payload.get('proceed')}"
        ),
    ]
    if payload.get("stop_reason"):
        lines.append(f"STOP: {payload['stop_reason']}")
    lines.append(f"cumulative ${_fmt_num(payload.get('cumulative_cost_usd'), 4)}")
    lines.append(f"volume record {payload.get('volume_record')}")
    return "\n".join(lines)


def _format_full(payload: dict) -> str:
    lines = [
        "stage full",
        f"release_id {payload.get('release_id')}",
        f"ok {payload.get('ok')} aborted {payload.get('aborted')} blocked {payload.get('blocked')}",
    ]
    for name, summary in (payload.get("by_dataset") or {}).items():
        if name == "cs_index":
            lines.append(
                f"cs index: papers {summary.get('cs_papers')} arxiv rows {summary.get('arxiv_rows')}"
            )
            continue
        lines.append(
            f"{name}: rows {summary.get('rows')} output {_fmt_num(summary.get('output_gb'), 3)} GB "
            f"shards ok {summary.get('shards_ok')} failed {summary.get('shards_failed')} "
            f"skipped {summary.get('shards_skipped')} "
            f"{_fmt_num(summary.get('container_seconds'), 1)} container-s -> "
            f"${_fmt_num(summary.get('cost_usd'), 4)}"
        )
    if payload.get("stop_reason"):
        lines.append(f"STOP: {payload['stop_reason']}")
    lines.append(f"cumulative ${_fmt_num(payload.get('cumulative_cost_usd'), 4)}")
    lines.append(f"volume record {payload.get('volume_record')}")
    return "\n".join(lines)


def _format_verify(payload: dict) -> str:
    lines = [
        "stage verify",
        f"release_id {payload.get('release_id')}",
        f"ok {payload.get('ok')}",
    ]
    for name, summary in (payload.get("datasets") or {}).items():
        gb = (summary.get("output_bytes") or 0) / 1e9
        lines.append(f"{name}: rows {summary.get('rows')} files {summary.get('files')} {_fmt_num(gb, 3)} GB")
    if payload.get("datasets", {}).get("citations-cs", {}).get("both_cs") is not None:
        lines.append(f"citations-cs both_cs {payload['datasets']['citations-cs'].get('both_cs')}")
    lines.append(f"cs_papers {payload.get('cs_papers')} consistent {payload.get('cs_index_consistent')}")
    lines.append(f"cs_embeddings {payload.get('cs_embeddings')}")
    lines.append(
        f"arxiv rows {payload.get('arxiv_rows')} "
        f"in CS {payload.get('arxiv_rows_in_cs')} "
        f"CS papers with arxiv {payload.get('cs_papers_with_arxiv')} "
        f"coverage {_fmt_num(payload.get('cs_arxiv_coverage'), 4)}"
    )
    lines.append(f"total {_fmt_num(payload.get('total_gb'), 3)} GB")
    lines.append(f"volume record {payload.get('volume_record')}")
    if payload.get("stop_reason"):
        lines.append(f"STOP: {payload['stop_reason']}")
    return "\n".join(lines)


@app.local_entrypoint()
def keycheck() -> None:
    result = run_keycheck.remote()
    print(_format_keycheck(result), flush=True)
    if not result.get("ok"):
        raise SystemExit(1)


@app.local_entrypoint()
def calibrate(
    cpu: float = DEFAULT_CPU,
    memory: int = DEFAULT_MEMORY_MIB,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> None:
    result = run_calibrate.remote(cpu, memory, concurrency)
    print(_format_calibrate(result), flush=True)
    if not result.get("ok"):
        raise SystemExit(1)
    if not result.get("proceed"):
        raise SystemExit(2)


@app.local_entrypoint()
def full(
    datasets: str = "",
    cpu: float = DEFAULT_CPU,
    memory: int = DEFAULT_MEMORY_MIB,
    concurrency: int = DEFAULT_CONCURRENCY,
    force: bool = False,
    reprocess: bool = False,
) -> None:
    result = run_full.remote(datasets, cpu, memory, concurrency, force, reprocess)
    print(_format_full(result), flush=True)
    if result.get("blocked"):
        raise SystemExit(4)
    if result.get("aborted"):
        raise SystemExit(3)
    if not result.get("ok"):
        raise SystemExit(1)


@app.local_entrypoint()
def verify() -> None:
    result = run_verify.remote()
    print(_format_verify(result), flush=True)
    if not result.get("ok"):
        raise SystemExit(1)
