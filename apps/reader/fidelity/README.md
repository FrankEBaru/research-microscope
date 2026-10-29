# Banco de fidelidad LaTeX → UI (RRM-8, parte B)

LaTeX real (`pdflatex`) como árbitro del pipeline **pandoc → KaTeX**. `npm run fidelity` (requiere TeX Live, pandoc, poppler, Playwright).
Cada caso de `cases.py` (96: 66 hechos a mano en 15 familias + 30 aleatorios con semilla) se compila a PDF, y la **misma** fuente pasa por el pipeline de `build_data.py` (aplanado, numeración, pandoc) y KaTeX con las opciones de la UI. `out/contact.html` pone los dos lado a lado.

Métricas (solo **triage**, no veredicto): KaTeX sin error; similitud estructural (SSIM sobre imágenes recortadas y desenfocadas); relación de aspecto; letras y dígitos de `pdftotext` presentes en el render (solo si hay ≥8). Lo que queda en «REVISAR» necesita ojo humano.

## Resultado (29 oct 2026, 96 casos)
81 PASA · 15 REVISAR · 0 fallos de KaTeX · 0 fallos de pandoc · 0 LaTeX inválido. Los 10 casos de peor similitud se revisaron a ojo: 8 son equivalentes (cambian tamaño y grosor del trazo), 1 era una pérdida real (**numeración de ecuaciones**, ya corregida: ahora se numera `equation` como LaTeX y no se numera si el paper usa `numberwithin`), y 1 es composición (`align*` ancha en LaTeX frente a `aligned` compacta). Los otros 5 «REVISAR» no se revisaron a ojo.

## Límites
- KaTeX y LaTeX no coinciden píxel a píxel: SSIM es ruidoso (mediana 0.73 con pares equivalentes).
- Un caso aislado no reproduce las macros ni los paquetes de un paper completo.
- Un banco sin fallos no prueba ausencia de fallos: cubre lo que pensamos probar. Casos nuevos entran a `cases.py`.
