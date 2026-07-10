#!/usr/bin/env bash
# Build static HTML site from markdown sources
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/scripts"
npm install --silent 2>/dev/null || npm install
node build_evo_deck.mjs
node build_survey_deck_i18n.mjs
node inject_deck_i18n.mjs
node generate_matrix_zh.mjs
node build_site.mjs
node fix_html_links.mjs
echo "Done. Serve with: python3 scripts/serve.py"
