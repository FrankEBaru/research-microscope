# Reader · motor de lectura v0 (RRM-5)

Prototipo local del lector de papers con zoom de 3 niveles (área → cluster → paper). Un solo motor de render;
cambia el contenido por nivel. **Todo local, sin Modal, sin API de Meta, sin backend.** Costo: $0.

## Correr
Requisitos: Node ≥ 22 y Python 3 (+ numpy solo para `scripts/numpy_check.py`). Pandoc y `pdftocairo` (poppler) hacen falta solo si se vuelve a correr `npm run data`.

Máquina nueva, con el mismo `content/`: el caché ya construido está en un GitHub Release. El tar (40 MB) no está en el árbol ni en el historial de commits.

```bash
npm install
gh release download artifacts/RRM-11-reader-data-2026-10-29 --pattern reader-data-2026-10-29.tar.gz
tar -xzf reader-data-2026-10-29.tar.gz && rm reader-data-2026-10-29.tar.gz
npm run verify    # KaTeX sobre todas las fórmulas + pruebas del instrumento (node --test)
npm run build && python3 -m http.server 3100 -d out   # o: npm run dev
```

Si `content/` cambió, o ese Release no corresponde a este código:

```bash
npm run data      # usa `.cache/` si ya está; si no, arXiv a 1 petición cada 3 s. NO se commitea
```

## Vercel

Export estático (`next.config.mjs`: `output: "export"`, `images.unoptimized: true`). En Vercel Hobby la raíz del proyecto es `apps/reader`, Node 22, build `npm ci && npm run build`. Variables de entorno del proyecto, nunca en git: `NEXT_PUBLIC_BURST_URL`, `NEXT_PUBLIC_READER_URL`, `NEXT_PUBLIC_RRM_DEMO_TOKEN`. Si las dos URLs están vacías, la pantalla sigue siendo la ráfaga curada y no llama al backend. Restaurar `public/papers/` desde el Release RRM-11 antes del build. Este repo no despliega.

## Modo en vivo (backend)

Tres variables de entorno, nunca en git, se inlinean en el export estático:

| Variable | Qué es |
|---|---|
| `NEXT_PUBLIC_BURST_URL` | URL del servicio `rrm-burst` (`/burst`) |
| `NEXT_PUBLIC_READER_URL` | URL del servicio `rrm-reader` (`/status`, `/paper`, `/file`, `/panorama`) |
| `NEXT_PUBLIC_RRM_DEMO_TOKEN` | token de la demo: va en `X-RRM-Demo` y en `?k=` para `/file` |

Con las dos URLs vacías la pantalla es la ráfaga curada y no llama a nada. Si hay URLs y falta el token, la UI falla al cargar. El token queda dentro del bundle: frena a quien solo tiene la URL, no a quien lee el bundle. Contrato de las rutas: `docs/backend-api.md`.

- **Tiempos de espera** (`src/lib/backend.js`): `/burst` 150 s y sin reintento (un contenedor dormido tarda 100–131 s en arrancar); `/status` 20 s y 2 reintentos; `/paper` 40 s y 1 reintento; `/panorama` 20 s y sin reintento. Se reintenta solo en 429, 5xx, tiempo agotado y red caída, con espera creciente.
- **Mensajes**: 401 (token), 403 (origen), 429, 5xx, tiempo agotado y sin conexión se explican en la pantalla, sin token ni URL. Un paper `failed` muestra su `reason`.
- **Papers que no terminan**: tras 90 s con papers en cola aparece «Armar el Panorama con los ya leídos». Los que faltan no cuentan como leídos ni como «no lo dice».
- **Panorama**: con backend, la UI pide `POST /panorama`. El default del servidor es selección simulada (coincidencia de términos, no un modelo). `RRM_PANORAMA_MODE=meta` pide los enunciados a Muse y las citas por índice; si Muse falla, el servidor responde la selección simulada y la UI lo dice. Si el POST falla, la UI cae al simulador del navegador. En todos los casos la compuerta (`validateSelections`) corre en la UI: rechaza toda frase que no exista exactamente una vez en su paper.
- **Zonas y gráficas**: las zonas de figuras están curadas por `arxivId` (`content/zones.json`); un paper en vivo sin zonas curadas no las muestra. Las gráficas de tabla usan `hspan`/`bspan` si el bundle los trae y leen un span ausente como 1.
- `npm run build:live` genera `out-live/` con URLs de prueba (`b.test`, `r.test`) para `npm run test:live`; no llama a ningún servidor real.

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
| Compañero (RRM-11): opcional, apagado por defecto (botón o tecla C), mudo; tres personajes originales; ofrece llevarte a una definición, figura o leyenda tras 3 repeticiones | Real; **no guarda ni envía nada** (comprobado por prueba). Hipótesis, sin evidencia de efecto |
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

## Probado con 5 papers completos (RRM-8 A)
Attention, BERT, Kaplan, Chinchilla y Pearce y Song (e-prints de arXiv): **1,099 de 1,108 fórmulas (99.2%) renderizan** en KaTeX; las 9 restantes usan una macro propia (`\mathpalette`) y se muestran como LaTeX crudo, sin ocultarse. Pérdida de texto (auditoría independiente contra pandoc→markdown): 0.7% a 3.0%; lo que quedó entre los peores bloques es en su mayoría ruido de la referencia (macros y matemática sin delimitar), salvo tablas con celdas anidadas, ya corregidas. Referencias cruzadas resueltas: 83 de 86 en Chinchilla.
Fallos de robustez encontrados y corregidos al ampliar: pandoc se cuelga con la expansión de macros en BERT (tiempo límite y segunda estrategia), líneas en blanco dentro de `\caption`, `\graphicspath`, bibliografías `.bbl` y autor-año, `\label` y `\hat \mathbb{E}` dentro de matemática, ecuaciones de bloque dentro de párrafos, apéndices con letras.

## Datos y licencias
- Los papers y figuras salen de arXiv y quedan en `public/papers/` y `.cache/` (ambos en `.gitignore`). El repo es público: ese corpus no se commitea.
- El mismo resultado, empaquetado, está en el Release [`artifacts/RRM-11-reader-data-2026-10-29`](https://github.com/FrankEBaru/research-microscope/releases/tag/artifacts/RRM-11-reader-data-2026-10-29) (asset `reader-data-2026-10-29.tar.gz`, sha256 `c1ac80888eec76e3c8f46f1e77431fed7739999496d9210b8453d694cc4c7b07`). Corresponde al commit `a0a332a`. Al descomprimirlo en `apps/reader/` aparecen `.cache/` (fichas, e-prints, fuentes y JSON de pandoc: `npm run data` no vuelve a llamar a arXiv) y `public/papers/` (JSON y figuras: se puede saltar `npm run data` y solo construir).
- Attention: Google permite reproducir tablas y figuras con atribución para trabajos periodísticos o académicos (aviso visible en la UI). Cada paper enlaza a su original en arXiv.

## Estructura
`content/` ranura curada (papers, ráfaga, símbolos, instrumento) · `scripts/` pipeline y auditorías · `src/lib/` matemática e instrumento · `src/components/` motor, paper, instrumento · `tests/`.
