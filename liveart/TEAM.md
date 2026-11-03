# Equipo artefactos

Archivo de esta rama. La coordinación que se puede escribir va en compass `equipo-artefactos/` (rama `claude/rrm-50-plan-b1`).

Lectura de `origin` el 2026-11-03: `cursor/rrm-79-live-engine-c8e7` (`liveart/HANDOFF-RRM-79.md`) y `cursor/rrm-80-mockups-2121` (`rrm/liveart/HANDOFF-RRM-80.md`). Los dos copiaron el contrato **0.1**. Esta rama ya está en **0.2**. No abran un segundo contrato: rebasen sobre este texto.

## RRM-78 (`cursor/rrm-78-prompts-526e`, PR #57)

Contrato **`rrm-widget/0.2`**. Límites iguales (draw 3500, 1–4 controles). Cambios de texto, no de tope:

- Razón `slop` en el selector y en el verificador (`not_slop` en el esquema). Adorno, o un control que solo pinta.
- Temas nuevos, con arXiv chequeado: `giou` (1902.09630), `ppo_clip` (1707.06347), `nerf_freq` (2003.08934), `vit_patch` (2010.11929).
- `rope-shift` reemplaza el giro de un solo vector: distancia y corrimiento. El parecido es el producto de los dos giros. No entra al prompt.
- El few-shot de posición ahora muestra la onda y el parecido entre posiciones. Siguen siendo 4 few-shots. El prompt de código mide 10161 caracteres.
- Galería de prueba, fuera del lector: `liveart/host/gallery.html`. Lienzo 360×200, iframe `sandbox=allow-scripts`, sin `allow-same-origin`, sin `eval` (el CSP no lo deja).

### Pedido a RRM-79

El iframe del lector sigue siendo tuyo. La galería no lo reemplaza. Host: `state.w=360`, `state.h=200`. Rechaza lo que `banned_in`, `dead_control` y `slop` ya rechazan. Si mueves un límite, sube la versión.

### Pedido a RRM-80

Vi los 100 mockups y los 14 `fewshot_ids`. No entran al prompt: con 4 de oro ya va en ~10 mil caracteres. Si uno se ve mejor que el de `fewshots.py`, pásame ese JSON. La galería ya muestra los 4 nuevos junto a los emulados.

Franklin: no integrar al lector todavía. Cada widget tiene que enseñar, no solo moverse.
