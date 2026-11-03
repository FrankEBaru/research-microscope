"""Feature flag for the demo surface.

`RRM_FEATURES=core` (default) is the B1 surface: burst, reader, margin notes
and the explain box. Panorama, Muse subtopics, SAM crops and the instrument
stay off. Notes and the explain box call Meta when `MODEL_API_KEY` is set.
`all` is the previous surface and is never implied by a run mode. An unknown
value is core, so a typo cannot turn the rest of Meta on.
"""

import os

CORE = "core"
ALL = "all"


def features_mode() -> str:
    raw = (os.environ.get("RRM_FEATURES") or CORE).strip().lower()
    return ALL if raw == ALL else CORE


def core_mode() -> bool:
    return features_mode() != ALL
