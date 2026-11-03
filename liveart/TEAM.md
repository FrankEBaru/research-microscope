# Equipo artefactos

Archivo de esta rama. La coordinación que se puede escribir va en compass `equipo-artefactos/` (rama `claude/rrm-50-plan-b1`).

Contrato vigente: **`rrm-widget/0.3`**, el de RRM-79 (`cursor/rrm-79-live-engine-c8e7`, PR #59). Misma forma JSON que 0.2. Presupuestos: draw 8000, explain 420, pregunta 180, why 160, etiqueta 28, controles 1–6, lienzo 640×360, frame 1000 ms, corte del intérprete 200000 pasos. El sandbox está en `apps/reader/src/lib/liveart/`. Esta rama rebasa los prompts y los casos sobre ese texto. No abran un 0.4.

## RRM-78 (`cursor/rrm-78-prompts-526e`, PR #57)

Los prompts siguen siendo de esta rama. Los límites son los de 0.3. Cambios de texto que se quedan:

- Razón `slop` en el selector y en el verificador (`not_slop` en el esquema). Adorno, o un control que solo pinta.
- Temas nuevos, con arXiv chequeado: `giou` (1902.09630), `ppo_clip` (1707.06347), `nerf_freq` (2003.08934), `vit_patch` (2010.11929).
- `rope-shift` reemplaza el giro de un solo vector: distancia y corrimiento. El parecido es el producto de los dos giros. No entra al prompt.
- Temas del banco, misma versión 0.2, sin mover límites: softmax por bloques, Chinchilla, Adam, costo del borrador, YaRN por partes, BatchNorm, destilación, LoRA, KL, haz, BPE, SmoothQuant, delta selectivo. El delta para RRM-79 está en compass `CONTRACT.md`. `rope_relative` es `rope`. `scaling` es `chinchilla`.
- El few-shot de posición ahora muestra la onda y el parecido entre posiciones. Siguen siendo 4 few-shots.
- Tras la sonda 1: el prompt lista las llamadas `ctx.*` y prohíbe `setLineDash`; dice el subconjunto (`continue`, `undefined` y helpers no declarados no entran); pide title/explain/questions en el idioma del enunciado; a lo más dos `for` anidados y menos de 50000 vueltas; cada control mueve la figura. El selector tiene ejemplos de RoPE, SwiGLU y speculative decoding como widget.
- Galería de prueba, fuera del lector: `liveart/host/gallery.html`. Lienzo 640×360, iframe `sandbox=allow-scripts`, sin `allow-same-origin`, sin `eval` (el CSP no lo deja).

### Pedido a RRM-79

El iframe del lector sigue siendo tuyo. La galería no lo reemplaza. Host: `state.w=640`, `state.h=360`, frame 1000 ms. El verificador del modelo sigue rechazando slop; el sandbox ya rechaza `dead_control`, `slop_inert`, `slop_unrelated` y `slop_seal`.

Sonda 2: no hace falta tocar el motor. No agregues `setLineDash`, `continue` ni `undefined`, no subas el corte de pasos y no hagas bilingüe `slop_unrelated`. Esos rechazos de la sonda 1 son los correctos. El prompt ya dice la lista, el subconjunto, el idioma, el tope de bucles y que cada control mueve la figura. Detalle en `rrm/liveart/CONTRACT.md`, sección «Sonda 2».

### Pedido a RRM-80

Vi los 100 mockups y los 14 `fewshot_ids`. No entran al prompt: con 4 de oro ya va en ~10 mil caracteres. Si uno se ve mejor que el de `fewshots.py`, pásame ese JSON. La galería ya muestra los 4 nuevos junto a los emulados.

Franklin: no integrar al lector todavía. Cada widget tiene que enseñar, no solo moverse.
