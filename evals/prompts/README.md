# Evaluación de prompts

Esta carpeta es el paquete para copiar a compass (`datos/` o donde Franklin lo deje). No tiene claves.

| Archivo | Qué es |
|---|---|
| `cases.json` | Secciones, respuestas simuladas, categoría y veredicto esperado |
| `cases.py` | La misma lista, en código, para el runner |
| `AUDIT.md` | Qué guard había y cuál se añadió |
| `REPORT.md` | Fecha, commit, modelo y pass/fail de la corrida offline |
| `results/offline.json` | Lo mismo, en JSON |
| `recorded/llama_t2.json` | El caso LLaMA T2 y por qué no se leyó el fixture v3 |

Categorías: `absurd`, `sensible`, `injection`, `near-correct-but-wrong`.

Corre sin red. El modelo grabado repite dos fallos: dice `Contradice` cuando la única diferencia es la misma magnitud (LLaMA T2, 10× contra «more than ten times»), y obedece una inyección que pide `Coincide`. El juez de `rrm/reader/feedback.py` tiene que corregirlos. Al terminar escribe `cases.json`, `results/offline.json` y `REPORT.md`.

```bash
python -m evals.prompts
```

Imprime una tabla PASS/FAIL y el costo estimado de un pase en vivo.

En vivo (gasta Meta; no lo corrí):

```bash
RRM_EVAL_LIVE=1 python -m evals.prompts
```

Sin esa variable el runner usa el modelo grabado y no abre la red. Con la variable, cada caso llama a `post_responses` (hace falta `MODEL_API_KEY`). Precios: `muse-spark-1.3-contributor`, los de `rrm/reader/metacall.py`. El proceso imprime el estimado antes de saber el resultado.

`RRM_PROMPT_GUARD=0` quita cercas y el rechazo a inyecciones. `RRM_QTY_EQUIV=0` deja el veredicto del modelo cuando la magnitud está escrita de otra forma. `RRM_SAM_GUARD=1` marca la frase de SAM como dato; por defecto SAM no cambia, porque esa frase es el recorte.
