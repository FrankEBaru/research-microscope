# Handoff RRM-80

Rama: `cursor/rrm-80-mockups-2121`. Contrato: `rrm-widget/0.3` (RRM-79, PR #59). No se llamó a Meta.

## Hecho

- 100 draws a mano, forma del contrato: `id`, `topic`, `title`, `explain`, `questions`, `controls`, `draw`.
- `draw` es `function draw(ctx, state, t)`. El host pone `state.w`, `state.h` y los controles.
- Fuente JS: `apps/reader/src/live/` (`draws.js` primarios, `variants.js`, `variants2.js`, `variants3.js`, banco en `banks.js`).
- JSON para el otro lado: `rrm/liveart/mockups.json` (`version`, `count`, `fewshot_ids`, `widgets`).
- 14 temas del selector. Cada uno tiene al menos un draw. Los cuatro de oro copian el draw de `fewshots.py` de RRM-78 y usan estos ids: `positional-encoding`, `softmax-temperature`, `attention-scale`, `stddev`.
- Temas que no tenían draw y ahora sí: `rope`, `dpo_beta`, `yarn_scale`, `speculative`, `noise_schedule`, `guidance`, `detr_match`, `residual`, `nucleus`, `contrastive_temp`.
- La explicación y las preguntas salen del banco de RRM-78, con la palabra marca (`base`, `temperatura`, `raíz`, `desviación`, `gira`, `beta`, `escala`, `borrador`, `ruido`, `guía`, `emparej`, `atajo`, `masa`). Así el verificador offline no los marca `off_claim`.
- Rechazos de ejemplo en `apps/reader/src/live/rejects.js`: `fetch` + url, `Math.random`, rango invertido, llave extra, tema cruzado.
- Prueba: `node --test apps/reader/tests/live_mockups.test.mjs`. Pasó: 100/100 pintan y el primer control cambia pixeles. También está en `scripts/check.sh`. El raster no es el sandbox.
- Galería en `apps/reader/src/app/live/`, bandera `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS` en `1` / `true` / `yes` / `on`. Apagada, el lector no cambia.
- Notas de coordinación: `compass_updates/RRM-80.md` y `compass_updates/equipo-artefactos/`.

## Pase del 3 nov ~1:45 (contrato 0.3)

Franklin: no integrar al lector. El host es la galería estática, ahora a 640×360.

- Catálogo 117. JSON `rrm/liveart/mockups.json`, versión `rrm-widget/0.3`.
- Harness local (`apps/reader/src/live/contract.js`) con los números de 0.3: draw 8000, explicación 420, pregunta 180, porqué 160, etiqueta 28, controles 1–6.
- `verifyWidget` de RRM-79 (`613cf74`): 117/117 accept. La prueba de pixeles local también, 4/4.
- Temas del harness alineados a la tabla publicada: `chinchilla` (antes `scaling`), `rope` (absorbe el relativo), `spec_cost`, `gqa`, `moe` con control `k`. `quant` es propuesta: no está en la tabla.
- Seis draws de varios pasos en `rich.js`. El ranking de 15 está en compass `equipo-artefactos/IDEAS.md`.

## Pase anterior (11 widgets)

Franklin: no integrar al lector todavía. El host es la galería estática `rrm/liveart/gallery/index.html` (servir la raíz del repo). `GET /live` sigue en 500 (`ssr: false` en un Server Component); no se tocó.

Los 100 primeros draws se quedaron. Se sumaron 11 en `apps/reader/src/live/explore.js`. Prueba: `node --test apps/reader/tests/live_mockups.test.mjs`, 111/111. Temas nuevos propuestos (RRM-79 aún no publica CONTRACT.md): `rope_relative`, `adam`, `lora`, `kl_rlhf`, `beam`, `batchnorm`, `scaling`, `online_softmax`.

## Siguiente

1. La galería del lector (`/live`) sigue en 500. Cuando toque integrar, mover el `dynamic()` a un Client Component. La revisión visual está hecha en la galería estática, en Chrome headless, a 640×360.
2. El raster de `apps/reader/src/live/raster.js` solo cubre rect, path, arc y texto. No implementa `save` / `rotate` / `scale`. Los draws no los usan.
3. `fewshot_ids` trae un draw por tema del harness (25), oro primero. Si el prompt se alarga, no metas los 117.
4. Esta rama no pide la llave de Meta. El motor ya tiene sandbox.

## Mejores mockups

Los cuatro de oro, más el primario de cada tema que faltaba. Esos 14 están en `fewshot_ids` del JSON.

- `positional-encoding`. La base cambia la frecuencia. También usa `t`.
- `softmax-temperature`. Bajar la temperatura concentra una barra.
- `attention-scale`. Fila de arriba sin raíz (se afila con `d`), fila de abajo con raíz.
- `stddev`. La banda y los puntos se abren con sigma.
- `rope`. Un vector gira con `theta`.
- `dpo-beta`. La curva `-log sigmoid(beta * gap)` se empina.
- `yarn-scale`. `sin(pos / escala)` da menos vueltas.
- `speculative`. De 8 tokens del borrador, los aceptados son `round(8 * acuerdo)`.
- `noise-schedule`. Señal baja y ruido sube con beta.
- `guidance`. El punto se corre de lo incondicional hacia el texto, y se pasa si la escala es mayor que 1.
- `detr-match`. Con peso de clase alto, la línea cruza hacia la otra caja.
- `residual`. Cuatro barras mezclan entrada y capa con `skip`.
- `nucleus`. El corte de top-p salta de token en token.
- `contrastive-temp`. Tau bajo deja la masa en el positivo.

Variantes que también enseñan bien: `pe-heatmap`, `scale-cloud`, `std-z`, `rope-pairs`, `temp-entropy`.

## Fallos

- El primer host (`({ canvas, slider, loop })`) no era el contrato. Se borró. No lo revivas.
- `pe-dimbase` al principio no cambiaba pixeles: la altura quedaba topada en el mínimo y en el máximo. Se bajó el tope. La prueba lo cazó.
- La galería no abre (500 de arriba). El catálogo y la prueba de pixeles sí pasan sin Next.
- Varias variantes son un esquema (una barra, un conteo), no una escena. Sirven como cobertura del tema. Para few-shots usa los 14 primarios.
- El raster cuenta como tinta cualquier pixel que no sea `#fdfaf4`. Un fondo `#f6f3ec` ya cuenta. El control igual tiene que cambiar el digest.
