# RRM-78 — prompts de artefactos vivos

Compass (`FrankEBaru/research-microscope-compass`, rama `claude/rrm-50-plan-b1`) respondió 404. Este archivo es la nota que iba a esa rama. No hay secretos ni cifras de gasto.

## Qué quedó

Contrato `rrm-widget/0.1` en `rrm/liveart/CONTRACT.md`. La lista que el verificador aplica está en `rrm/liveart/contract.py`.

Cinco prompts (selector, preguntas, explicación, código, verificador) en `rrm/liveart/prompts.py`. El enunciado va en una cerca y es dato. `schemas()` es el JSON Schema de cada paso. `package(claim)` arma los mensajes solo si la bandera está prendida.

Camino offline, sin Meta: 14 temas, banco de dudas en español, cuatro widgets de oro (encoding posicional, temperatura del softmax, escala por la raíz de d_k, desviación estándar). Esos draws se ejecutan y cambian con el control; el de posición también con el tiempo.

Bandera apagada por defecto: `RRM_LIVE_ARTIFACTS` o `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS`. Sin ella `path_for` devuelve `static`.

Eval: `python -m evals.liveart`. También entra en `bash scripts/check.sh` vía `tests/test_liveart_prompts.py`.

## Para los otros

- RRM-79: el iframe, el AST y el tope de tiempo contra `contract.py`. No cambiar un límite sin subir la versión.
- RRM-80: puede reemplazar el `draw` de los cuatro de oro y sumar draws para los temas que todavía no tienen (RoPE, DPO, YaRN, borrador, ruido, guía, DETR, residual, top-p, contraste). La forma JSON no cambia. El selector ya los manda a `widget`, pero `emulated_widget` devuelve `None` hasta que exista draw.

## Meta

No. Falta el sandbox y la calificación de los mockups. Llamar al modelo ahora mediría un contrato que el renderer todavía no impone.
