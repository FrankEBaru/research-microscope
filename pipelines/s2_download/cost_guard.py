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
# Calibrate samples papers, the smallest citations shard, a cheap abstracts
# shard, and one embeddings shard. This cap is the sample spend, not the $9
# ledger. A shard that stops early is not a throughput measurement.
CALIBRATION_USD = 0.10

DEFAULT_CPU = 2.0
DEFAULT_MEMORY_MIB = 4096
DEFAULT_CONCURRENCY = 100

# A shard is killed at this multiple of its own estimate. Waves are launched
# only when spent + multiplier * wave_estimate still fits under the cap, so a
# whole wave hitting the ceiling stays within the cap.
SHARD_KILL_MULTIPLIER = 3.0

# Synthetic papers on this parser: 2 cores were about 1.4x the rows/s of 1
# core, not 2x. Embeddings are not scaled. This is not a Modal measurement.
JSON_TWO_CORE_SPEEDUP = 1.4

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
    citations_seconds_per_byte: float | None = None,
    abstracts_seconds_per_byte: float | None = None,
    tldrs_seconds_per_byte: float | None = None,
    measured_cpu: float | None = None,
) -> dict:
    """Project container-seconds, dollars, and wall time for every shard.

    Papers run first (the CS id set is built from them). The other datasets
    then share one pool of `concurrency` containers. Citations use only their
    own measured seconds/byte. Abstracts use their own rate when it was
    measured, otherwise the papers rate. Tldrs follow abstracts, then papers.
    Embeddings use their own rate and are not scaled with cpu. JSON throughput
    at 2 cores is treated as 1.4x one core, not 2x. The result is an estimate.
    """
    measured_at = float(cpu if measured_cpu is None else measured_cpu)
    present = {"papers", "embeddings-specter_v2"}
    present.update(other_bytes)
    present.update(other_shards)

    rates: dict[str, float] = {}
    sources: dict[str, str | None] = {}
    missing: list[str] = []

    def remember(name: str, seconds_per_byte: float | None, source: str | None) -> None:
        if name not in present:
            return
        if seconds_per_byte is not None and seconds_per_byte > 0:
            rates[name] = float(seconds_per_byte)
            sources[name] = source
            return
        rates[name] = 0.0
        sources[name] = None
        missing.append(name)

    remember("papers", papers_seconds_per_byte, "measured")
    remember("embeddings-specter_v2", embeddings_seconds_per_byte, "measured")
    if "abstracts" in present:
        if abstracts_seconds_per_byte is not None and abstracts_seconds_per_byte > 0:
            remember("abstracts", abstracts_seconds_per_byte, "measured")
        else:
            remember("abstracts", papers_seconds_per_byte if papers_seconds_per_byte > 0 else 0.0, "papers")
    if "citations" in present:
        # Never borrow the papers rate. That is what made citations look like $14.
        remember(
            "citations",
            citations_seconds_per_byte if citations_seconds_per_byte else 0.0,
            "measured",
        )
    if "tldrs" in present:
        if tldrs_seconds_per_byte is not None and tldrs_seconds_per_byte > 0:
            remember("tldrs", tldrs_seconds_per_byte, "measured")
        elif rates.get("abstracts", 0.0) > 0:
            followed = sources.get("abstracts")
            if followed == "measured":
                followed = "abstracts"
            remember("tldrs", rates["abstracts"], followed or "abstracts")
        else:
            remember("tldrs", 0.0, None)
    for name in other_bytes:
        if name not in rates:
            remember(name, 0.0, None)

    def json_speed(target_cpu: float) -> float:
        cores = float(target_cpu)
        if cores <= 1.0:
            return 1.0
        if cores >= 2.0:
            return JSON_TWO_CORE_SPEEDUP
        return 1.0 + (JSON_TWO_CORE_SPEEDUP - 1.0) * (cores - 1.0)

    def scaled(name: str, target_cpu: float) -> float:
        base = rates.get(name, 0.0)
        if base <= 0 or name == "embeddings-specter_v2" or measured_at <= 0 or target_cpu <= 0:
            return base
        return base * (json_speed(measured_at) / json_speed(target_cpu))

    bytes_of = {
        "papers": int(papers_bytes),
        "embeddings-specter_v2": int(embeddings_bytes),
    }
    shards_of = {
        "papers": int(papers_shards),
        "embeddings-specter_v2": int(embeddings_shards),
    }
    for name, total in other_bytes.items():
        bytes_of[name] = int(total)
        shards_of[name] = int(other_shards.get(name, 0))

    order = ["papers", "abstracts", "tldrs", "citations", "embeddings-specter_v2"]
    for name in other_bytes:
        if name not in order:
            order.append(name)

    def build(target_cpu: float) -> dict:
        rate = usd_per_second(target_cpu, memory_mib)
        by_dataset: dict[str, dict] = {}
        container = 0.0
        other_seconds = 0.0
        other_n = 0
        papers_seconds = 0.0
        for name in order:
            if name not in bytes_of and name not in ("papers", "embeddings-specter_v2"):
                continue
            if name not in shards_of:
                continue
            total = int(bytes_of.get(name, 0))
            spb = scaled(name, target_cpu)
            known = name not in missing and spb > 0
            seconds = total * spb if known else None
            by_dataset[name] = {
                "shards": shards_of.get(name, 0),
                "input_bytes": total,
                "input_gb": total / 1e9,
                "seconds_per_byte": spb if known else None,
                "rate_source": sources.get(name),
                "container_seconds": seconds,
                "cost_usd": None if seconds is None else seconds * rate,
            }
            if seconds is None:
                continue
            container += seconds
            if name == "papers":
                papers_seconds = seconds
            else:
                other_seconds += seconds
                other_n += shards_of.get(name, 0)
        container += overhead_seconds
        workers = max(int(concurrency), 1)

        def wall(total_seconds: float, shards: int) -> float:
            if shards <= 0 or total_seconds <= 0:
                return 0.0
            return total_seconds / min(workers, shards)

        papers_wall = wall(papers_seconds, shards_of.get("papers", 0))
        rest_wall = wall(other_seconds, other_n)
        wall_seconds = papers_wall + rest_wall + overhead_seconds
        cost = container * rate
        reasons = []
        if missing:
            reasons.append("measured throughput was zero for " + ", ".join(missing))
        elif cost > PROJECTION_COST_LIMIT_USD:
            reasons.append(
                f"projected cost ${cost:.2f} is above ${PROJECTION_COST_LIMIT_USD:.0f}"
            )
        elif wall_seconds > PROJECTION_WALL_LIMIT_SECONDS:
            hours = wall_seconds / 3600.0
            reasons.append(f"projected wall time {hours:.2f} h is above 3 h")
        priced = not missing
        return {
            "estimated": True,
            "proceed": not reasons,
            "stop_reason": "; ".join(reasons) if reasons else None,
            "container_seconds": container if priced else None,
            "cost_usd": cost if priced else None,
            "wall_seconds": wall_seconds if priced else None,
            "wall_hours": (wall_seconds / 3600.0) if priced else None,
            "papers_wall_seconds": papers_wall if priced else None,
            "parallel_wall_seconds": rest_wall if priced else None,
            "overhead_seconds": overhead_seconds,
            "concurrency": workers,
            "cpu": float(target_cpu),
            "usd_per_container_second": rate,
            "by_dataset": by_dataset,
        }

    targets: list[float] = [1.0, 2.0]
    if not any(abs(float(cpu) - item) < 1e-9 for item in targets):
        targets.append(float(cpu))
    by_cpu = {str(int(item)) if float(item).is_integer() else str(item): build(item) for item in targets}
    primary_key = str(int(cpu)) if float(cpu).is_integer() else str(cpu)
    primary = by_cpu.get(primary_key) or build(float(cpu))
    priced = [
        (float(item["cost_usd"]), key)
        for key, item in by_cpu.items()
        if item.get("cost_usd") is not None
    ]
    recommended = None
    if priced:
        best = min(priced, key=lambda pair: (pair[0], 0 if pair[1] == primary_key else 1, pair[1]))
        recommended = float(best[1]) if best[1].isdigit() else float(best[1])
    stop_reason = primary.get("stop_reason")
    if primary.get("proceed") is False and recommended is not None and abs(recommended - float(cpu)) > 1e-9:
        alt = by_cpu.get(str(int(recommended)))
        if alt and alt.get("proceed") and alt.get("cost_usd") is not None:
            extra = (
                f"cpu={recommended:.0f} estimate is inside the gate "
                f"(${alt['cost_usd']:.2f}, {(alt.get('wall_hours') or 0):.2f} h); "
                f"this projection is priced at cpu={float(cpu):.0f}"
            )
            stop_reason = extra if not stop_reason else stop_reason + "; " + extra
    assumptions = (
        "Shard bytes are the probed totals for each dataset. Citations use "
        "only the citations sample seconds/byte and are not scaled from papers. "
        "Abstracts use their own sample when it finished, otherwise the papers "
        "rate. Tldrs follow that abstracts rate. Embeddings use their own rate. "
        "JSON throughput at 2 cores is treated as 1.4x the 1-core rate (a local "
        "synthetic measurement of this parser, not a Modal result), not 2x. "
        "Embeddings seconds/byte does not change with cpu. Papers finish first; "
        "the other datasets then share "
        "one pool of containers. 600s of single-container overhead is included. "
        "Image build and queue wait are not included. This is an estimate."
    )
    return {
        **primary,
        "stop_reason": stop_reason,
        "by_cpu": by_cpu,
        "recommended_cpu": recommended,
        "measured_cpu": measured_at,
        "assumptions": assumptions,
    }
