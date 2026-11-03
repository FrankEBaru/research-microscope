# RRM-81 — Attention offline (compass)

`gh` contra `FrankEBaru/research-microscope-compass` (rama `claude/rrm-50-plan-b1`, `datos/offline/`) respondió **404**. Este repo público no trae el tar v2. Lo que hay que meter en compass, sin copiarlo al mapa de licencias en vivo:

## Licencia

En `licenses-v2.json` (el fetch lo copia a `licenses.json`), la fila real de arXiv más la marca de fixture:

```json
"1706.03762": {
  "license": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
  "version": "v7",
  "corpusid": 13756489,
  "fixture_open": true
}
```

`fixture_open` no abre el paper si `RRM_LICENSE_FIXTURE` no es exactamente `1`. El servidor en vivo no pone esa variable. La clase sigue `closed` y la etiqueta sigue «arXiv license». Sin la fila, el gate deja solo el abstract.

## Consulta `attention`

El fixture local (no va a git; el e-print es de arXiv, no de Modal ni de Meta) sale de:

```bash
python3 scripts/build_attention_fixture.py --out offline-fixtures-attention
RRM_LICENSE_FIXTURE=1 python3 -m rrm.offline --root offline-fixtures-attention
```

Eso escribe, para la pregunta `attention` / slug `attention` / corpus `13756489`:

- `papers/13756489.json` — respuesta de `/paper` (secciones, ecuaciones, figuras, tablas, refs).
- `files/13756489/*.png` — figuras del e-print.
- `status/attention.json`, `burst/attention.json`, `labels/attention.json`.
- `ask/index.json` con la frase  
  `The Transformer is based solely on attention and dispenses with recurrence.`  
  en `frases` y `revisar`.
- `ask/frases.json` y `ask/revisar.json` — veredictos `coincide`, `contradice`, `sin_respaldo`, `te_falto`, citas textuales del paper, `verified: true` donde hay cita. `meta.source` es `rrm-81-fixture` (no es una corrida de Muse). Si compass ya tiene la grabación de Muse para esa pregunta, esa grabación gana: no la reemplaces por esta.

## Chequeo

```bash
node apps/reader/tests/attention_walk.mjs
```

Recorre cada sección en modo Read y guarda `apps/reader/shots/attention/`.
