#!/usr/bin/env bash
# Un switch para la UI B1.
#   RRM_MODE=offline bash scripts/run.sh    fixtures, cero Modal, cero Meta
#   RRM_MODE=online  bash scripts/run.sh    la misma UI, ráfaga y lector en Modal, notas y Explain con Meta
# RRM_MAX_MINUTES (default 30) apaga rrm-burst y rrm-reader al cumplirse, solo en online.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${RRM_MODE:-offline}"
case "$MODE" in
  offline|off) export RRM_LIVE=off ;;
  online|on) export RRM_LIVE=on ;;
  *)
    echo "RRM_MODE debe ser offline o online." >&2
    exit 2
    ;;
esac
exec bash scripts/live.sh
