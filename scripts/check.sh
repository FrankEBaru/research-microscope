#!/usr/bin/env bash
# Repo check. Does not call Modal, Semantic Scholar, arXiv, or Meta.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f tests/fixtures/demo/paper_sections.json ]]; then
  tmp="$(mktemp -d)"
  if ! gh release download artifacts/RRM-16-demo-fixtures-2026-10-29 --pattern demo-fixtures.tar.gz --dir "$tmp"; then
    echo "gh release download failed" >&2
    exit 1
  fi
  mkdir -p tests/fixtures/demo
  tar -xzf "$tmp/demo-fixtures.tar.gz" -C tests/fixtures/demo
fi
python3 -m pytest -q tests/test_demo_contract.py tests/test_search.py tests/test_reader.py
node --test apps/reader/tests/contract.test.mjs apps/reader/tests/instrument.test.mjs apps/reader/tests/scaling.test.mjs apps/reader/tests/bibtex.test.mjs apps/reader/tests/companion.test.mjs
