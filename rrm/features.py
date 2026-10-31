"""Feature flag for the demo surface.

`RRM_FEATURES=core` (default) keeps the burst and the reader. Panorama, Muse
subtopics, SAM crops, and any other Meta call stay off. `all` is the previous
surface. An unknown value is core, so a typo cannot turn Meta on.
"""

import os

CORE = "core"
ALL = "all"


def features_mode() -> str:
    raw = (os.environ.get("RRM_FEATURES") or CORE).strip().lower()
    return ALL if raw == ALL else CORE


def core_mode() -> bool:
    return features_mode() != ALL
