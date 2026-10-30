# AGENTS.md — research-microscope (PÚBLICO)

Código de Research Reading Microscope. El código puede ser feo; se pule con el tiempo.

## Qué va aquí
- Código, pipelines, configs sin secretos, README.
- Resultados de corridas: como GitHub Releases (`gh release create artifacts/RRM-n-<slug>-YYYY-MM-DD ...`), nunca commiteados al árbol. El tag lo crea la API; el asset no entra al historial.
- Caché del reader (arXiv + bundles, 40 MB): Release `artifacts/RRM-11-reader-data-2026-10-29`. Restaurar en `apps/reader/` antes de volver a bajar arXiv. Ver `apps/reader/README.md`.
- Datos pesados (índices, embeddings, dumps): en el Volume de Modal, no en git.

## Qué NO va aquí (repo público)
- Secretos: tokens de Modal, keys de Semantic Scholar o Meta. Se leen de variables de entorno (`MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `S2_API_KEY`, ...). Nunca en código, logs, commits ni Releases.
- Datasets, corpus con licencia, PDFs de papers.
- Notas internas, costos, diario, pitch o ideas (van en el repo privado compass).

## Reglas de gasto (obligatorias)
- No correr nada en Modal ni llamar a la API de Meta sin permiso explícito de Franklin, transmitido en la conversación. Mocks primero.
- Cada etapa que gasta: detenerse, reportar costo, tiempo y resultado, y esperar aprobación. Respetar el tope de $ del ticket.
- Lecturas gratuitas (listar apps/volúmenes) sí están permitidas.

## Economía de recursos (tokens y gasto real)
- Intenta gastar poco, pero **no sacrifiques calidad técnica, visual ni experimental por ahorrar**: si una prueba más cara es la que de verdad responde la pregunta, proponla con su costo y espera aprobación. Un ahorro que deja una conclusión débil no es ahorro.
- Cada etapa que gasta tiene un presupuesto fijado por Franklin en el ticket (en dólares, papers, preguntas y minutos). Entra en ese presupuesto. Al 80 % detente y reporta; no lo rebases sin aprobación.
- Pruebas baratas primero (`bash scripts/check.sh`, `npm test`). Solo si pasan, se gasta en Modal o Meta.
- Sin reintentos de llamadas de pago ni corridas repetidas «por si acaso». Un fallo se reporta con su `reason`; no se improvisa otra corrida.
- Al terminar una etapa, o si te detienes, apaga lo que encendiste (`modal app stop <app>`) y verifica con `modal app list`. No dejes `RRM_DEMO_KEEP_WARM` ni `scripts/warm.sh` activos.
- Tokens propios: busca con `grep`/lectura parcial en vez de releer repos, resume salidas largas y no pegues logs completos.
- Reporta siempre costo (medido o, si es estimación, rotulado así), tiempo y resultado.

## Trabajo
- Cada tarea corresponde a un ticket RRM-n del repo compass; PRs titulados `RRM-n: ...`.
- Sin tests ni smoke harness por ahora, hasta que el diseño se asiente. **Excepción (RRM-9, 29 oct):** `apps/reader/` tiene pruebas unitarias, de extremo a extremo y CI (`npm test`); Franklin pidió continuar los tickets planeados, que incluían RRM-9. `bash scripts/check.sh` es el chequeo del repo; no llama a Modal, Semantic Scholar, arXiv ni Meta.
- Nunca inventar resultados; reportar números medidos y marcar estimaciones.
- Semantic Scholar: respetar 1 request/s con backoff exponencial; dar atribución "Semantic Scholar" en la interfaz.
