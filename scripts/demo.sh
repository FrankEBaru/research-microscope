#!/usr/bin/env bash
# RRM-98 · El demo online en un comando (máquina de Franklin, WSL):
#
#   bash scripts/demo.sh            # deploy de rrm-burst y rrm-reader, build de producción, http://localhost:3100
#   RRM_DEMO_DEPLOY=0 bash scripts/demo.sh   # reusa las URLs del último deploy (.demo-urls), sin modal deploy
#
# Backend: RRM_FEATURES=core, RRM_GROUP_NAMES=1, RRM_LICENSE_GATE=off, RRM_OCR_MAX=0 (sin OCR en GPU).
# UI: build estático con las figuras vivas de RRM-96 (NEXT_PUBLIC_RRM_LIVEART=1); los datos vienen de
# compass vía scripts/liveart_assets.sh. Puerto 3100: es el que está en el CORS de rrm/demo_guard.py.
# Llaves: `source ~/projects/hackaton/envars.sh` lo hace este script; no imprime ninguna.
# Al salir (Ctrl+C o RRM_MAX_MINUTES, default 90) para rrm-burst y rrm-reader y muestra modal app list.
# RRM_DEMO_KEEP=1 los deja arriba al salir (para grabar en otra terminal).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PORT="${RRM_DEMO_PORT:-3100}"
MAX_MIN="${RRM_MAX_MINUTES:-90}"
URLS="$ROOT/.demo-urls"

[[ -f "$HOME/projects/hackaton/.venv/bin/activate" ]] && source "$HOME/projects/hackaton/.venv/bin/activate"
[[ -d "$HOME/.nvm/versions/node/v24.14.0/bin" ]] && export PATH="$HOME/.nvm/versions/node/v24.14.0/bin:$PATH"
if [[ -z "${MODEL_API_KEY:-}" && -f "$HOME/projects/hackaton/envars.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/projects/hackaton/envars.sh"
fi
for v in MODEL_API_KEY S2_API_KEY RRM_DEMO_TOKEN; do
  if [[ -z "${!v:-}" ]]; then echo "Falta $v (source ~/projects/hackaton/envars.sh)." >&2; exit 1; fi
done
for bin in modal node npx python3; do
  command -v "$bin" >/dev/null 2>&1 || { echo "Falta $bin." >&2; exit 1; }
done
if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "El puerto ${PORT} está ocupado: ss -ltnp | grep ${PORT}" >&2
  exit 1
fi

export RRM_FEATURES=core RRM_GROUP_NAMES=1 RRM_LICENSE_GATE=off RRM_OCR_MAX=0 RRM_PANORAMA_MODE=sim RRM_SAM=off
# Integración RRM-97..101: análisis de paper v2 (RRM-99, precalculado en rrm-data:/analysis/v2) y top 3 (RRM-97).
export RRM_ANALYSIS=v2 RRM_PREPARE_TOP=3 NEXT_PUBLIC_RRM_PREPARE_TOP=3
unset RRM_DEMO_KEEP_WARM

UI_PID=""
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "$UI_PID" ]] && { pkill -P "$UI_PID" 2>/dev/null || true; kill "$UI_PID" 2>/dev/null || true; }
  if [[ "${RRM_DEMO_KEEP:-0}" != 1 ]]; then
    modal app stop --yes rrm-burst >/dev/null 2>&1 || true
    modal app stop --yes rrm-reader >/dev/null 2>&1 || true
    echo "rrm-burst y rrm-reader parados."
  fi
  modal app list 2>/dev/null | grep -E "rrm-|App ID" || true
  exit "$status"
}
trap cleanup EXIT INT TERM
( sleep $((MAX_MIN * 60)); kill -TERM $$ 2>/dev/null ) >/dev/null 2>&1 &

deploy() {
  local log url
  log="$(mktemp)"
  if ! modal deploy "$1" >"$log" 2>&1; then
    echo "Falló modal deploy $1 (últimas líneas, sin llaves):" >&2
    tail -n 15 "$log" | grep -viE "key|token|secret" >&2 || true
    rm -f "$log"; return 1
  fi
  url="$(grep -oE 'https://[A-Za-z0-9.-]+\.modal\.run' "$log" | tail -n 1 || true)"
  rm -f "$log"
  [[ -n "$url" ]] || { echo "modal deploy $1 no imprimió una URL." >&2; return 1; }
  printf '%s' "${url%/}"
}

# A deploy leaves the old container serving the old code: stop it so the next request gets the new one.
stop_old_containers() {
  modal container list --json 2>/dev/null | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    name = str(c.get("App Name") or c.get("app_name") or "")
    if name in ("rrm-burst", "rrm-reader"):
        print(c.get("Container ID") or c.get("container_id") or "")
' | while read -r cid; do [[ -n "$cid" ]] && modal container stop --yes "$cid" >/dev/null 2>&1 || true; done
}

if [[ "${RRM_DEMO_DEPLOY:-1}" == 0 && -f "$URLS" ]]; then
  # shellcheck disable=SC1090
  source "$URLS"
  echo "Reuso el último deploy."
else
  echo "modal deploy rrm-burst y rrm-reader (core, nombres de grupo, sin compuerta, sin OCR)…"
  stop_old_containers
  BURST="$(deploy rrm/search/serve.py)"
  READER="$(deploy rrm/reader/serve.py)"
  stop_old_containers
  printf 'BURST=%q\nREADER=%q\n' "$BURST" "$READER" >"$URLS"
fi

bash "$ROOT/scripts/liveart_assets.sh"

cd "$ROOT/apps/reader"
[[ -d node_modules ]] || npm ci
export NEXT_PUBLIC_RRM_FEATURES=core NEXT_PUBLIC_RRM_LIVEART=1
export NEXT_PUBLIC_BURST_URL="$BURST" NEXT_PUBLIC_READER_URL="$READER" NEXT_PUBLIC_RRM_DEMO_TOKEN="$RRM_DEMO_TOKEN"
unset NEXT_PUBLIC_RRM_OFFLINE
rm -rf .next out
echo "next build (producción)…"
npx next build >/tmp/rrm-demo-build.log 2>&1 || { tail -n 30 /tmp/rrm-demo-build.log >&2; exit 1; }
# The token is baked into the static bundle: wipe it from the build log.
rm -f /tmp/rrm-demo-build.log
echo ""
echo "Demo: http://localhost:${PORT}   (Ctrl+C apaga la UI y para las apps de Modal; tope ${MAX_MIN} min)"
npx serve out -l "$PORT" >/dev/null 2>&1 &
UI_PID=$!
wait "$UI_PID"
