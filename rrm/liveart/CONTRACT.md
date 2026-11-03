# Contrato rrm-widget/0.3

Fecha: 2026-11-03. Dueño del texto del prompt: RRM-78. Dueño del iframe, el AST y el runtime: RRM-79.
La forma del JSON no cambió desde 0.2. Sube la versión porque cambian presupuestos (tamaño, controles, lienzo, tiempo) y la lista de Math y de canvas. El prompt lee `rrm/liveart/contract.py`.

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

Controles: 1 a 6. `id` en minúsculas (`^[a-z][a-z0-9_]{0,15}$`), `min < max`, `step > 0`, `value` dentro del rango. `w`, `h` y `t` no se declaran.

El draw tiene que leer al menos un control (`state.base`, no solo `state.w`). Si no lo lee, el verificador devuelve `dead_control`.

Límites: draw 8000 caracteres, title 80, explain 420, cada pregunta 12–180 y termina en `?`, el porqué 160, la etiqueta 28, preguntas 2–4. El JSON entero, 20000 caracteres.

## Qué puede tocar el draw

Canvas 2d: `clearRect`, `fillRect`, `strokeRect`, `beginPath`, `closePath`, `moveTo`, `lineTo`, `arc`, `ellipse`, `rect`, `fill`, `stroke`, `fillText`, `save`, `restore`, `translate`, `rotate`, `scale`, `fillStyle`, `strokeStyle`, `lineWidth`, `font`, `globalAlpha`, `lineCap`, `lineJoin`, `textAlign`, `textBaseline`.

Math: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `exp`, `log`, `sqrt`, `abs`, `hypot`, `sign`, `min`, `max`, `pow`, `floor`, `ceil`, `round`, `PI`, `E`.

El lenguaje del sandbox es un subconjunto: `var` o `const`, `if` / `else`, `for`, `while`, funciones anidadas, arreglos, `===` y `!==`. Un string solo expone `.length`. Sin flechas, sin `new`, sin `toFixed`, sin `slice`.

Prohibido en el fuente (la lista viva está en `contract.py`): red, `fetch`, `eval`, `Function`, `import`, `document`, `window`, almacenamiento, `postMessage`, `innerHTML`, `setTimeout`, `requestAnimationFrame`, `Math.random`, `Date`, `Worker`, `WebAssembly`, `http://` y `https://`.

## Temas que el selector ya reconoce

La lista viva está en `offline.py` (`TOPICS`): encoding posicional, temperatura, raíz de d_k, sigma, RoPE, DPO, YaRN, borrador, ruido, guía, DETR, atajo, top-p, contraste, GIoU, recorte de PPO, frecuencias de NeRF, parche de ViT, y también RMSNorm, SwiGLU, GQA, multi-head, ALiBi, GELU, suavizado de etiquetas, dropout, calentamiento, MoE, top-k y focal loss. Los de varios pasos: softmax por bloques, valle de Chinchilla, Adam, largo óptimo del borrador, YaRN por partes, BatchNorm, temperatura de destilación, LoRA, KL del RLHF, haz, fusiones BPE, SmoothQuant y delta de un modelo selectivo. La segunda ola vive en `wave2.py` y entra delante: DDIM, AdamW, CutMix, SGDR, SAC, recorte de gradiente, atrous, SAM, Mixup, Soft-NMS, GAE, GroupNorm, Lookahead, double descent, lottery ticket, PagedAttention, ZeRO, RetNet, FaceNet, Huber, capacidad de Switch, penalización de largo, EMA, calendario coseno, replay priorizado, epsilon-greedy, retorno descontado, Polyak, ventana deslizante, attention sink, negative sampling, checkpointing, burbuja de pipeline, linear scaling, ArcFace, flow matching, consistency, Min-SNR, Medusa, multi-query, soft-cap de logits, pre-norm, stochastic depth, buckets de T5, BigBird, Linformer, CIoU y SWA.

Un resultado (BLEU, “N× smaller”, “8x deeper”, outperforms) es `skip`. Una fórmula que no es de esos temas es `static`. Texto absurdo o una inyección es `skip`.

Un adorno es `skip` con razón `slop`: confeti, arcoíris, rebote, o un slider que solo cambia color o la velocidad de una animación. Un mecanismo con su parámetro no es slop. El verificador también devuelve `slop` si el draw lee el control solo para pintar (`fillStyle`, `strokeStyle`, `globalAlpha`), si el id es de adorno (`hue`, `speed`, `bounce`), o si el draw trae un sello (`verified`, `from the paper`, ✓). El esquema del verificador incluye `not_slop`.

Dos controles enlazados caben en el máximo de 6 cuando cada uno es un parámetro del enunciado y el dibujo muestra cómo se cruzan. Un control también puede recorrer un paso (bloques, fusiones, el presupuesto). `t` solo si el fenómeno se mueve solo.

## Host

Lienzo lógico **640×360**, inyectado como `state.w` y `state.h`. El iframe es `sandbox="allow-scripts"` y no lleva `allow-same-origin`. CSP: `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'`. El padre corta a los **1000 ms**. El intérprete corta a las **200000** operaciones. La galería de prueba aparte del lector sigue en `liveart/host/gallery.html`. El sandbox del lector está en `apps/reader/src/lib/liveart/` y la ruta `/liveart`, con la bandera apagada. No está conectada a `GapNotes`.

## Few-shots

Cuatro draws de oro en `fewshots.py`: base del encoding posicional (la onda y el parecido entre posiciones; también usa `t`), temperatura del softmax, escala por la raíz de `d_k`, desviación estándar. El prompt de código los incluye completos. El resto vive en `emulated.py` y no entra al prompt: entre ellos, RoPE con dos controles (la distancia abre el ángulo; correr ambos lo deja igual). RRM-80 puede cambiar un draw; la forma no.

El verificador offline ya rechaza forma mala, API prohibida, tema cruzado, un enunciado que es una orden, y un widget que copia esa orden al título, la explicación o el draw. `intuitive` y `answers_a_question` quedan para el verificador de modelo, cuando haya sandbox.

`prompts.schemas()` devuelve el JSON Schema de cada paso (`additionalProperties: false`). `prompts.package(claim)` arma la decisión, las preguntas, la explicación y, solo con la bandera, los mensajes. Sin bandera, `messages` es `None`.

## Qué no entra en 0.3

Integrar el widget en `GapNotes`. La bandera apagada deja el lector como está. No se llama a Meta hasta que Franklin pida la pasada.
