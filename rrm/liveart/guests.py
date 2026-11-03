"""Four figures from RRM-82 that the bank did not draw.

The gallery reads the same widgets from apps/reader/src/lib/liveart/guest.js.
"""

import json
from pathlib import Path

GUESTS = json.loads(Path(__file__).with_name("guests.json").read_text(encoding="utf-8"))
