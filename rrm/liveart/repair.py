"""One codegen retry after the engine rejects a widget.

Off unless RRM_LIVE_REPAIR is 1, true, yes, or on. This module does not call Meta.
A caller that sees should_repair may build repair_messages once, then run the
engine verifier again. A second failure stays on the static explanation.
Injection and a painted seal are not retried: the engine stays authoritative.
"""

import os

_BLOCK = frozenset({"injection", "slop_seal"})


def repair_on() -> bool:
    raw = os.environ.get("RRM_LIVE_REPAIR", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def retriable(reasons) -> bool:
    if not reasons:
        return False
    for reason in reasons:
        head = str(reason).split(":", 1)[0]
        if head in _BLOCK:
            return False
    return True


def should_repair(reasons, enabled=None) -> bool:
    if enabled is None:
        enabled = repair_on()
    return bool(enabled) and retriable(reasons)


def repair_note(reasons, detail=None) -> str:
    """One short note the retry can act on. Spanish, same voice as the prompts."""
    lines = []
    notes = [str(item) for item in (detail or []) if item]
    named = [item.split(":", 1)[1] for item in notes if item.startswith("ctx:")]
    for reason in reasons or []:
        text = str(reason)
        head, _, tail = text.partition(":")
        if head == "banned":
            if named:
                who = ", ".join(named)
                lines.append(
                    f"ctx.{who} no está. Usa solo los métodos de la lista. "
                    "Una línea punteada son segmentos cortos de moveTo y lineTo."
                )
            else:
                lines.append(
                    "El motor marcó banned. Usa solo los métodos de la lista. "
                    "setLineDash no existe: una línea punteada son segmentos cortos."
                )
        elif head == "throw":
            lines.append(
                "El draw llamó algo que no existe. Un string solo tiene .length. "
                "Nada de charAt, slice o indexOf. Declara cada función antes de usarla."
            )
        elif head == "syntax":
            lines.append("El parser no aceptó el draw. Quédate en var, if, for, while, break y continue.")
        elif head == "step_cap":
            lines.append("Hay demasiados pasos. Como mucho dos bucles anidados, y menos de 50000 vueltas.")
        elif head == "slop_inert":
            who = tail or "ese"
            lines.append(
                f"El control {who} no mueve la figura. Tiene que cambiar una posición o un tamaño "
                "en al menos 2 px. El color y el texto no cuentan."
            )
        elif head == "slop_unrelated":
            lines.append(
                "El título, la explicación y las preguntas tienen que hablar del enunciado, "
                "en el idioma del enunciado."
            )
        elif head == "dead_control":
            lines.append("Cada control se lee en el draw como state.<id> y mueve la geometría.")
        elif head == "blank":
            lines.append("El draw no pintó. Tiene que haber un fill, un stroke o un fillRect.")
        elif head in {"size", "draw", "title", "explain", "question", "questions", "control", "controls"}:
            lines.append(f"El motor marcó {text}. Acorta o corrige esa parte y deja el resto.")
        elif head in _BLOCK:
            lines.append(f"El motor marcó {text}. No hay reintento.")
        else:
            lines.append(f"El motor marcó {text}.")
    for item in notes:
        if item.startswith("ctx:"):
            continue
        if item not in lines:
            lines.append(item)
    return " ".join(lines)
