# AGENTS.md — research-microscope (PÚBLICO)

Código de Research Reading Microscope. El código puede ser feo; se pule con el tiempo.

## Qué va aquí
- Código, pipelines, configs sin secretos, README.
- Resultados de corridas: como GitHub Releases (`gh release create artifacts/RRM-n-<slug>-YYYY-MM-DD ...`), nunca commiteados al árbol.
- Datos pesados (índices, embeddings, dumps): en el Volume de Modal, no en git.

## Qué NO va aquí (repo público)
- Secretos: tokens de Modal, keys de Semantic Scholar o Meta. Se leen de variables de entorno (`MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `S2_API_KEY`, ...). Nunca en código, logs, commits ni Releases.
- Datasets, corpus con licencia, PDFs de papers.
- Notas internas, costos, diario, pitch o ideas (van en el repo privado compass).

## Reglas de gasto (obligatorias)
- No correr nada en Modal ni llamar a la API de Meta sin permiso explícito de Franklin, transmitido en la conversación. Mocks primero.
- Cada etapa que gasta: detenerse, reportar costo, tiempo y resultado, y esperar aprobación. Respetar el tope de $ del ticket.
- Lecturas gratuitas (listar apps/volúmenes) sí están permitidas.

## Trabajo
- Cada tarea corresponde a un ticket RRM-n del repo compass; PRs titulados `RRM-n: ...`.
- Sin tests ni smoke harness por ahora, hasta que el diseño se asiente.
- Nunca inventar resultados; reportar números medidos y marcar estimaciones.
- Semantic Scholar: respetar 1 request/s con backoff exponencial; dar atribución "Semantic Scholar" en la interfaz.
