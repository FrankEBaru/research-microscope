#!/usr/bin/env bash
# Arranca la API local y la UI. Sin Modal ni Meta.
#   RRM_OFFLINE_DIR=<dir con manifest.json>   usa ese directorio. No llama a gh.
#   RRM_OFFLINE_TAR=<.tar.gz o prefijo de *.part-aa…>   lo descomprime en offline-fixtures/.
#   RRM_OFFLINE_SYNTH=1   fixtures sintéticos. No llama a gh.
#   RRM_OFFLINE_VERSION=v2|v3   Release de FrankEBaru/research-microscope-compass
#                               (datos/offline/). Default v2. v3 selecciona offline-fixtures-v3.
#   RRM_OFFLINE_NO_UI=1   solo arranca la API.
# Si no hay carpeta local ni sintéticos, baja el Release con gh. Si gh no está
# autenticado, se detiene y lo dice.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PORT=8787

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta python3. En Frank: source ~/projects/hackaton/activate.sh" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Falta Node. En Frank: source ~/projects/hackaton/activate.sh" >&2
  exit 1
fi

# shellcheck source=scripts/_fixtures.sh
source "$ROOT/scripts/_fixtures.sh"
resolve_fixtures "$ROOT" || exit 1

export RRM_FEATURES="${RRM_FEATURES:-core}"
export NEXT_PUBLIC_RRM_FEATURES="${NEXT_PUBLIC_RRM_FEATURES:-$RRM_FEATURES}"
export NEXT_PUBLIC_BURST_URL="http://127.0.0.1:${PORT}"
export NEXT_PUBLIC_READER_URL="http://127.0.0.1:${PORT}"
export NEXT_PUBLIC_RRM_DEMO_TOKEN="${NEXT_PUBLIC_RRM_DEMO_TOKEN:-local}"
export NEXT_PUBLIC_RRM_OFFLINE=1

python3 -m rrm.offline --root "$FIX_DIR" --host 127.0.0.1 --port "$PORT" &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; }
trap cleanup EXIT
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/', timeout=1)" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.2
done
if [[ "$ready" != 1 ]]; then
  echo "El servidor offline no arrancó en el puerto ${PORT}." >&2
  exit 1
fi

if [[ "${RRM_OFFLINE_NO_UI:-}" == "1" ]]; then
  echo "API local: http://127.0.0.1:${PORT} (sin UI). Ctrl+C la apaga."
  wait "$PID"
  exit $?
fi

echo ""
echo "Ábrelo en el navegador de Windows: http://localhost:3000"
echo "API local: http://127.0.0.1:${PORT}"
echo "Ctrl+C apaga la UI y el servidor."
cd "$ROOT/apps/reader"
if [[ ! -d node_modules ]]; then
  npm ci
fi
exec npm run dev
