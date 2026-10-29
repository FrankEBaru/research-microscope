# Puntos de regreso de `apps/reader`

Cada hito está identificado por el hash de su commit y cada cambio posterior va en su propio commit, para revertir uno solo
(`git revert <hash>`) o volver a un hito sin tocar la historia (`git switch -c prueba <hash>`).

| Hito | Commit | Qué cubre |
|---|---|---|
| RRM-5 v0 | `3d59bbb` | Primera iteración: render de Attention, 3 niveles, hover, instrumento √d_k |
| RRM-8 B | `5605e77` | + banco de fidelidad LaTeX→PDF real→UI y numeración de ecuaciones |
| RRM-10 | `17a1c1e` | + mapa-platina con lentes y minimapa |
| RRM-8 A (5 papers) | `9129d07` | + pipeline probado con 5 papers (robustez, referencias cruzadas, autor-año) |
| RRM-9 | `ba729fa` | + pruebas unitarias, e2e y CI |
| v0.2 | `955a37b` | + deslizador Kaplan/Chinchilla, BibTeX, figura acompañante y sus pruebas |
| RRM-11 | `42abbf7` | + compañero opcional (3 personajes), lógica `f365013`, componente `8fdc7a4` y pruebas e2e |

Commits posteriores a `42abbf7` no tienen hito hasta el siguiente.

**Tags:** el entorno de desarrollo no puede subir tags con `git push` (el servidor responde 403: solo permite la rama designada). Un Release sí: `gh release create` crea el tag `artifacts/…` por la API y el binario no entra al historial. El caché del reader es el Release `artifacts/RRM-11-reader-data-2026-10-29`; cómo restaurarlo está en el README. Para un tag de código, desde tu máquina:
```bash
git tag -a reader-v0.2 955a37b -m "v0.2" && git push origin reader-v0.2
```
(y lo mismo con los otros hashes).
