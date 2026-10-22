#!/usr/bin/env bash
# remove_all.sh — removes all Novamind assets from the active Orchestrate env
#
# Run from the repo root:
#   ./scripts/remove_all.sh
#
# Ordering is the reverse of import:
#   1. Supervisor agent first (it references collaborators)
#   2. Leaf agents
#   3. Tools (14 individual tools, one per @tool function)
#   4. Knowledge base
#   5. Connection last
#
# Each command uses || true so a missing asset doesn't abort the whole run.
set -euo pipefail

ORCHESTRATE=orchestrate

# ---------------------------------------------------------------------------
# 1. Supervisor agent
# ---------------------------------------------------------------------------
echo "==> 1/5  Supervisor agent"
$ORCHESTRATE agents remove --name risk_agent --kind native || true

# ---------------------------------------------------------------------------
# 2. Leaf agents
# ---------------------------------------------------------------------------
echo ""
echo "==> 2/5  Leaf agents"
$ORCHESTRATE agents remove --name action_agent     --kind native || true
$ORCHESTRATE agents remove --name engagement_agent --kind native || true
$ORCHESTRATE agents remove --name baseline_agent   --kind native || true

# ---------------------------------------------------------------------------
# 3. Tools  (remove by individual @tool function name, not by file name)
# ---------------------------------------------------------------------------
echo ""
echo "==> 3/5  Tools"

# baseline_agent_tools.py
$ORCHESTRATE tools remove --name get_transaction_history  || true
$ORCHESTRATE tools remove --name compute_baseline         || true
$ORCHESTRATE tools remove --name compare_to_baseline      || true
$ORCHESTRATE tools remove --name learn_merchant           || true

# risk_agent_tools.py
$ORCHESTRATE tools remove --name get_score_context        || true
$ORCHESTRATE tools remove --name score_risk               || true
$ORCHESTRATE tools remove --name record_risk_decision     || true

# engagement_agent_tools.py
$ORCHESTRATE tools remove --name send_in_app_question     || true
$ORCHESTRATE tools remove --name get_question_status      || true
$ORCHESTRATE tools remove --name retry_second_channel     || true

# action_agent_tools.py
$ORCHESTRATE tools remove --name place_partial_hold       || true
$ORCHESTRATE tools remove --name release_hold             || true
$ORCHESTRATE tools remove --name open_case                || true
$ORCHESTRATE tools remove --name update_case              || true
$ORCHESTRATE tools remove --name queue_analyst            || true

# ---------------------------------------------------------------------------
# 4. Knowledge base
# ---------------------------------------------------------------------------
echo ""
echo "==> 4/5  Knowledge base"
$ORCHESTRATE knowledge-bases remove --name novamind_kb || true

# ---------------------------------------------------------------------------
# 5. Connection
# ---------------------------------------------------------------------------
echo ""
echo "==> 5/5  Connection"
$ORCHESTRATE connections remove --app-id novamind_mock_bank || true

echo ""
echo "Done. All Novamind assets removed."
