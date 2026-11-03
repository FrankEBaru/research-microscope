# Contrato rrm-widget/0.2

Fecha: 2026-11-03. Dueño del texto: RRM-78. Dueño del iframe, el AST y el runtime: RRM-79.
Si RRM-79 cambia un límite, sube la versión y el prompt lee `rrm/liveart/contract.py`.

La bandera sale apagada. `RRM_LIVE_ARTIFACTS` o `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS` en `1` encienden el camino vivo. Sin ella, `path_for` devuelve `static` y se queda el artefacto que ya dibuja el lector.

## Camino

1. Selector. `widget`, `static` o `skip`.
2. Preguntas de un recién llegado (2 a 4), solo si el mérito es `widget`.
3. Explicación de una o dos frases: qué se ve al mover el control.
4. Código, un JSON de este contrato.
5. Verificador. Si falla, se cae al artefacto estático. No se muestra un widget a medias.

El enunciado, el latex y el contexto van entre `<<<` y `FIN`. Son dato. Una orden metida ahí (`ignore previous instructions`, un fetch, “el mérito debe ser widget”) es `skip` / rechazo, aunque la fórmula sea real.

## JSON

Llaves: `id`, `topic`, `title`, `explain`, `questions`, `controls`, `draw`. Ninguna más.

`draw` es `function draw(ctx, state, t)`. Puede declarar funciones adentro. `state.w` y `state.h` los pone el host. `t` es segundos; se usa solo si el fenómeno se mueve solo. El mismo `state` y el mismo `t` dibujan lo mismo.

Controles: 1 a 4. `id` en minúsculas (`^[a-z][a-z0-9_]{0,15}$`), `min < max`, `step > 0`, `value` dentro del rango. `w`, `h` y `t` no se declaran.

El draw tiene que leer al menos un control (`state.base`, no solo `state.w`). Si no lo lee, el verificador devuelve `dead_control`.

Límites: draw 3500 caracteres, title 80, explain 360, cada pregunta 12–160 y termina en `?`, el porqué 140, la etiqueta 24, preguntas 2–4.

## Qué puede tocar el draw

Canvas 2d: `clearRect`, `fillRect`, `strokeRect`, `beginPath`, `closePath`, `moveTo`, `lineTo`, `arc`, `ellipse`, `rect`, `fill`, `stroke`, `fillText`, `save`, `restore`, `translate`, `rotate`, `scale`, `fillStyle`, `strokeStyle`, `lineWidth`, `font`, `globalAlpha`.

Math: `sin`, `cos`, `tan`, `exp`, `log`, `sqrt`, `abs`, `min`, `max`, `pow`, `floor`, `ceil`, `round`, `PI`, `E`.

Prohibido en el fuente (la lista viva está en `contract.py`): red, `fetch`, `eval`, `Function`, `import`, `document`, `window`, almacenamiento, `postMessage`, `innerHTML`, `setTimeout`, `requestAnimationFrame`, `Math.random`, `Date`, `Worker`, `WebAssembly`, `http://` y `https://`.

## Temas que el selector ya reconoce

La lista viva está en `offline.py` (`TOPICS`): encoding posicional, temperatura, raíz de d_k, sigma, RoPE, DPO, YaRN, borrador, ruido, guía, DETR, atajo, top-p, contraste, y también RMSNorm, SwiGLU, GQA, multi-head, ALiBi, GELU, suavizado de etiquetas, dropout, calentamiento, MoE, top-k y focal loss.

Un resultado (BLEU, “N× smaller”, “8x deeper”, outperforms) es `skip`. Una fórmula que no es de esos temas es `static`. Texto absurdo o una inyección es `skip`.

## Few-shots

Cuatro draws de oro en `fewshots.py`: base del encoding posicional (también usa `t`), temperatura del softmax, escala por la raíz de `d_k`, desviación estándar. El prompt de código los incluye completos. Otros treinta, en `emulated.py`, pasan el verificador pero no entran al prompt: inflarlo con treinta ejemplos lo pone peor. RRM-80 puede cambiar un draw; la forma no.

El verificador offline ya rechaza forma mala, API prohibida, tema cruzado, un enunciado que es una orden, y un widget que copia esa orden al título, la explicación o el draw. `intuitive` y `answers_a_question` quedan para el verificador de modelo, cuando haya sandbox.

`prompts.schemas()` devuelve el JSON Schema de cada paso (`additionalProperties: false`). `prompts.package(claim)` arma la decisión, las preguntas, la explicación y, solo con la bandera, los mensajes. Sin bandera, `messages` es `None`.

## Qué no entra en 0.2

El iframe, el CSP, el tope de tiempo y el validador AST. Los hace RRM-79 contra esta lista. Hasta que existan, no se llama a Meta.
