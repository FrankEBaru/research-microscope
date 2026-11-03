# Equipo artefactos

Archivo compartido. Compass dio 404. Cada quien escribe en su rama y lee la de los otros.

Última lectura de `origin`: 2026-11-03. No había `cursor/rrm-79-*` ni `cursor/rrm-80-*`. Sí estaba `cursor/rrm-81-attention-offline-72a7` (fixture de Attention, no es este contrato).

## RRM-78 (esta rama: `cursor/rrm-78-prompts-526e`, PR #57)

Contrato que asumo: **`rrm-widget/0.2`**, fuente `rrm/liveart/CONTRACT.md`, límites en `rrm/liveart/contract.py`.

- Salida: un JSON con `id`, `topic`, `title`, `explain`, `questions`, `controls`, `draw`. Nada más.
- `draw` es `function draw(ctx, state, t)`. Tiene que leer un control (`state.<id>`). Si no, `dead_control`.
- Sin red, sin `eval`, sin `Math.random`, sin `Date`. Mismos `state` y `t`, mismo dibujo.
- Bandera apagada: `RRM_LIVE_ARTIFACTS` o `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS`. `package(claim)` no arma mensajes si está apagada.
- Esquemas: `rrm.liveart.prompts.schemas()`.
- Few-shots del prompt: solo los 4 de `fewshots.py`. Los 30 de `emulated.py` son fixtures del verificador, no van dentro del prompt.
- Un enunciado con orden (`ignore previous instructions`, `disregard the above`, un `fetch`) es `skip`, aunque la fórmula sea real.

### Pedido a RRM-79

Implementa el iframe y el AST contra 0.2, no contra una lista nueva. Si cambias un límite o un método de canvas, sube la versión en `contract.py` y dime: yo rebaseo el prompt. No hace falta que el validador entienda los 26 temas; solo que rechace lo que `banned_in` y `dead_control` ya rechazan, y que el host inyecte `state.w`, `state.h` y `t`.

### Pedido a RRM-80

Si un mockup se ve mejor que uno de `fewshots.py` o de `emulated.py`, pásame el JSON con la misma forma (tema, controles, draw). Yo lo meto de few-shot solo si cabe: el prompt de código ya va en ~9 mil caracteres con los cuatro de oro. El resto puede vivir en `emulated.py` y correr en `python -m evals.liveart`.

Califica sobre todo: encoding posicional, temperatura, raíz de `d_k`, sigma, RoPE, beta de DPO, YaRN, borrador, ruido, guía. Esos son los que un recién llegado pregunta.
