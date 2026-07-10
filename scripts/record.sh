#!/usr/bin/env bash
# Register a new artifact in the research archive.
# Usage: ./scripts/record.sh <relative-path> <evidence-level> [category] [title]
#
# Examples:
#   ./scripts/record.sh notes/synthesis/new-analysis.md L2 synthesis "My analysis"
#   ./scripts/record.sh notes/synthesis/repos/foo.md L3 repo "Foo deep dive"
#
# Does NOT auto-edit manifest.yaml (append manually or use record-append mode).
# Prints INDEX.md row template and manifest snippet.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/store/manifest.yaml"
DATE="$(date +%Y-%m-%d)"

usage() {
  echo "Usage: $0 <relative-path> <L0|L1|L2|L3|L4> [category] [title]"
  exit 1
}

[[ $# -ge 2 ]] || usage

REL_PATH="$1"
LEVEL="$2"
CATEGORY="${3:-synthesis}"
TITLE="${4:-}"

FILE="$ROOT/$REL_PATH"

if [[ ! -f "$FILE" ]]; then
  echo "Error: file not found: $FILE"
  exit 1
fi

case "$LEVEL" in
  L0|L1|L2|L3|L4) ;;
  *) echo "Error: evidence level must be L0–L4"; exit 1 ;;
esac

# Derive title from first H1 if not provided
if [[ -z "$TITLE" ]]; then
  TITLE="$(grep -m1 '^# ' "$FILE" 2>/dev/null | sed 's/^# //' || basename "$FILE" .md)"
fi

# Generate ID from date + slug
SLUG="$(echo "$REL_PATH" | tr '/' '-' | sed 's/\.md$//' | tr '[:upper:]' '[:lower:]')"
ID="N${DATE}-$(echo "$SLUG" | tail -c 20 | tr -cd 'a-z0-9-' | sed 's/^-//')"

echo "═══════════════════════════════════════════════════════════"
echo "  Recorded: $REL_PATH"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Suggested ID: $ID"
echo "Evidence:     $LEVEL"
echo "Category:     $CATEGORY"
echo "Title:        $TITLE"
echo ""
echo "── INDEX.md row (paste into Notes & logs) ──"
echo "| $DATE | $TITLE | [$REL_PATH]($REL_PATH) |"
echo ""
echo "── manifest.yaml snippet ──"
cat <<EOF
  - id: $ID
    path: $REL_PATH
    category: $CATEGORY
    evidence_level: $LEVEL
    title: $TITLE
    date: "$DATE"
EOF
echo ""
echo "── Frontmatter (add to top of file if missing) ──"
cat <<EOF
---
id: $ID
title: $TITLE
date: $DATE
tags: []
status: processed
evidence_level: $LEVEL
summary:
---
EOF
echo ""
echo "Next:"
echo "  1. Append snippet to store/manifest.yaml under appropriate section"
echo "  2. Add row to INDEX.md"
echo "  3. If session work: update store/sessions/YYYY-MM-DD-*.md"
echo "  4. See store/protocols/recording.md"
echo ""

# Touch manifest last_updated if file exists
if [[ -f "$MANIFEST" ]]; then
  if grep -q '^last_updated:' "$MANIFEST"; then
    sed -i '' "s/^last_updated:.*/last_updated: \"$DATE\"/" "$MANIFEST" 2>/dev/null || \
    sed -i "s/^last_updated:.*/last_updated: \"$DATE\"/" "$MANIFEST" 2>/dev/null || true
  fi
fi

# Append to data/processed/record-log.jsonl
LOG="$ROOT/data/processed/record-log.jsonl"
mkdir -p "$(dirname "$LOG")"
echo "{\"date\":\"$DATE\",\"id\":\"$ID\",\"path\":\"$REL_PATH\",\"level\":\"$LEVEL\",\"category\":\"$CATEGORY\",\"title\":\"$TITLE\"}" >> "$LOG"
echo "Appended to data/processed/record-log.jsonl"
