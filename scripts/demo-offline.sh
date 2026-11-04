#!/usr/bin/env bash
# Demo offline en un comando: respuestas grabadas de la pasada final (RRM-95, 4 nov), widgets vivos,
# build de producción. Sin Modal ni Meta. Los datos viven en compass (privado), nunca en este repo.
#
#   RRM_OFFLINE_DIR=<dir con manifest.json> bash scripts/demo-offline.sh
#   (sin RRM_OFFLINE_DIR: baja el Release privado `rrm-final-offline` de compass con gh)
#   RRM_DEMO_PORT=3000 (default)   RRM_OFFLINE_API_PORT=8787 (default)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PORT="${RRM_DEMO_PORT:-3000}"
API="${RRM_OFFLINE_API_PORT:-8787}"
[[ -d "$HOME/.nvm/versions/node/v24.14.0/bin" ]] && export PATH="$HOME/.nvm/versions/node/v24.14.0/bin:$PATH"
FIX="${RRM_OFFLINE_DIR:-}"
if [[ -z "$FIX" ]]; then
  FIX="$ROOT/offline-final/offline-final"
  if [[ ! -f "$FIX/manifest.json" ]]; then
    mkdir -p "$ROOT/offline-final"
    gh release download rrm-final-offline -R "${RRM_OFFLINE_REPO:-FrankEBaru/research-microscope-compass}" -p '*.tar.gz' -D "$ROOT/offline-final" --clobber
    tar -xzf "$ROOT"/offline-final/*.tar.gz -C "$ROOT/offline-final"
  fi
fi
[[ -f "$FIX/manifest.json" ]] || { echo "Falta manifest.json en $FIX" >&2; exit 1; }
export RRM_FEATURES=core RRM_LICENSE_GATE=off RRM_META=off
python3 -m rrm.offline --root "$FIX" --host 127.0.0.1 --port "$API" &
API_PID=$!
UI_PID=""
trap 'kill $API_PID ${UI_PID:-} 2>/dev/null || true' EXIT INT TERM
bash "$ROOT/scripts/liveart_assets.sh"
cd "$ROOT/apps/reader"
[[ -d node_modules ]] || npm ci
export NEXT_PUBLIC_RRM_FEATURES=core NEXT_PUBLIC_RRM_LIVEART=1 NEXT_PUBLIC_RRM_OFFLINE=1 NEXT_PUBLIC_RRM_PREPARE_TOP=3
export NEXT_PUBLIC_BURST_URL="http://127.0.0.1:$API" NEXT_PUBLIC_READER_URL="http://127.0.0.1:$API" NEXT_PUBLIC_RRM_DEMO_TOKEN=local
rm -rf .next out
echo "next build (producción, offline)…"
npx next build >/tmp/rrm-demo-offline-build.log 2>&1 || { tail -n 30 /tmp/rrm-demo-offline-build.log >&2; exit 1; }
echo ""
echo "Demo offline: http://localhost:${PORT}   (preguntas grabadas en la pantalla de inicio; Ctrl+C apaga)"
npx serve out -l "$PORT" >/dev/null 2>&1 &
UI_PID=$!
wait "$UI_PID"
