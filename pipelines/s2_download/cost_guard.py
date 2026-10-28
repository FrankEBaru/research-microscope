"""Container-second cost ledger and the full-run projection.

Rates are the Modal CPU and memory prices for this job:
$0.0473 per core-hour and $0.008 per GiB-hour. The ledger is cumulative.
A running total at or above $9 must stop further work.
"""

from __future__ import annotations

import math
from typing import Mapping, MutableMapping

CPU_USD_PER_CORE_HOUR = 0.0473
MEMORY_USD_PER_GIB_HOUR = 0.008

ABORT_USD = 9.0
PROJECTION_COST_LIMIT_USD = 8.0
PROJECTION_WALL_LIMIT_SECONDS = 3 * 60 * 60

DEFAULT_CPU = 2.0
DEFAULT_MEMORY_MIB = 4096
DEFAULT_CONCURRENCY = 100

# A shard is killed at this multiple of its own estimate. Waves are launched
# only when spent + multiplier * wave_estimate still fits under the cap, so a
# whole wave hitting the ceiling stays within the cap.
SHARD_KILL_MULTIPLIER = 3.0

PREFIX = "c|"


def usd_per_second(cpu: float, memory_mib: int) -> float:
    gib = memory_mib / 1024.0
    per_hour = cpu * CPU_USD_PER_CORE_HOUR + gib * MEMORY_USD_PER_GIB_HOUR
    return per_hour / 3600.0


def cost_usd(container_seconds: float, cpu: float, memory_mib: int) -> float:
    if container_seconds < 0:
        raise ValueError("container_seconds must be >= 0")
    return container_seconds * usd_per_second(cpu, memory_mib)


def estimate_seconds(input_bytes: int, mb_per_s: float) -> float:
    """Seconds to stream `input_bytes` at a measured MB/s (1e6 bytes/s)."""
    if input_bytes < 0:
        raise ValueError("input_bytes must be >= 0")
    if mb_per_s <= 0 or math.isnan(mb_per_s):
        return 3600.0
    return (input_bytes / 1e6) / mb_per_s


def entry_usd(entry: object) -> float:
    if isinstance(entry, dict):
        attempts = entry.get("attempts") or []
        reserved = float(entry.get("reserved") or 0.0)
        return float(sum(float(x) for x in attempts)) + reserved
    if entry is None:
        return 0.0
    return float(entry)


class Ledger:
    """Cumulative cost over a dict-like store. One writer per key.

    Values are ``{"attempts": [usd, ...], "reserved": usd}``. Reservations
    count toward the total so in-flight shards hold budget. ``finish``
    replaces the reservation with the measured cost. A crashed attempt that
    left a reservation is counted when that key is reserved again.
    """

    def __init__(self, store: MutableMapping, limit: float = ABORT_USD):
        self.store = store
        self.limit = limit

    def _full_key(self, key: str) -> str:
        return key if key.startswith(PREFIX) else PREFIX + key

    def _get(self, key: str) -> dict:
        raw = self.store.get(self._full_key(key))
        if not isinstance(raw, dict):
            return {"attempts": [], "reserved": 0.0}
        attempts = [float(x) for x in (raw.get("attempts") or [])]
        return {"attempts": attempts, "reserved": float(raw.get("reserved") or 0.0)}

    def _put(self, key: str, entry: dict) -> None:
        self.store[self._full_key(key)] = {
            "attempts": [float(x) for x in entry["attempts"]],
            "reserved": float(entry["reserved"]),
        }

    def total(self) -> float:
        keys = list(self.store.keys())
        total = 0.0
        for key in keys:
            if isinstance(key, str) and key.startswith(PREFIX):
                total += entry_usd(self.store.get(key))
        return total

    def begin(self, key: str, reserve_usd: float) -> None:
        entry = self._get(key)
        if entry["reserved"] > 0:
            entry["attempts"].append(entry["reserved"])
        entry["reserved"] = float(reserve_usd)
        self._put(key, entry)

    def finish(self, key: str, actual_usd: float) -> None:
        entry = self._get(key)
        entry["attempts"].append(float(actual_usd))
        entry["reserved"] = 0.0
        self._put(key, entry)

    def over_budget(self) -> bool:
        return self.total() >= self.limit


def plan_wave(
    spent_usd: float,
    estimates_usd: list[float],
    *,
    limit: float = ABORT_USD,
    multiplier: float = SHARD_KILL_MULTIPLIER,
    max_wave: int = DEFAULT_CONCURRENCY,
) -> int:
    """How many leading shards fit so spent + multiplier * sum stays <= limit."""
    if max_wave <= 0:
        return 0
    count = 0
    running = 0.0
    for estimate in estimates_usd:
        if count >= max_wave:
            break
        nxt = running + float(estimate)
        if spent_usd + multiplier * nxt > limit:
            break
        running = nxt
        count += 1
    return count


def shard_over_ceiling(
    elapsed_seconds: float,
    rate_usd_per_second: float,
    estimate_usd: float,
    *,
    multiplier: float = SHARD_KILL_MULTIPLIER,
) -> bool:
    if estimate_usd <= 0:
        return False
    return elapsed_seconds * rate_usd_per_second > estimate_usd * multiplier


def project_full_run(
    *,
    papers_seconds_per_byte: float,
    papers_shards: int,
    papers_bytes: int,
    embeddings_seconds_per_byte: float,
    embeddings_shards: int,
    embeddings_bytes: int,
    other_bytes: Mapping[str, int],
    other_shards: Mapping[str, int],
    cpu: float,
    memory_mib: int,
    concurrency: int = DEFAULT_CONCURRENCY,
    overhead_seconds: float = 600.0,
) -> dict:
    """Project container-seconds, dollars, and wall time for every shard.

    Papers run first (the CS id set is built from them). The other datasets
    then share one pool of `concurrency` containers. Non-embedding datasets
    use the papers seconds/byte rate. The result is an estimate.
    """
    if papers_seconds_per_byte <= 0 or embeddings_seconds_per_byte <= 0:
        return {
            "estimated": True,
            "proceed": False,
            "stop_reason": "measured throughput was zero",
            "container_seconds": None,
            "cost_usd": None,
            "wall_seconds": None,
            "wall_hours": None,
            "by_dataset": {},
        }

    rate = usd_per_second(cpu, memory_mib)
    by_dataset: dict[str, dict] = {}

    def add(name: str, shards: int, total_bytes: int, seconds_per_byte: float) -> float:
        seconds = total_bytes * seconds_per_byte
        by_dataset[name] = {
            "shards": int(shards),
            "input_bytes": int(total_bytes),
            "container_seconds": seconds,
            "cost_usd": seconds * rate,
        }
        return seconds

    papers_s = add("papers", papers_shards, papers_bytes, papers_seconds_per_byte)
    emb_s = add(
        "embeddings-specter_v2",
        embeddings_shards,
        embeddings_bytes,
        embeddings_seconds_per_byte,
    )
    other_s = 0.0
    other_n = 0
    for name, total_bytes in other_bytes.items():
        shards = int(other_shards.get(name, 0))
        other_s += add(name, shards, int(total_bytes), papers_seconds_per_byte)
        other_n += shards

    container_seconds = papers_s + emb_s + other_s + overhead_seconds
    cost = container_seconds * rate

    workers = max(int(concurrency), 1)

    def wall(total_seconds: float, shards: int) -> float:
        if shards <= 0 or total_seconds <= 0:
            return 0.0
        return total_seconds / min(workers, shards)

    papers_wall = wall(papers_s, papers_shards)
    rest_shards = embeddings_shards + other_n
    rest_wall = wall(emb_s + other_s, rest_shards)
    wall_seconds = papers_wall + rest_wall + overhead_seconds

    reasons = []
    if cost > PROJECTION_COST_LIMIT_USD:
        reasons.append(
            f"projected cost ${cost:.2f} is above ${PROJECTION_COST_LIMIT_USD:.0f}"
        )
    if wall_seconds > PROJECTION_WALL_LIMIT_SECONDS:
        hours = wall_seconds / 3600.0
        reasons.append(f"projected wall time {hours:.2f} h is above 3 h")

    return {
        "estimated": True,
        "proceed": not reasons,
        "stop_reason": "; ".join(reasons) if reasons else None,
        "container_seconds": container_seconds,
        "cost_usd": cost,
        "wall_seconds": wall_seconds,
        "wall_hours": wall_seconds / 3600.0,
        "papers_wall_seconds": papers_wall,
        "parallel_wall_seconds": rest_wall,
        "overhead_seconds": overhead_seconds,
        "concurrency": workers,
        "usd_per_container_second": rate,
        "by_dataset": by_dataset,
        "assumptions": (
            "Shard bytes are summed from presigned-object sizes when probing "
            "succeeds, otherwise sample_shard_bytes * shard_count. Papers, "
            "abstracts, citations, and tldrs use the measured papers "
            "seconds/byte. Embeddings use the measured embeddings seconds/byte. "
            "Papers finish before the other datasets, which then share one "
            "pool of containers. 600s of single-container overhead is included. "
            "Image build and queue wait are not included."
        ),
    }
