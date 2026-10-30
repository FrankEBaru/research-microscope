"""Demo-window keep-warm. Off unless the deploy process sets RRM_DEMO_KEEP_WARM.

Modal's default scaledown_window is 60s, which dropped the burst container
between prompts (100-131s cold starts in the RRM-17 run). The flag sets the
window to Modal's maximum, 20 minutes. min_containers stays 0: an idle demo
must not keep a container after the window.
"""

import os

# Modal rejects scaledown_window above 20 minutes.
DEMO_SCALEDOWN_S = 1200
_ON = {"1", "true", "yes", "on"}


def demo_keep_warm() -> bool:
    return os.environ.get("RRM_DEMO_KEEP_WARM", "").strip().lower() in _ON


def scaledown_window() -> int | None:
    """Seconds to pass as scaledown_window, or None to leave Modal's 60s default."""
    if demo_keep_warm():
        return DEMO_SCALEDOWN_S
    return None
