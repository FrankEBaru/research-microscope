"""Índice de pasajes (RRM-55).

Apagado salvo que `RRM_PASSAGES` sea exactamente `1`. El burst y el lector
no cambian cuando la variable no está.
"""

import os


def passages_enabled() -> bool:
    return os.environ.get("RRM_PASSAGES") == "1"
