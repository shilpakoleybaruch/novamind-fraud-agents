"""Shared scoring logic for Novamind — single source of truth.

Both baseline_agent_tools and risk_agent_tools import from here.
Tests import from here directly.

Signal weights rationale
------------------------
new_terminal_known_merchant  30  Medium: same trusted merchant, but the device
                                 has never been seen on this account. That alone
                                 is enough to ask — it doesn't need a second
                                 signal to reach the 30-point ask threshold.

new_merchant_known_category  20  Lower medium: the MCC (category) has been seen
                                 before, so the type of spend is familiar. Alone
                                 it sits below the ask threshold; a second signal
                                 tips it over.

new_merchant                 30  Medium: completely unseen merchant AND category.
                                 One completely unknown merchant is at least as
                                 suspicious as a new terminal — ask immediately.

amount_above_p90             20  Additive: amplifies other signals.

unusual_hour                 20  Additive: amplifies other signals.  A legitimate
                                 transaction at an unusual hour (e.g. coffee shop
                                 at 14:30 when Dana always goes at 07:00–09:00)
                                 is fine on its own (score stays below threshold);
                                 combined with a new merchant/terminal it tips the
                                 score higher.

card_not_present_overseas    50  High: CNP + foreign country in combination is the
                                 single strongest fraud indicator.  Unknown merchant
                                 (30) + this (50) = 80 → always high.

velocity_spike               45  High: amount > 3× the weekly median.

thin_baseline                 5  Informational only.  Its real effect is to lower
                                 the ask threshold from 30 → 20 (edge rule 3).
                                 The weight itself adds minor score to borderline
                                 transactions.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Signal weight table
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS: dict[str, int] = {
    "new_terminal_known_merchant": 30,   # medium — new device on a trusted merchant;
                                         # alone reaches the 30-pt ask threshold
    "new_merchant_known_category": 20,   # lower medium — familiar category, new merchant
    "new_merchant":                30,   # medium — fully unseen merchant + category
    "amount_above_p90":            20,   # additive
    "unusual_hour":                20,   # additive
    "card_not_present_overseas":   50,   # high — overseas CNP alone is near-threshold
    "velocity_spike":              45,   # high
    "thin_baseline":                5,   # informational; mainly adjusts threshold
}

# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

LOW_THRESHOLD_NORMAL: int = 30   # score < 30 → clear
LOW_THRESHOLD_THIN: int   = 20   # score < 20 → clear (edge rule 3: thin baseline)
HIGH_THRESHOLD: int       = 70   # score ≥ 70 → hold/escalate (never ask)


# ---------------------------------------------------------------------------
# score_risk — deterministic, no LLM
# ---------------------------------------------------------------------------

def score_risk(
    signals: list[dict],
    thin_baseline: bool,
    approvals_last_24h: int,
) -> dict:
    """Compute a deterministic 0–100 risk score from deviation signals.

    This function is the single authoritative scorer.  It is called by the
    score_risk @tool in risk_agent_tools (which wraps it for Orchestrate) and
    directly by tests.

    Thresholds (normal baseline):
      score < 30   → level "low"      → branch "clear"
      30 ≤ score < 70 → level "moderate" → branch "ask"
      score ≥ 70   → level "high"     → branch "hold"

    Thin-baseline adjustment (edge rule 3):
      Lower ask threshold drops from 30 → 20 when the customer has < 30
      transactions OR < 60 days of history.

    Rapid-approval override (edge rule 1):
      If approvals_last_24h ≥ 3, must_escalate is set to True.  The level and
      score are returned unchanged; the caller must escalate instead of releasing.

      escalate_on_approval is set to True when approvals_last_24h + 1 ≥ 3
      (i.e. ≥ 2 prior approvals already exist).  This signals that if the
      current question is answered "me" and verified, recording a release
      would trip the rapid-approval gate at the server — the risk_agent must
      record "escalate" instead.  The server-side 403 remains the hard backstop
      even if this flag is ignored.

    Args:
        signals: List of {"name": str, "weight": int} dicts from
                 compare_to_baseline.  Unknown names are looked up in
                 SIGNAL_WEIGHTS; if still unknown they are skipped.
        thin_baseline: True when the baseline is thin (from compare_to_baseline).
        approvals_last_24h: Count of verified "me" approvals in the last 24 h
                            (from get_score_context), NOT including the current
                            transaction.

    Returns:
        {
          "ok": True,
          "score": int (0–100),
          "level": "low" | "moderate" | "high",
          "low_threshold": int,         # 20 (thin) or 30 (normal)
          "high_threshold": int,        # always 70
          "must_escalate": bool,        # True when approvals_last_24h >= 3
          "escalate_on_approval": bool, # True when approvals_last_24h + 1 >= 3
                                        # (a "me" reply on this txn would trip
                                        # the rapid-approval gate)
          "signals_used": [{"name": str, "weight": int}, ...],
        }
    """
    raw = 0
    signals_used: list[dict] = []
    for sig in signals:
        name   = sig.get("name", "")
        weight = sig.get("weight") or SIGNAL_WEIGHTS.get(name, 0)
        if weight:
            raw += weight
            signals_used.append({"name": name, "weight": weight})

    score       = min(100, raw)
    low_thresh  = LOW_THRESHOLD_THIN if thin_baseline else LOW_THRESHOLD_NORMAL

    if score < low_thresh:
        level = "low"
    elif score < HIGH_THRESHOLD:
        level = "moderate"
    else:
        level = "high"

    return {
        "ok":                   True,
        "score":                score,
        "level":                level,
        "low_threshold":        low_thresh,
        "high_threshold":       HIGH_THRESHOLD,
        "must_escalate":        approvals_last_24h >= 3,
        "escalate_on_approval": approvals_last_24h + 1 >= 3,
        "signals_used":         signals_used,
    }
