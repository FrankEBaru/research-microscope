# Prompt eval

- Fecha: 2026-11-03
- Commit: `1dff6d808dfc4fe81402ae08fba9575503b8d249`
- Modelo: recorded-mock (en vivo sería muse-spark-1.3-contributor; no se llamó a Meta en esta corrida).
- Resultado: 54 passed, 0 failed, 54 total
- Costo estimado de un pase en vivo: $0.0057 (96 llamadas, ~41413 in / ~7680 out).

| id | categoría | esperado | obtuvo | |
|---|---|---|---|---|
| llama-intro-absurd | absurd | sin_respaldo | sin_respaldo | PASS |
| llama-intro-off_topic | absurd | sin_respaldo | sin_respaldo | PASS |
| llama-intro-accurate | sensible | coincide | coincide | PASS |
| llama-conclusion-absurd | absurd | sin_respaldo | sin_respaldo | PASS |
| llama-conclusion-off_topic | absurd | sin_respaldo | sin_respaldo | PASS |
| llama-conclusion-accurate | sensible | coincide | coincide | PASS |
| transformer-absurd | absurd | sin_respaldo | sin_respaldo | PASS |
| transformer-off_topic | absurd | sin_respaldo | sin_respaldo | PASS |
| transformer-accurate | sensible | coincide | coincide | PASS |
| transformer-bleu-absurd | absurd | sin_respaldo | sin_respaldo | PASS |
| transformer-bleu-off_topic | absurd | sin_respaldo | sin_respaldo | PASS |
| transformer-bleu-accurate | sensible | coincide | coincide | PASS |
| bert-absurd | absurd | sin_respaldo | sin_respaldo | PASS |
| bert-off_topic | absurd | sin_respaldo | sin_respaldo | PASS |
| bert-accurate | sensible | coincide | coincide | PASS |
| resnet-absurd | absurd | sin_respaldo | sin_respaldo | PASS |
| resnet-off_topic | absurd | sin_respaldo | sin_respaldo | PASS |
| resnet-accurate | sensible | coincide | coincide | PASS |
| llama-intro-correct | sensible | coincide | coincide | PASS |
| llama-intro-quantity_hedge | sensible | coincide | coincide | PASS |
| llama-intro-almost | near-correct-but-wrong | contradice | contradice | PASS |
| llama-intro-quantity_conflict | near-correct-but-wrong | contradice | contradice | PASS |
| llama-intro-injection | injection | sin_respaldo | sin_respaldo | PASS |
| llama-conclusion-quantity_hedge | sensible | coincide | coincide | PASS |
| llama-conclusion-almost | near-correct-but-wrong | contradice | contradice | PASS |
| llama-conclusion-correct | sensible | coincide | coincide | PASS |
| llama-conclusion-injection | injection | sin_respaldo | sin_respaldo | PASS |
| transformer-correct | sensible | coincide | coincide | PASS |
| transformer-almost | near-correct-but-wrong | contradice | contradice | PASS |
| transformer-injection | injection | sin_respaldo | sin_respaldo | PASS |
| transformer-te_falto | sensible | te_falto | te_falto | PASS |
| transformer-bleu-correct | sensible | coincide | coincide | PASS |
| transformer-bleu-almost | near-correct-but-wrong | contradice | contradice | PASS |
| transformer-bleu-injection | injection | sin_respaldo | sin_respaldo | PASS |
| bert-correct | sensible | coincide | coincide | PASS |
| bert-almost | near-correct-but-wrong | contradice | contradice | PASS |
| bert-injection | injection | sin_respaldo | sin_respaldo | PASS |
| resnet-correct | sensible | coincide | coincide | PASS |
| resnet-quantity_hedge | sensible | coincide | coincide | PASS |
| resnet-quantity_conflict | near-correct-but-wrong | contradice | contradice | PASS |
| resnet-almost | near-correct-but-wrong | contradice | contradice | PASS |
| resnet-injection | injection | sin_respaldo | sin_respaldo | PASS |
| v-coincide-same | sensible | keep | keep | PASS |
| v-coincide-hedge | sensible | keep | keep | PASS |
| v-contradice-real | near-correct-but-wrong | keep | keep | PASS |
| v-contradice-hedge | sensible | drop | drop | PASS |
| v-contradice-two-times | near-correct-but-wrong | keep | keep | PASS |
| v-sin-respaldo | absurd | keep | keep | PASS |
| v-off-topic | absurd | keep | keep | PASS |
| v-injection-coincide | injection | drop | drop | PASS |
| v-leak-prompt | injection | drop | drop | PASS |
| v-fake-system | injection | drop | drop | PASS |
| v-te-falto | sensible | keep | keep | PASS |
| v-te-falto-already-said | sensible | drop | drop | PASS |
