#!/usr/bin/env bash
# sync_knowledge.sh — regenerate the .txt copies used by the Orchestrate knowledge base
#
# Background
# ----------
# The ADK knowledge-base importer rejects text/markdown files, so the three
# policy/pattern documents are stored as both .md (for editing) and .txt (for
# ingestion).  This script copies the .md originals to their .txt counterparts
# so the two sets stay in sync.
#
# Run this any time you edit a .md file in knowledge/ and before running
#   orchestrate knowledge-bases import --file knowledge/novamind_kb.yaml
#
# Usage (from repo root):
#   ./scripts/sync_knowledge.sh
set -euo pipefail

KB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/knowledge"

PAIRS=(
  "bank_alert_and_hold_policy"
  "scam_patterns"
  "customer_messaging_guidelines"
)

echo "Syncing knowledge .md → .txt in ${KB_DIR}"
for base in "${PAIRS[@]}"; do
  src="${KB_DIR}/${base}.md"
  dst="${KB_DIR}/${base}.txt"
  if [ ! -f "$src" ]; then
    echo "  ERROR: source not found: $src" >&2
    exit 1
  fi
  cp "$src" "$dst"
  echo "  copied ${base}.md → ${base}.txt"
done

echo "Done. Run 'orchestrate knowledge-bases import --file knowledge/novamind_kb.yaml' to re-ingest."
