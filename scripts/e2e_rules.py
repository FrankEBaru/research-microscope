#!/usr/bin/env python3
"""RRM-17 stop and settle rules. Supersedes the stop sentence in PR #9.

Do not stop because two papers have stage `ocr` or source `ocr`. That counted
papers already on the volume. Before the twelve prompts, record:

    date +%s

A paper counts toward the cap of 2 only when `/status` (or `/paper` meta) has
ocr_gpu_s > 0 and ocr_invoked_at >= that clock. Then:

    modal app stop rrm-reader

and do not deploy the reader again in that run.

Poll `/status` every 2s and give up at 180s. Settled statuses are done,
abstract_only, and failed. `missing` is not settled: the row has not been
written yet. `queued` and `parsing` are not settled either.

No Modal and no Meta API. This script only prints the rule.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rrm.demo_e2e import SETTLED_STATUSES


def main():
    print("settled:", ", ".join(sorted(SETTLED_STATUSES)))
    print("not settled: missing, queued, parsing, absent")
    print("ocr cap: ocr_gpu_s > 0 and ocr_invoked_at >= $RUN_START, limit 2")
    print("cached OCR (no ocr_invoked_at in this window) does not count")


if __name__ == "__main__":
    main()
