#!/usr/bin/env bash
# File incoming data from inbox into data/raw/
# Usage: ./scripts/ingest.sh <file> <category>
# Categories: papers | repos | experiments | web

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INBOX="$ROOT/data/inbox"
RAW="$ROOT/data/raw"

usage() {
  echo "Usage: $0 <file> <category>"
  echo "  category: papers | repos | experiments | web"
  echo ""
  echo "Examples:"
  echo "  $0 data/inbox/skillrl.pdf papers"
  echo "  $0 ~/Downloads/export.json experiments"
  exit 1
}

[[ $# -ge 2 ]] || usage

SRC="$1"
CATEGORY="$2"
DATE_PREFIX="$(date +%Y-%m-%d)"

case "$CATEGORY" in
  papers|repos|experiments|web) ;;
  *) echo "Unknown category: $CATEGORY"; usage ;;
esac

if [[ ! -f "$SRC" ]]; then
  echo "Error: file not found: $SRC"
  exit 1
fi

BASENAME="$(basename "$SRC")"
# Prefix date if not already present
if [[ "$BASENAME" == "$DATE_PREFIX"* ]]; then
  DEST_NAME="$BASENAME"
else
  DEST_NAME="${DATE_PREFIX}-${BASENAME}"
fi

DEST_DIR="$RAW/$CATEGORY"
DEST="$DEST_DIR/$DEST_NAME"

mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST"

echo "Ingested:"
echo "  from: $SRC"
echo "  to:   $DEST"
echo ""
echo "Next steps:"
echo "  1. Add row to INDEX.md (Raw data section)"
echo "  2. Create note from templates/data-entry.md if needed"
echo "  3. Process → data/processed/"
