#!/usr/bin/env bash
# Verificación de la UI en un comando: tipos, pruebas, build y capturas.
# Sin Modal ni Meta. Sale con el primer fallo. --skip-py omite pytest (falta una dependencia Python).
#   RRM_OFFLINE_DIR=<dir>   usa esos datos en las capturas; si no, sintéticos.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
READER="$ROOT/apps/reader"
SKIP_PY=0
SKIPPED=()
for arg in "$@"; do
  case "$arg" in
    --skip-py) SKIP_PY=1; SKIPPED+=("pytest (--skip-py)") ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

for bin in node npm npx python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Falta $bin." >&2
    exit 1
  fi
done
if [[ ! -d "$READER/node_modules" ]]; then
  (cd "$READER" && npm ci)
fi

step() { echo ""; echo "== $1"; }

step "1/7 tsc --noEmit"
(cd "$READER" && npx tsc --noEmit)

step "2/7 npm run verify"
if [[ -d "$READER/public/papers" ]]; then
  npm --prefix "$READER" run verify
else
  # check_math.mjs lee public/papers (datos curados locales, fuera de git). Sin ellos, solo las pruebas de verify.
  echo "Falta apps/reader/public/papers: omito check_math.mjs y corro el resto de verify." >&2
  SKIPPED+=("check_math.mjs (falta apps/reader/public/papers)")
  (cd "$READER" && node -e 'for (const part of require("./package.json").scripts.verify.split("&&")) if (part.trim().startsWith("node --test")) console.log(part.trim())' | while IFS= read -r cmd; do bash -c "$cmd" || exit 1; done)
fi

step "3/7 node --test (sin e2e, live ni click)"
TESTS=()
for f in "$READER"/tests/*.test.mjs; do
  case "$(basename "$f")" in
    e2e.test.mjs|live.test.mjs|click.test.mjs) ;;
    *) TESTS+=("$f") ;;
  esac
done
node --test "${TESTS[@]}"

step "4/7 pytest"
if [[ "$SKIP_PY" == 1 ]]; then
  echo "omitido (--skip-py)"
elif ! python3 -c "import pytest, numpy" >/dev/null 2>&1; then
  echo "Falta una dependencia Python (pytest o numpy): pip install -r requirements-dev.txt. Sigo con --skip-py." >&2
  SKIP_PY=1
  SKIPPED+=("pytest (falta una dependencia Python)")
else
  python3 -m pytest -q tests/test_offline.py tests/test_ui_fixtures.py tests/test_core.py
fi

step "5/7 npm run build"
npm --prefix "$READER" run build

step "6/7 build:live + live.test.mjs + build"
npm --prefix "$READER" run build:live
if [[ -d "$READER/public/papers" ]]; then
  node --test "$READER/tests/live.test.mjs"
else
  # live.test.mjs abre papers de public/papers (datos curados locales, fuera de git).
  echo "Falta apps/reader/public/papers: omito live.test.mjs." >&2
  SKIPPED+=("live.test.mjs (falta apps/reader/public/papers)")
fi
npm --prefix "$READER" run build

step "7/7 capturas"
node "$READER/tests/shots.mjs"

echo ""
echo "Capturas: $READER/shots"
echo "Informe:  $READER/shots/report.json"
if [[ "${#SKIPPED[@]}" -gt 0 ]]; then
  echo "OMITIDO: ${SKIPPED[*]}. Esto no es una verificación completa." >&2
fi
echo "verify-ui: ok"
