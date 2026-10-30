#!/usr/bin/env bash
# Baja el Release offline-fixtures-v1 y arranca la API local y la UI. Sin Modal ni Meta.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
TAG=offline-fixtures-v1
REPO=FrankEBaru/research-microscope
PORT=8787

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta python3. En Frank: source ~/projects/hackaton/activate.sh" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Falta Node. En Frank: source ~/projects/hackaton/activate.sh" >&2
  exit 1
fi

if [[ ! -f "$ROOT/offline-fixtures/manifest.json" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "Faltan las consultas grabadas y no está gh. Instala gh y corre gh auth login." >&2
    exit 1
  fi
  gh release download "$TAG" --repo "$REPO" --pattern "${TAG}.tar.gz" --clobber --dir "$ROOT"
  tar -xzf "$ROOT/${TAG}.tar.gz" -C "$ROOT"
  rm -f "$ROOT/${TAG}.tar.gz"
fi

export NEXT_PUBLIC_BURST_URL="http://127.0.0.1:${PORT}"
export NEXT_PUBLIC_READER_URL="http://127.0.0.1:${PORT}"
export NEXT_PUBLIC_RRM_DEMO_TOKEN="${NEXT_PUBLIC_RRM_DEMO_TOKEN:-local}"
export NEXT_PUBLIC_RRM_OFFLINE=1

python3 -m rrm.offline --root "$ROOT/offline-fixtures" --host 127.0.0.1 --port "$PORT" &
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

echo ""
echo "Ábrelo en el navegador de Windows: http://localhost:3000"
echo "API local: http://127.0.0.1:${PORT}"
echo "Ctrl+C apaga la UI y el servidor."
cd "$ROOT/apps/reader"
if [[ ! -d node_modules ]]; then
  npm ci
fi
exec npm run dev
