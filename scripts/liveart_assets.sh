#!/usr/bin/env bash
# RRM-98 · Copia los datos de las figuras vivas de RRM-96 a apps/reader/public/liveart96 (fuera de git).
# Los datos viven en compass; el código solo recibe una ruta o URL:
#   RRM_LIVEART_BUNDLE=<ruta a bundle.json | https://…/bundle.json>
# Sin la variable prueba, en orden: un checkout de compass al lado con datos/offline/rrm96-widgets,
# y el Release privado rrm96-widgets de compass (gh release download). Sin Modal ni Meta.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT="$ROOT/apps/reader/public/liveart96"
REPO="${RRM_OFFLINE_REPO:-FrankEBaru/research-microscope-compass}"
mkdir -p "$OUT"

src="${RRM_LIVEART_BUNDLE:-}"
if [[ -z "$src" ]]; then
  # Canonical bundle (RRM-96 + RRM-99) first, then the RRM-96 one.
  for rel in datos/offline/widgets/bundle.json datos/offline/rrm96-widgets/bundle.json; do
    for dir in "$ROOT/../research-microscope-compass" "${HOME:-}/projects/hackaton/research-microscope-compass" "${HOME:-}/projects/hackaton/wt-compass-95"; do
      if [[ -f "$dir/$rel" ]]; then
        src="$dir/$rel"
        break 2
      fi
    done
  done
fi

if [[ -n "$src" && "$src" =~ ^https?:// ]]; then
  curl -fsSL "$src" -o "$OUT/bundle.json"
elif [[ -n "$src" ]]; then
  cp "$src" "$OUT/bundle.json"
elif command -v gh >/dev/null 2>&1; then
  tmp="$(mktemp -d)"
  gh release download rrm96-widgets -R "$REPO" -p 'rrm96-widgets.tar.gz' -D "$tmp" --clobber >/dev/null
  member="$(tar -tzf "$tmp/rrm96-widgets.tar.gz" | grep -E '(^|/)bundle\.json$' | head -n 1)"
  tar -xzf "$tmp/rrm96-widgets.tar.gz" -C "$tmp" "$member"
  mv "$tmp/$member" "$OUT/bundle.json"
  rm -rf "$tmp"
  src="release rrm96-widgets"
else
  echo "No encontré bundle.json: exporta RRM_LIVEART_BUNDLE (ruta o URL)." >&2
  exit 1
fi

font="$ROOT/apps/reader/node_modules/@fontsource-variable/instrument-sans/files/instrument-sans-latin-wght-normal.woff2"
if [[ -f "$font" ]]; then cp "$font" "$OUT/ui.woff2"; fi
n="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("entries", [])))' "$OUT/bundle.json")"
echo "liveart96: ${n} figuras desde ${src} → apps/reader/public/liveart96"
