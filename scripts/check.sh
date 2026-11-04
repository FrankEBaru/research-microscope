#!/usr/bin/env bash
# Repo check. Does not call Modal, Semantic Scholar, arXiv, or Meta.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f tests/fixtures/demo/paper_sections.json ]]; then
  tmp="$(mktemp -d)"
  # El tar es sintético: si gh no está o falla, se genera igual.
  if ! command -v gh >/dev/null 2>&1 || ! gh release download artifacts/RRM-16-demo-fixtures-2026-10-29 --pattern demo-fixtures.tar.gz --dir "$tmp" >/dev/null 2>&1; then
    echo "gh no bajó los fixtures: los genero con scripts/build_demo_fixtures.py" >&2
    python3 scripts/build_demo_fixtures.py "$tmp/demo-fixtures.tar.gz" >/dev/null
  fi
  mkdir -p tests/fixtures/demo
  tar -xzf "$tmp/demo-fixtures.tar.gz" -C tests/fixtures/demo
fi
python3 -m pytest -q tests/test_demo_contract.py tests/test_search.py tests/test_reader.py tests/test_bundle_contract.py tests/test_panorama.py tests/test_offline.py tests/test_live_sh.py tests/test_core.py tests/test_layout.py tests/test_phrases.py tests/test_labels.py tests/test_feedback.py tests/test_querylang.py tests/test_groupnames.py tests/test_textcase.py tests/test_gaps.py tests/test_passage_lookup.py tests/test_notes.py tests/test_fetch_offline.py tests/test_promptguard.py tests/test_prompt_eval.py tests/test_explain.py
node --test apps/reader/tests/contract.test.mjs apps/reader/tests/recorded.test.mjs apps/reader/tests/instrument.test.mjs apps/reader/tests/scaling.test.mjs apps/reader/tests/bibtex.test.mjs apps/reader/tests/companion.test.mjs apps/reader/tests/backend_net.test.mjs apps/reader/tests/core.test.mjs apps/reader/tests/layout.test.mjs apps/reader/tests/hover.test.mjs apps/reader/tests/path.test.mjs apps/reader/tests/falta.test.mjs apps/reader/tests/extract.test.mjs apps/reader/tests/explore.test.mjs apps/reader/tests/artifacts.test.mjs apps/reader/tests/artifacts_v2.test.mjs apps/reader/tests/richtext.test.mjs
