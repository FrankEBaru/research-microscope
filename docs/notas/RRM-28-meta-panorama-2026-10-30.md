# RRM-28 — panorama con Muse (2026-10-30)

Rama `feat/rrm-28-meta-panorama`, encima de `fix/rrm-26-sam`. Sin merge. No se tocó `main`, `feat/rrm-22` ni ramas `claude/*`.

## Cómo queda

`RRM_PANORAMA_MODE=sim` sigue siendo el default: no llama a Muse. `meta` usa el mismo cliente que `rrm/search/split.py` (`post_chat`, modelo `muse-spark-1.3-contributor`).

El servidor arma hasta 36 frases candidatas (como máximo 12000 caracteres), en ronda entre papers. Cada frase pasa por `_sentences` y, si la pregunta tiene temas, por `themes_of`. Muse recibe esas frases numeradas y devuelve JSON `{"themes":[{"statement","picks"}]}` con índices en string. El servidor reconstruye la cita desde el índice, así que el texto es la frase del paper. Descarta índice fuera de rango, repetición del mismo par paper+cita, y cita que no aparece exactamente una vez en los bloques (la misma regla que `validateSelections`, incluido el caso del abstract repetido). Si Muse no responde, se vence el tiempo o el JSON no sirve, la respuesta es `sim_panorama` con `mode: "sim"` y `fallback: true`. Un meta que sí respondió lleva `mode: "meta"` y `fallback: false`. El resto del objeto no cambia: `id`, `statement`, `selections[{paper, quote}]`.

El timeout de la llamada es `RRM_PANORAMA_TIMEOUT` (default 15 s, tope 45). Queda debajo de los 20 s con los que el navegador corta `POST /panorama`. Los tokens salen en el log `panorama_meta` (`prompt_tokens`, `completion_tokens`, `total_tokens`). La clave no se escribe.

`POST /panorama` en modo meta ya no responde 501.

## Por qué meta no es el default del demo

Se deja `sim`. En esta corrida, con el contenedor ya despierto, Q3 tardó 21.778 s de pared y 19.691 s solo en Muse. Eso pasa el corte de 20 s del navegador y el default de 15 s del servidor: con el default, Q3 habría caído a sim. Además cada pregunta gasta tokens, y en Q1 las 6 citas salieron de un solo paper. Los enunciados de Muse son mejores que «lo que dicen los papers sobre X», pero el default del demo sigue siendo el camino barato y el que cabe en el timeout.

## Tests sin red

Mock de Muse, sin `MODEL_API_KEY` en la llamada. Caso feliz (la cita es la frase del índice), JSON inválido que cae a sim, índice fuera de rango, cita que está en dos bloques y se descarta. También un string de índice, el tope de caracteres del prompt, y la compuerta de Node sobre las citas reconstruidas.

Medido en esta máquina: `pytest` de `tests/test_panorama.py` y `tests/test_search.py`, 32 passed, 0.56 s. En la misma pasada, Node (`panorama`, `panorama_live`, `musesim`, `backend_net`, `contract`) 27 passed, 2.19 s. Juntos, 4.70 s con un `pytest` más amplio (87 passed, 2.51 s). Esos 2 fallos son `tests/fixtures/demo/paper_sections.json` y `burst.json`, que no están en el checkout; `scripts/check.sh` los baja de un release. No los toqué.

## Corrida real

Tope $1 entre Meta y Modal, parar en $0.80. No se llegó. `RRM_OCR_MAX=0` en el deploy del reader. `RRM_DEMO_KEEP_WARM` no se usó. `RRM_PANORAMA_TIMEOUT=40` solo en el deploy de medición, para ver la respuesta de Muse y no el fallback de los 15 s.

Los 10 papers de cada pregunta salieron de `GET /burst?n=10` y ya estaban en el volumen (`done` o `abstract_only`). `POST /panorama` solo leyó. Comparé `ocr_gpu_s` y `ocr_invoked_at` de los 20 ids antes y después: ningún cambio. El 6628106 sigue con `ocr_gpu_s=490.12` y `ocr_invoked_at` vacío, de una corrida anterior.

| | temas | citas | pasan la compuerta de la UI | pared HTTP (contenedor despierto) | Muse | tokens (prompt + completion = total) |
|---|---|---|---|---|---|---|
| Q1 meta | 3 | 6 | 6 de 6, 0 rechazadas | 14.171 s | 12.265 s | 1935 + 929 = 2864 |
| Q1 sim | 3 | 17 | 17 de 17, 0 rechazadas | 0.914 s | — | 0 |
| Q3 meta | 3 | 17 | 17 de 17, 0 rechazadas | 21.778 s | 19.691 s | 1818 + 1078 = 2896 |
| Q3 sim | 4 | 25 | 25 de 25, 0 rechazadas | 1.015 s | — | 0 |

Q1: «how does self-attention replace recurrence in sequence translation». Q3: «neural radiance fields view synthesis». Sim en el servidor no lleva `mode` (el default no marca). El JSON de sim del servidor coincidió con `sim_panorama` local sobre los mismos `paper.json`. Meta no descartó ningún índice (`dropped_range=0`, `dropped_repeat=0`, `dropped_unmatched=0`). Candidatas: 36 en las dos. `prompt_chars` 8672 y 7836. El campo `cost` del usage vino `null`.

Enunciados de sim: «Lo que dicen los papers sobre «attention» / «recurrence» / «translation»» (Q1, 5+6+6 citas) y «radiance» / «fields» / «view» / «synthesis» (Q3, 6+6+6+7). Los de meta son afirmaciones. Q1 meta usó un solo paper (13756489) en las 6 citas. Q3 meta usó 6 papers (220968781, 227254854, 232045969, 232352655, 246016186, 260545139).

Ejemplo Q1, primer enunciado, citas literales:

- statement: «The Transformer is the first sequence transduction model to replace recurrent encoder-decoder layers with multi-headed self-attention.»
- 13756489: «In this work, we presented the Transformer, the first sequence transduction model based entirely on attention, replacing the recurrent layers most commonly used in encoder-decoder architectures with multi-headed self-attention.»
- 13756489: «Recurrent neural networks, long short-term memory and gated recurrent neural networks in particular, have been firmly established as state of the art approaches in sequence modeling and transduction problems such as language modeling and machine translation .»

La segunda frase es del paper, la compuerta la acepta, y no dice lo que afirma el enunciado.

## Costo

Factura Modal de hoy (`modal billing report --for today`), delta entre antes del deploy y después del stop:

| app | antes | después | delta |
|---|---|---|---|
| rrm-burst | 0.08981541 | 0.10936431 | 0.01954890 |
| rrm-reader | 0.17365759 | 0.17418024 | 0.00052265 |
| suma | 0.26347300 | 0.28354455 | 0.02007155 |

Meta no devolvió dólares. Estimación con la tarifa publicada de `muse-spark-1.3-contributor` (input $0.10 / 1M, output $0.20 / 1M, [Pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits), leída el 2026-10-30), usando `prompt_tokens` como input y `completion_tokens` como output, sin saber si hubo caché: 3753 × 0.10 / 1e6 + 2007 × 0.20 / 1e6 = 0.0007767. No es una factura. Suma Modal medido + esa estimación: 0.02084825. Por debajo de $0.80.

## Bugs

- [V] Q3 en caliente tardó 21.778 s de pared. El navegador corta `/panorama` a los 20 s, así que la UI de la demo no llegaría a ver este meta.
- [V] Muse en Q3 tardó 19.691 s. El timeout default de 15 s habría hecho fallback a sim. La medición usó 40 s a propósito.
- [V] En Q1 las 6 citas son del corpus 13756489. La segunda de t0 (RNNs como estado del arte) y la primera de t2 (End-to-end memory networks) no sostienen el enunciado. La compuerta solo mira que la frase exista una vez.

## Apagado

`modal app stop --yes rrm-reader` y `modal app stop --yes rrm-burst`. Las dos apps de este deploy (creadas 2026-10-30 17:51 UTC) quedaron `stopped`, 0 tasks, paradas a las 2026-10-30 17:58 UTC. `modal container list` quedó vacío. `modal app list` no muestra ninguna de las dos en otro estado.
