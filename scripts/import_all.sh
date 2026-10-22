#!/usr/bin/env bash
# import_all.sh — imports all Novamind assets into the active Orchestrate env
#
# Run from the repo root:
#   ./scripts/import_all.sh
#
# Ordering is mandatory:
#   1. Connection      — tools need it to resolve the app-id
#   2. Tool files      — agents reference tools by name; tools must exist first
#   3. Knowledge base  — agents reference it by name; skip if already imported
#   4. Leaf agents     — baseline_agent, engagement_agent, action_agent
#   5. Supervisor      — risk_agent lists collaborators; they must exist first
set -euo pipefail

ORCHESTRATE=orchestrate
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Active env"
$ORCHESTRATE env list

# ---------------------------------------------------------------------------
# 1. Connection
# ---------------------------------------------------------------------------
echo ""
echo "==> 1/5  Connection"
$ORCHESTRATE connections import --file "$ROOT/connections/mock_bank.yaml"

# ---------------------------------------------------------------------------
# 2. Tools (one file per agent)
# ---------------------------------------------------------------------------
echo ""
echo "==> 2/5  Tools (one file per agent)"
for tool_file in \
  baseline_agent_tools.py \
  risk_agent_tools.py \
  engagement_agent_tools.py \
  action_agent_tools.py; do
  echo "    importing $tool_file"
  $ORCHESTRATE tools import \
    --kind python \
    --file "$ROOT/tools/$tool_file" \
    --package-root "$ROOT/tools/" \
    --requirements-file "$ROOT/tools/requirements.txt" \
    --app-id novamind_mock_bank
done

# ---------------------------------------------------------------------------
# 3. Knowledge base — skip if already present
# ---------------------------------------------------------------------------
echo ""
echo "==> 3/5  Knowledge base"
if $ORCHESTRATE knowledge-bases list 2>/dev/null | grep -q "novamind_kb"; then
  echo "    novamind_kb already exists — skipping import"
else
  echo "    importing novamind_kb"
  $ORCHESTRATE knowledge-bases import --file "$ROOT/knowledge/novamind_kb.yaml"
fi

# ---------------------------------------------------------------------------
# 4. Leaf agents (order within this group does not matter)
# ---------------------------------------------------------------------------
echo ""
echo "==> 4/5  Leaf agents"
for agent_yaml in \
  baseline_agent.yaml \
  engagement_agent.yaml \
  action_agent.yaml; do
  echo "    importing $agent_yaml"
  $ORCHESTRATE agents import --file "$ROOT/agents/$agent_yaml"
done

# ---------------------------------------------------------------------------
# 5. Supervisor — must be last; collaborators must already exist
# ---------------------------------------------------------------------------
echo ""
echo "==> 5/5  Supervisor agent"
echo "    importing risk_agent.yaml"
$ORCHESTRATE agents import --file "$ROOT/agents/risk_agent.yaml"

echo ""
echo "Done. All Novamind assets imported."
