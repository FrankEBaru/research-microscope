Cada `*.mjs` de esta carpeta se importa en orden alfabético después de los pasos fijos de `shots.mjs`.
Exporta `export default async function (page, { width, base, shot, fixtures })`; `shot(name)` guarda `apps/reader/shots/<ancho>-<name>.png`.
`page` queda en el paper completo de los datos; un fallo del paso se anota como omitido en `report.json`.
