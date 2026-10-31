#!/usr/bin/env bash
# Un comando para la máquina Frank (WSL). Las llaves vienen de
#   source ~/projects/hackaton/activate.sh
# y no se imprimen ni se escriben en el repo.
#
#   RRM_LIVE=off|modal|meta|full bash scripts/live.sh
#
# off   — scripts/offline.sh (sin Modal ni Meta). RRM_FEATURES=core.
# modal — deploy de ráfaga y lector, panorama sim, SAM apagado. RRM_FEATURES=core.
# meta  — datos grabados; POST /panorama llama a Muse. Sin deploy. RRM_FEATURES=all.
# full  — deploy con panorama meta y SAM. RRM_FEATURES=all.
#
# RRM_FEATURES=core (default de off y modal) apaga Panorama, subtemas Muse y SAM.
# meta y full ponen all si la variable no viene puesta, para conservar ese comportamiento.
# core no llama a Meta aunque el modo pida panorama meta.
#
# Al salir (Ctrl+C, error o RRM_MAX_MINUTES, default 30) para rrm-burst y
# rrm-reader y muestra modal app list. off no llega a ese trap: lo apaga
# scripts/offline.sh. Este script no pone RRM_DEMO_KEEP_WARM.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
MODE="${RRM_LIVE:-off}"
MAX_MIN="${RRM_MAX_MINUTES:-30}"
PORT=8787
FIX_DIR="${RRM_OFFLINE_DIR:-$ROOT/offline-fixtures}"

if [[ -z "${RRM_FEATURES:-}" ]]; then
  case "$MODE" in
    meta|full) RRM_FEATURES=all ;;
    *) RRM_FEATURES=core ;;
  esac
fi
if [[ "$RRM_FEATURES" != "core" && "$RRM_FEATURES" != "all" ]]; then
  echo "RRM_FEATURES debe ser core o all." >&2
  exit 2
fi
export RRM_FEATURES
export NEXT_PUBLIC_RRM_FEATURES="$RRM_FEATURES"

if [[ "$MODE" == "off" ]]; then
  echo "Modo: off. Features: ${RRM_FEATURES}. Igual que scripts/offline.sh. Sin Modal ni Meta."
  exec bash "$ROOT/scripts/offline.sh"
fi

case "$MODE" in
  modal|meta|full) ;;
  *)
    echo "RRM_LIVE debe ser off, modal, meta o full." >&2
    exit 2
    ;;
esac

if ! [[ "$MAX_MIN" =~ ^[0-9]+$ ]] || [[ "$MAX_MIN" -lt 1 ]]; then
  echo "RRM_MAX_MINUTES debe ser un entero >= 1 (default 30)." >&2
  exit 2
fi

for bin in modal node npm; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Falta $bin. En Frank: source ~/projects/hackaton/activate.sh" >&2
    exit 1
  fi
done
if [[ "$MODE" == "meta" ]] && ! command -v python3 >/dev/null 2>&1; then
  echo "Falta python3. En Frank: source ~/projects/hackaton/activate.sh" >&2
  exit 1
fi

unset RRM_DEMO_KEEP_WARM
CAP_FILE="$(mktemp)"
rm -f "$CAP_FILE"
DEPLOY_LOG=""
DEPLOY_PID=""
API_PID=""
UI_PID=""
WATCH_PID=""
_cleaned=0

case "$MODE" in
  modal)
    export RRM_PANORAMA_MODE=sim
    export RRM_SAM=off
    REMINDER="Pudo gastar dinero: Modal (el deploy y los contenedores de rrm-burst y rrm-reader, incluido OCR en GPU si se abrió un paper sin LaTeX). Panorama en sim y SAM apagado: esas rutas no llaman a Meta. No se midió un importe."
    ;;
  meta)
    export RRM_OFFLINE_PANORAMA=meta
    export RRM_PANORAMA_MODE=meta
    REMINDER="Pudo gastar dinero: Meta, si el navegador llamó a /panorama (Muse). No hubo deploy. /crops sigue grabado y no llama a SAM. El trap igual ejecutó modal app stop. No se midió un importe."
    ;;
  full)
    export RRM_PANORAMA_MODE=meta
    export RRM_SAM=on
    REMINDER="Pudo gastar dinero: Modal (deploy, contenedores y OCR en GPU) y Meta (panorama Muse y SAM en /crops). No se midió un importe."
    ;;
esac

redact() {
  local text="$1" name value pat
  for name in RRM_DEMO_TOKEN MODEL_API_KEY MODAL_TOKEN_ID MODAL_TOKEN_SECRET S2_API_KEY; do
    value="${!name:-}"
    if [[ -z "$value" ]]; then
      continue
    fi
    pat=""
    local i c
    for ((i = 0; i < ${#value}; i++)); do
      c="${value:i:1}"
      case "$c" in
        '*'|'?'|'['|']'|'\\') pat+="\\$c" ;;
        *) pat+="$c" ;;
      esac
    done
    text="${text//${pat}/[redacted]}"
  done
  printf '%s\n' "$text"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  if [[ "$_cleaned" == 1 ]]; then
    exit "$status"
  fi
  _cleaned=1
  local pid
  for pid in "$WATCH_PID" "$DEPLOY_PID" "$API_PID" "$UI_PID"; do
    if [[ -n "$pid" ]]; then
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  modal app stop rrm-burst || true
  modal app stop rrm-reader || true
  modal app list || true
  local elapsed="$SECONDS"
  echo ""
  echo "Modo: ${MODE}"
  echo "Tiempo: ${elapsed}s"
  if [[ -s "$CAP_FILE" ]]; then
    echo "Corte: RRM_MAX_MINUTES=${MAX_MIN}."
  fi
  echo "$REMINDER"
  rm -f "$CAP_FILE" "$DEPLOY_LOG"
  exit "$status"
}
trap cleanup EXIT INT TERM

(
  sleep $((MAX_MIN * 60))
  echo 1 >"$CAP_FILE"
  kill -TERM $$ 2>/dev/null || true
) >/dev/null 2>&1 &
WATCH_PID=$!

echo "Modo: ${MODE}. Tope: ${MAX_MIN} min. Features: ${RRM_FEATURES}."
echo "Panorama: ${RRM_PANORAMA_MODE}. SAM: ${RRM_SAM:-grabado}."

ensure_fixtures() {
  if [[ -f "$FIX_DIR/manifest.json" ]]; then
    return
  fi
  if [[ -n "${RRM_OFFLINE_DIR:-}" ]]; then
    echo "RRM_OFFLINE_DIR no tiene manifest.json." >&2
    exit 1
  fi
  if ! command -v gh >/dev/null 2>&1; then
    echo "Faltan las consultas grabadas y no está gh. Instala gh y corre gh auth login." >&2
    exit 1
  fi
  local tag=offline-fixtures-v1
  gh release download "$tag" --repo FrankEBaru/research-microscope --pattern "${tag}.tar.gz" --clobber --dir "$ROOT"
  tar -xzf "$ROOT/${tag}.tar.gz" -C "$ROOT"
  rm -f "$ROOT/${tag}.tar.gz"
}

deploy_one() {
  local src="$1" log url status
  log="$(mktemp)"
  DEPLOY_LOG="$log"
  status=0
  modal deploy "$src" >"$log" 2>&1 &
  DEPLOY_PID=$!
  wait "$DEPLOY_PID" || status=$?
  DEPLOY_PID=""
  if [[ "$status" != 0 ]]; then
    echo "Falló modal deploy ${src}." >&2
    redact "$(cat "$log")" >&2
    rm -f "$log"
    DEPLOY_LOG=""
    return "$status"
  fi
  url="$(grep -oE 'https://[^[:space:]]+\.modal\.run' "$log" | tail -n 1 || true)"
  rm -f "$log"
  DEPLOY_LOG=""
  url="${url%/}"
  DEPLOYED_URL="$url"
  if [[ -z "$url" ]]; then
    echo "modal deploy ${src} no imprimió una URL *.modal.run." >&2
    return 1
  fi
}

start_ui() {
  cd "$ROOT/apps/reader"
  if [[ ! -d node_modules ]]; then
    npm ci
  fi
  echo ""
  echo "Ábrelo en el navegador de Windows: http://localhost:3000"
  echo "Ctrl+C apaga la UI y corre modal app stop."
  npm run dev &
  UI_PID=$!
  cd "$ROOT"
  local status=0
  wait "$UI_PID" || status=$?
  UI_PID=""
  exit "$status"
}

if [[ "$MODE" == "modal" || "$MODE" == "full" ]]; then
  if [[ -z "${RRM_DEMO_TOKEN:-}" ]]; then
    echo "Falta RRM_DEMO_TOKEN. En Frank: source ~/projects/hackaton/activate.sh" >&2
    exit 1
  fi
  export NEXT_PUBLIC_RRM_DEMO_TOKEN="$RRM_DEMO_TOKEN"
  unset NEXT_PUBLIC_RRM_OFFLINE
  deploy_one rrm/search/serve.py
  export NEXT_PUBLIC_BURST_URL="$DEPLOYED_URL"
  deploy_one rrm/reader/serve.py
  export NEXT_PUBLIC_READER_URL="$DEPLOYED_URL"
  echo "Ráfaga: ${NEXT_PUBLIC_BURST_URL}"
  echo "Lector: ${NEXT_PUBLIC_READER_URL}"
  start_ui
fi

ensure_fixtures
export NEXT_PUBLIC_BURST_URL="http://127.0.0.1:${PORT}"
export NEXT_PUBLIC_READER_URL="http://127.0.0.1:${PORT}"
export NEXT_PUBLIC_RRM_DEMO_TOKEN="${NEXT_PUBLIC_RRM_DEMO_TOKEN:-local}"
export NEXT_PUBLIC_RRM_OFFLINE=1
python3 -m rrm.offline --root "$FIX_DIR" --host 127.0.0.1 --port "$PORT" &
API_PID=$!
ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/', timeout=1)" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    break
  fi
  sleep 0.2
done
if [[ "$ready" != 1 ]]; then
  echo "El servidor offline no arrancó en el puerto ${PORT}." >&2
  exit 1
fi
echo "API local: http://127.0.0.1:${PORT}"
start_ui
