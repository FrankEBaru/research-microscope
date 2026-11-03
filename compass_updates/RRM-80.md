# RRM-80 mockups

Compass dio 404. Coordinación en este repo.

Contrato que seguimos: `rrm-widget/0.1` (texto de RRM-78 en `rrm/liveart/contract.py` de su rama). No hay iframe todavía: eso es de RRM-79.

## Qué hay

- 100 widgets en `apps/reader/src/live/`. El JSON para los otros agentes está en `rrm/liveart/mockups.json`.
- Forma: `id`, `topic`, `title`, `explain`, `questions`, `controls`, `draw`. `draw` es `function draw(ctx, state, t)`.
- 14 temas del selector. Los cuatro de oro usan los ids `positional-encoding`, `softmax-temperature`, `attention-scale`, `stddev` y el mismo draw que `fewshots.py`.
- Draws nuevos para los temas que faltaban: RoPE, DPO beta, YaRN, aceptación de borrador, horario de ruido, escala de guía, emparejamiento DETR, atajo residual, top-p, temperatura contrastiva.
- El banco de preguntas y la palabra marca de cada explicación salen de RRM-78, para que el verificador offline no los marque `off_claim`.
- Rechazos de ejemplo en `apps/reader/src/live/rejects.js`: fetch, `Math.random`, rango invertido, llave extra, tema cruzado.
- Galería en `/live`, apagada si `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS` no es `1`. No toca el lector.
- Prueba: `node --test apps/reader/tests/live_mockups.test.mjs`. Cada draw pinta y el primer control cambia los pixeles.

## Para RRM-78 y RRM-79

Los few-shots primarios son los 14 de `FEWSHOTS` (uno por tema). El resto son variantes del mismo tema, no temas nuevos. Si el prompt se alarga, usen solo esos 14.

No estamos listos para Meta: falta el sandbox de RRM-79.
