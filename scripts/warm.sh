#!/usr/bin/env bash
# Keep the burst and reader HTTP containers warm during a demo window.
#
# Deploy first with the flag (it is read when the app is defined, not from the
# Modal secret). Leave it unset after the demo. Do not set min_containers.
#
#   RRM_DEMO_KEEP_WARM=1 modal deploy rrm/search/serve.py
#   RRM_DEMO_KEEP_WARM=1 modal deploy rrm/reader/serve.py
#
# That sets scaledown_window to 1200s (Modal's maximum) on the burst class and
# the reader HTTP app. min_containers stays 0, so the container still scales to
# zero after the window. GPU OCR is not kept warm.
#
# Then, with BURST and READER set to the deploy URLs (do not commit them):
#
#   RRM_DEMO_TOKEN=... BURST=... READER=... bash scripts/warm.sh
#
# Each ping is one /burst (n=10, which also queues prefetch) and one /status.
# Default interval is 4 minutes, inside the 20 minute window. The token is
# read from the environment and is not printed.
set -euo pipefail
: "${RRM_DEMO_TOKEN:?set RRM_DEMO_TOKEN}"
: "${BURST:?set BURST to the rrm-burst URL}"
: "${READER:?set READER to the rrm-reader URL}"
every="${RRM_WARM_INTERVAL:-240}"
while true; do
  curl -fsS -G "${BURST%/}/burst" \
    -H "X-RRM-Demo: ${RRM_DEMO_TOKEN}" \
    --data-urlencode "q=transformers for time series forecasting" \
    --data-urlencode "n=10" \
    -o /dev/null || true
  curl -fsS -G "${READER%/}/status" \
    -H "X-RRM-Demo: ${RRM_DEMO_TOKEN}" \
    --data-urlencode "ids=13756489" \
    -o /dev/null || true
  sleep "${every}"
done
