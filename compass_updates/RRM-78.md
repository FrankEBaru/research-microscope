# RRM-78 — prompts de artefactos vivos

Compass (`FrankEBaru/research-microscope-compass`, rama `claude/rrm-50-plan-b1`) respondió 404. Este archivo es la nota que iba a esa rama. No hay secretos ni cifras de gasto.

## Qué quedó

Contrato `rrm-widget/0.2` en `rrm/liveart/CONTRACT.md`. La lista que el verificador aplica está en `rrm/liveart/contract.py`. Coordinación con el equipo: `liveart/TEAM.md`.

Cinco prompts (selector, preguntas, explicación, código, verificador) en `rrm/liveart/prompts.py`. El enunciado va en una cerca y es dato. `schemas()` es el JSON Schema de cada paso. `package(claim)` arma los mensajes solo si la bandera está prendida.

Camino offline, sin Meta: 26 temas, banco de dudas en español, cuatro widgets de oro en el prompt y treinta emulados en `emulated.py`. Los draws se ejecutan y cambian con el control; el de posición también con el tiempo.

Bandera apagada por defecto: `RRM_LIVE_ARTIFACTS` o `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS`. Sin ella `path_for` devuelve `static`.

Eval: `python -m evals.liveart`. También entra en `bash scripts/check.sh` vía `tests/test_liveart_prompts.py`.

## Para los otros

- RRM-79: el iframe, el AST y el tope de tiempo contra `contract.py`. No cambiar un límite sin subir la versión.
- RRM-80: puede reemplazar un `draw` de `fewshots.py` o de `emulated.py`. La forma JSON no cambia. Solo los cuatro de oro entran al prompt.

## Meta

No. Falta el sandbox y la calificación de los mockups. Llamar al modelo ahora mediría un contrato que el renderer todavía no impone.
