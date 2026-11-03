"""Prompts y camino offline de artefactos vivos. No llama a Meta.

El renderer, el iframe y el validador AST son de RRM-79.
La bandera sale apagada: sin ella el lector se queda en el artefacto estático.
"""

from rrm.liveart.contract import VERSION, live_on
from rrm.liveart.offline import explain_for, path_for, questions_for, select_claim, verify_widget
from rrm.liveart.prompts import package, schemas

__all__ = [
    "VERSION",
    "explain_for",
    "live_on",
    "package",
    "path_for",
    "questions_for",
    "schemas",
    "select_claim",
    "verify_widget",
]
