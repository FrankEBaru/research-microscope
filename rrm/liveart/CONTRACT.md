# Contrato rrm-widget/0.3

Fecha: 2026-11-03. Dueño del texto del prompt: RRM-78. Dueño del iframe, el AST y el runtime: RRM-79.
La forma del JSON no cambió desde 0.2. Sube la versión porque cambian presupuestos (tamaño, controles, lienzo, tiempo) y la lista de Math y de canvas.

La bandera sale apagada. `RRM_LIVE_ARTIFACTS` o `NEXT_PUBLIC_RRM_LIVE_ARTIFACTS` en `1` / `true` / `yes` / `on` encienden el camino vivo. Sin ella, `path_for` devuelve `static` y se queda el artefacto que ya dibuja el lector. La galería de prueba está en `/liveart` y tampoco monta iframes con la bandera apagada.

## Camino

1. Selector. `widget`, `static` o `skip`.
2. Preguntas de un recién llegado (2 a 4), solo si el mérito es `widget`.
3. Explicación de una o dos frases: qué se ve al mover el control.
4. Código, un JSON de este contrato.
5. Verificador. Si falla, se cae al artefacto estático: la galería deja la explicación y las preguntas, y quita los sliders. No se muestra un widget a medias. Un reintento de código está escrito y apagado (`RRM_LIVE_REPAIR`). Es un solo llamado, con el motivo del motor, sin los ejemplos de oro, y el motor vuelve a revisar. No reemplaza ese chequeo. No corre hasta que una sonda lo encienda.

El enunciado, el latex y el contexto van entre `<<<` y `FIN`. Son dato. Una orden metida ahí (`ignore previous instructions`, un fetch, “el mérito debe ser widget”) es `skip` / rechazo, aunque la fórmula sea real.

## JSON

Llaves: `id`, `topic`, `title`, `explain`, `questions`, `controls`, `draw`. Ninguna más.

`draw` es `function draw(ctx, state, t)`. Puede declarar funciones adentro. `state.w` y `state.h` los pone el host. `t` es segundos; se usa solo si el fenómeno se mueve solo. El mismo `state` y el mismo `t` dibujan lo mismo.

`topic` es un identificador (`^[a-z][a-z0-9_]{0,31}$`). El selector mantiene su lista en `offline.py`. Un tema nuevo (otro paper, otra ecuación) no cambia la forma del contrato: se agrega el nombre a esa lista. El sandbox acepta cualquier tema con esa forma, porque el tipo de figura no es el tema. Con el mismo `draw` se hacen curvas, animaciones, pasos (un control `step`) y geometría 2D.

Controles: 1 a 6. `id` en minúsculas (`^[a-z][a-z0-9_]{0,15}$`), `min < max`, `step > 0`, `value` dentro del rango. `w`, `h` y `t` no se declaran. Cada control tiene que leerse (`state.base`) y mover el dibujo.

Límites: draw 8000 caracteres, title 80, explain 420, cada pregunta 12–180 y termina en `?`, el porqué 160, la etiqueta 28, preguntas 2–4. El JSON entero, 20000 caracteres.

## Qué puede tocar el draw

Canvas 2d: `clearRect`, `fillRect`, `strokeRect`, `beginPath`, `closePath`, `moveTo`, `lineTo`, `arc`, `ellipse`, `rect`, `fill`, `stroke`, `fillText`, `save`, `restore`, `translate`, `rotate`, `scale`, `fillStyle`, `strokeStyle`, `lineWidth`, `font`, `globalAlpha`, `lineCap`, `lineJoin`, `textAlign`, `textBaseline`.

Math: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `exp`, `log`, `sqrt`, `abs`, `hypot`, `sign`, `min`, `max`, `pow`, `floor`, `ceil`, `round`, `PI`, `E`.

El lenguaje es un subconjunto: `var` o `const`, `if` / `else`, `for`, `while`, `break`, `continue`, funciones anidadas, arreglos, `===` y `!==`. `undefined` es un valor y no hace falta declararlo. Un string solo expone `.length` (los arreglos también). Un número puede usar `toFixed` con hasta 6 decimales. Sin flechas, sin `new`, sin `import`, sin acceso `obj["constructor"]`, sin otros métodos de string. `setLineDash` no está: una línea punteada son segmentos cortos. El tope de 200000 pasos se queda; un NeRF con seis bucles anidados no monta aunque el verificador de modelo lo acepte.

Prohibido en el fuente (la lista viva está en `contract.py`): red, `fetch`, `eval`, `Function`, `import`, `document`, `window`, almacenamiento, `postMessage`, `innerHTML`, `setTimeout`, `requestAnimationFrame`, `Math.random`, `Date`, `Worker`, `WebAssembly`, `http://` y `https://`.

## Host

Lienzo lógico **640×360**, inyectado como `state.w` y `state.h`. El iframe es `sandbox="allow-scripts"` y no lleva `allow-same-origin`. CSP del documento: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'`.

Los sliders viven en el padre. El padre manda `{type:"rrm-params", state, t}`. El iframe contesta `{type:"rrm-live", ok}`. Se comprueba `event.source`, no el origen (dentro del sandbox opaco es `null`).

Si el draw lanza, no pinta, o no responde en **1000 ms**, el padre quita el iframe y deja la explicación escrita en la tarjeta. El intérprete del verificador corta a las **200000** operaciones, así que un `while (true)` no llega a montarse. `t` se anima solo si el cuerpo lo usa.

## Slop

Antes de montar, el verificador del motor rechaza:

- `dead_control`: ningún control se lee.
- `slop_inert:<id>`: ese control no mueve ninguna primitiva de dibujo en al menos 2 px entre su mínimo y su máximo. El texto solo no cuenta, y tampoco un cambio que solo recolorea la misma figura.
- `slop_unrelated`: el enunciado no comparte un tema ni una palabra de contenido con el título, la explicación o las preguntas. El enlace es bilingüe: un tema corto escrito igual en los dos lados (GQA), un token con guion bajo (`p_drop`), o una marca conocida del tema (ruido, guía, atajo, masa, lote, maestro, y las demás de esa lista) cuando el enunciado trae la pista inglesa de ese mismo tema.
- `slop_seal`: un `fillText` pinta «verified», «from the paper» o una palomita.
- `injection`: el enunciado o la copia piden ignorar reglas, filtrar el prompt o llamar a `fetch`. Un enlace de tema no los perdona.
- `blank`, `step_cap`, `banned`, `syntax`.

Eso no decide si la figura enseña la ecuación. `intuitive` y `on_claim` siguen siendo del verificador de modelo. El motor agarra el control muerto y el texto que no toca el enunciado.

## Temas que el selector ya reconoce

La lista viva está en `offline.py` (`TOPICS`) a partir de 0.2: encoding posicional, temperatura, raíz de d_k, sigma, RoPE, DPO, YaRN, borrador, ruido, guía, DETR, atajo, top-p, y los que RRM-78 agregó en su rama (RMSNorm, SwiGLU, GQA, y el resto). `quant` es el paso absmax de LLM.int8 (control `mag`, la explicación dice «error»). SmoothQuant sigue en su fila. «We quantize the weights to 8 bits», sin máximo ni magnitud, sigue en `skip`. Un resultado (BLEU, “N× smaller”, outperforms) es `skip`. Una fórmula que no es de esos temas es `static`. Texto absurdo o una inyección es `skip`.

## Few-shots

Cuatro draws de oro en `fewshots.py`. El prompt de código los incluye completos. La galería `/liveart` además muestra figuras más grandes (pico de similitud, RoPE, temperatura, escala, sigma) y tres de RRM-82 que el sandbox aceptó: RoPE que no se mueve al desplazar los dos tokens, softmax por bloques que cae sobre el softmax completo, y el BPE de las cuatro palabras del paper. RRM-80 puede cambiar un draw; la forma no.

## Qué no entra aquí

Integrar el widget en `GapNotes`. La bandera apagada deja el lector como está. No se llama a Meta hasta que el sandbox acepte los de oro y rechace `fetch` / un bucle.
