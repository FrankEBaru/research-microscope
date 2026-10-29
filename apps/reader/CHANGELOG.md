# Puntos de regreso de `apps/reader`

Cada hito tiene un tag anotado; cada cambio posterior va en su propio commit para poder revertirlo solo (`git revert <hash>`).
Volver a un hito sin tocar la historia: `git checkout reader-rrm10-mapa` o `git switch -c prueba reader-rrm10-mapa`.

| Tag | Qué cubre |
|---|---|
| `reader-rrm5-v0` | Primera iteración: render de Attention, 3 niveles, hover, instrumento √d_k |
| `reader-rrm8b-fidelidad` | + banco de fidelidad LaTeX→PDF real→UI y numeración de ecuaciones |
| `reader-rrm10-mapa` | + mapa-platina con lentes y minimapa |
| `reader-rrm8a-5papers` | + pipeline probado con 5 papers (robustez, referencias cruzadas, autor-año) |
| `reader-rrm9-tests` | + pruebas unitarias, e2e y CI |
| `reader-v0.2` | + deslizador Kaplan/Chinchilla, BibTeX, figura acompañante y sus pruebas |

Commits sueltos posteriores a `reader-v0.2` no tienen tag hasta el siguiente hito.
