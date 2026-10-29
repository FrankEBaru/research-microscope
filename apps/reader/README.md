# Reader · motor de lectura v0 (RRM-5)

Prototipo local del lector de papers con zoom de 3 niveles (área → cluster → paper). Un solo motor de render;
cambia el contenido por nivel. **Todo local, sin Modal, sin API de Meta, sin backend.** Costo: $0.

## Correr
```bash
npm install
npm run data      # descarga de arXiv (1 petición cada 3 s) y construye los bundles; NO se commitean
npm run verify    # KaTeX sobre todas las fórmulas + pruebas del instrumento (node --test)
npm run build && python3 -m http.server 3100 -d out   # o: npm run dev
```
Requisitos: Node ≥ 22, pandoc, `pdftocairo` (poppler) y Python 3 (+ numpy solo para `scripts/numpy_check.py`).

## Qué es real y qué es simulado
| Pieza | Estado |
|---|---|
| Render del paper (texto, secciones, listas, notas, figuras, tablas, bibliografía) desde el e-print TeX | Real |
| Ecuaciones (KaTeX), color constante por símbolo, copiar LaTeX | Real |
| Hover en citas, símbolos, notas al pie y celdas de tabla | Real (la lectura de celda es mecánica: fila, columna, valor) |
| Hover en oración: tarjeta lateral | **Simulado** (rotulado «ejemplo simulado») |
| Lectura semántica de celdas de tabla | **Simulado** |
| Ráfaga de ejemplo (preguntas, clusters, vista de un minuto, tensión) | **Curada a mano**; no es la salida del motor de ráfaga |
| Mapa-platina (RRM-10): arrastrar, rueda, lentes ×1/×2/×4/×8, minimapa, retícula, lente con vista de un minuto | Real (interacción); **posiciones ilustrativas** y relaciones: sólidas solo si el build las confirma (bibliografía del paper o frase del abstract), punteadas = curadas |
| Instrumento √d_k (apuesta, deslizadores, histogramas, softmax) | Real: cálculo bajo los supuestos del paper |

Todo lo que no es texto del paper lleva una etiqueta de procedencia (`del paper`, `curado a mano`, `cálculo…`, `ejemplo simulado`).
Nunca se usa la palabra «verificada».

## Fidelidad (medida, no supuesta)
- `scripts/check_math.mjs`: renderiza con KaTeX **todas** las fórmulas de los bundles; las que fallen se listan y la UI las muestra como LaTeX crudo, nunca se omiten. Resultado actual: 145/145 sin error (138 en Attention).
- `scripts/audit_loss.py`: compara las palabras de la prosa del LaTeX (pandoc a markdown, referencia independiente de mi conversor) con las que llegan a la UI. Attention: 22 de 3,247 tokens ≥4 letras no aparecen, todos artefactos de sintaxis (ids de referencia como `tab:variations`, nombres de entorno), no contenido.
- Pérdidas de pandoc detectadas y corregidas en `scripts/build_data.py`: `\caption` dentro de `figure*`/`table*` (se normalizan), figuras en PDF (se convierten a PNG con `pdftocairo`), secciones `\section*` sin numerar, notas `\thanks` de autoría.
- Cada ancla del contenido curado (`content/*.json`) se resuelve por **cita textual**: si no aparece exactamente una vez en el paper, `npm run data` falla.

## Instrumento √d_k (contrato)
Afirmación y supuesto: nota 1 de §3.2.1 de *Attention Is All You Need* (componentes de q y k independientes, media 0, varianza 1; q·k tiene varianza d_k).
El paper no fija la distribución: se usa normal estándar y la UI lo declara. `tests/instrument.test.mjs` (6 pruebas): Var(q·k) ≈ d_k, media ≈ 0, Var(q·k/√d_k) ≈ 1, con σ²=2 la varianza escalada es σ⁴ (no 1), el softmax sin escala es más puntiagudo, y coincidencia con una reimplementación independiente en numpy (`scripts/numpy_check.py` → `tests/numpy_reference.json`).
**El contrato está pendiente de aprobación de Franklin.**

## Datos y licencias
- Los papers y figuras se descargan de arXiv al correr `npm run data` y quedan en `public/papers/` y `.cache/` (ambos en `.gitignore`): el repo es público y `AGENTS.md` prohíbe commitear corpus o PDFs.
- Attention: Google permite reproducir tablas y figuras con atribución para trabajos periodísticos o académicos (aviso visible en la UI). Cada paper enlaza a su original en arXiv.

## Estructura
`content/` ranura curada (papers, ráfaga, símbolos, instrumento) · `scripts/` pipeline y auditorías · `src/lib/` matemática e instrumento · `src/components/` motor, paper, instrumento · `tests/`.
