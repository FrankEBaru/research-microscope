#!/usr/bin/env bash
# Baja el Release offline-fixtures-v1 y arranca la API local y la UI. Sin Modal ni Meta.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
TAG=offline-fixtures-v1
REPO=FrankEBaru/research-microscope
PORT=8787

if ! command -v gh >/dev/null 2>&1; then
  echo "Falta gh. En WSL: instálalo y corre gh auth login." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta python3." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Falta Node ≥ 22." >&2
  exit 1
fi

if [[ ! -f "$ROOT/offline-fixtures/manifest.json" ]]; then
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
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/', timeout=1)" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

echo "API en http://127.0.0.1:${PORT}  ·  UI en http://localhost:3000"
echo "Ctrl+C apaga las dos."
cd "$ROOT/apps/reader"
if [[ ! -d node_modules ]]; then
  npm ci
fi
exec npm run dev
