"""Demo-window keep-warm. Off unless the deploy process sets RRM_DEMO_KEEP_WARM.

Modal's default scaledown_window is 60s, which dropped the burst container
between prompts (100-131s cold starts in the RRM-17 run). The flag sets the
window to Modal's maximum, 20 minutes. min_containers stays 0: an idle demo
must not keep a container after the window.
"""

import os

# Modal rejects scaledown_window above 20 minutes.
DEMO_SCALEDOWN_S = 1200
# Between questions the burst container stays up. min_containers stays 0.
BURST_IDLE_S = 600
_ON = {"1", "true", "yes", "on"}


def demo_keep_warm() -> bool:
    return os.environ.get("RRM_DEMO_KEEP_WARM", "").strip().lower() in _ON


def scaledown_window() -> int | None:
    """Seconds for the demo flag, or None to leave Modal's 60s default.

    The reader still uses this. The burst container uses burst_scaledown().
    """
    if demo_keep_warm():
        return DEMO_SCALEDOWN_S
    return None


def burst_scaledown() -> int:
    """How long the burst container stays after the last question.

    Ten minutes between questions. The demo flag keeps the 20 minute window.
    No min_containers: an idle demo still scales to zero after the window.
    """
    if demo_keep_warm():
        return DEMO_SCALEDOWN_S
    return BURST_IDLE_S
