"""Orchestrate tools for risk_agent (SUPERVISOR).

Scores the deviation from the customer's baseline, retrieves RAG context
(scam patterns + bank policy), and decides the response branch:
clear | ask | hold | escalate.

Scoring and threshold logic runs in plain Python (score_risk) so it is fast,
deterministic, and testable without an LLM.  The LLM's job is to choose the
branch from the returned level and to write the plain-language reason text.

Connection injected by Orchestrate: novamind_mock_bank
  MOCK_BANK_URL      — base URL of the mock bank API
  MOCK_BANK_API_KEY  — value for the X-API-Key header
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

from scoring import score_risk as _score_risk_impl  # single source of truth

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    url = os.environ["MOCK_BANK_URL"].rstrip("/")
    key = os.environ["MOCK_BANK_API_KEY"]
    return httpx.Client(
        base_url=url,
        headers={"X-API-Key": key},
        timeout=15,
    )


def _err(msg: str) -> dict:
    return {"ok": False, "error": str(msg)}


# ---------------------------------------------------------------------------
# Tool 1 — get_score_context
# ---------------------------------------------------------------------------

@tool
def get_score_context(transaction: dict) -> dict:
    """Fetch scoring context for a candidate transaction from the mock bank.

    Returns the transaction record (creating it if new), the number of
    verified "me" approvals in the last 24 hours, and the customer's list
    of essential payees (supplier payments and rent that must never be blocked).

    The risk_agent calls this first, before score_risk, to check the
    rapid-approval edge case and to guard essential payees.

    Args:
        transaction: A transaction dict with at minimum txn_id and customer_id.
            All other fields (merchant_name, amount, channel, etc.) are passed
            through so the mock bank can persist the record.

    Returns:
        {"ok": true, "transaction": {...}, "approvals_last_24h": int,
         "essential_payees": [...]} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    try:
        with _client() as c:
            r = c.post("/transactions/score-context", json=transaction)
        r.raise_for_status()
        return {"ok": True, **r.json()}
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 2 — score_risk  (deterministic Python, delegated to scoring.py)
# ---------------------------------------------------------------------------

@tool
def score_risk(
    signals: list,
    thin_baseline: bool,
    approvals_last_24h: int,
) -> dict:
    """Compute a deterministic 0–100 risk score from the deviation signals.

    Delegates to scoring.score_risk — the single source of truth for weights,
    thresholds, and level logic.  See scoring.py for full documentation.

    Thresholds (normal baseline):
      score < 30   → level "low"      → branch "clear"
      30 ≤ score < 70 → level "moderate" → branch "ask"
      score ≥ 70   → level "high"     → branch "hold"

    Thin-baseline adjustment (edge rule 3 — fewer than 30 txns or < 60 days):
      The lower ask threshold drops from 30 to 20.

    Rapid-approval override (edge rule 1):
      If approvals_last_24h ≥ 3, must_escalate is set to true regardless of score.

    Args:
        signals: List of signal dicts {"name": str, "weight": int} from
            compare_to_baseline.
        thin_baseline: True if < 30 transactions or < 60 days of history.
        approvals_last_24h: Verified "me" approvals in the last 24 hours.

    Returns:
        {"ok": true, "score": int, "level": "low"|"moderate"|"high",
         "low_threshold": int, "high_threshold": 70,
         "must_escalate": bool, "escalate_on_approval": bool,
         "signals_used": [...]}

    escalate_on_approval is True when approvals_last_24h + 1 >= 3, meaning a
    verified "me" reply on this transaction would trip the rapid-approval gate.
    Use this flag to record decision "escalate" instead of "release" when
    the customer answers "me" and escalate_on_approval is True.
    The server-side 403 on release_hold is the hard backstop regardless.
    """
    return _score_risk_impl(signals, thin_baseline, approvals_last_24h)


# ---------------------------------------------------------------------------
# Tool 3 — record_risk_decision
# ---------------------------------------------------------------------------

@tool
def record_risk_decision(
    customer_id: str,
    txn_id: str,
    score: float,
    level: str,
    signals: list,
    decision: str,
    reason: str,
    question_id: Optional[str] = None,
    hold_id: Optional[str] = None,
) -> dict:
    """Write a risk decision record to the mock bank and obtain an authorization_id.

    This records the risk_agent's decision — score, level, chosen branch, and
    reason text — for the audit trail.  It does NOT place a hold or open a
    case; those are action_agent's responsibilities.

    The returned authorization_id must be passed to action_agent when placing
    a hold or requesting a release, acting as the proof that risk_agent
    authorised the action.

    Allowed values for decision: clear | ask | hold | release | escalate.

    Args:
        customer_id: The customer the decision concerns.
        txn_id: The transaction being assessed.
        score: The numeric risk score (0–100).
        level: "low" | "moderate" | "high".
        signals: List of signal dicts from compare_to_baseline / score_risk.
        decision: The chosen branch: clear | ask | hold | release | escalate.
        reason: Plain-language explanation (written by the LLM) for the audit log.
        question_id: Optional — the in-app question ID if one was created.
        hold_id: Optional — the hold ID if one was already placed.

    Returns:
        {"ok": true, "authorization_id": "AUTH-..."} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    payload: dict = {
        "customer_id": customer_id,
        "txn_id": txn_id,
        "score": score,
        "level": level,
        "decision": decision,
        "signals": signals,
        "reason": reason,
        "actor": "risk_agent",
    }
    try:
        with _client() as c:
            r = c.post("/risk-decisions", json=payload)
        r.raise_for_status()
        auth_id = r.json()["authorization_id"]
        return {"ok": True, "authorization_id": auth_id}
    except Exception as exc:
        return _err(exc)
