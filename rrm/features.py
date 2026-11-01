"""Feature flag for the demo surface.

`RRM_FEATURES=core` (default) keeps the burst and the reader. Panorama, Muse
subtopics and SAM crops stay off. The ask box may call Meta when
`MODEL_API_KEY` is set. `all` is the previous surface. An unknown value is
core, so a typo cannot turn the rest of Meta on.
"""

import os

CORE = "core"
ALL = "all"


def features_mode() -> str:
    raw = (os.environ.get("RRM_FEATURES") or CORE).strip().lower()
    return ALL if raw == ALL else CORE


def core_mode() -> bool:
    return features_mode() != ALL
