"""Orchestrate tools for baseline_agent.

Builds Dana's normal spending pattern from transaction history and answers
"is this consistent with who this customer is?"

This agent is READ-ONLY with one exception: compute_baseline writes the
computed summary back via PUT /baseline, and learn_merchant adds a newly
confirmed merchant. No account-state changes (holds, cases) happen here.

Signal weights and scoring live in scoring.py — the single source of truth.

Connection injected by Orchestrate: novamind_mock_bank
  MOCK_BANK_URL      — base URL of the mock bank API
  MOCK_BANK_API_KEY  — value for the X-API-Key header
"""
from __future__ import annotations

import os
import statistics
from collections import defaultdict
from datetime import datetime

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

from scoring import SIGNAL_WEIGHTS  # single source of truth for signal weights

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
# Tool 1 — get_transaction_history
# ---------------------------------------------------------------------------

@tool
def get_transaction_history(customer_id: str, days: int = 180) -> dict:
    """Fetch the customer's recent transaction history from the mock bank.

    Returns up to `days` days of transactions for the given customer, newest
    first.  The baseline_agent calls this before computing or comparing
    against the customer's spending pattern.

    Args:
        customer_id: The customer identifier, e.g. "C-DANA-001".
        days: How many calendar days of history to retrieve (default 180).

    Returns:
        {"ok": true, "transactions": [...]} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    try:
        with _client() as c:
            r = c.get(f"/customers/{customer_id}/transactions", params={"days": days})
        r.raise_for_status()
        return {"ok": True, "transactions": r.json()}
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 2 — compute_baseline  (deterministic Python)
# ---------------------------------------------------------------------------

@tool
def compute_baseline(customer_id: str) -> dict:
    """Build and save a statistical spending baseline for the customer.

    Fetches up to 180 days of history, then computes — in plain Python, with
    no LLM involvement:
      - known_merchants: set of merchant_ids seen
      - known_terminals: map merchant_id → set of terminal_ids
      - weekday_per_merchant: typical weekday(s) each merchant is visited
      - hour_range_per_merchant: [min_hour, max_hour] per merchant
      - amount_stats_per_merchant: {median, p90} per merchant_id
      - amount_stats_per_mcc: {median, p90} per MCC category
      - weekly_volume: median weekly spend in USD
      - history_days: span of the data in days
      - transaction_count: total number of transactions
      - thin_baseline: true if < 30 transactions OR < 60 days of history

    The result is written back to the mock bank via PUT /customers/{id}/baseline
    and also returned here so the risk_agent can use it directly.

    Args:
        customer_id: The customer identifier, e.g. "C-DANA-001".

    Returns:
        {"ok": true, "baseline": {...}} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    # --- fetch history ---
    hist = get_transaction_history(customer_id, days=180)
    if not hist.get("ok"):
        return hist
    txns = hist["transactions"]
    if not txns:
        return _err("No transactions found — cannot build baseline.")

    # --- parse timestamps ---
    def _dt(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    parsed: list[dict] = []
    for t in txns:
        try:
            t["_dt"] = _dt(t["timestamp"])
            parsed.append(t)
        except Exception:
            pass

    if not parsed:
        return _err("Could not parse any transaction timestamps.")

    parsed.sort(key=lambda t: t["_dt"])
    first_dt = parsed[0]["_dt"]
    last_dt = parsed[-1]["_dt"]
    history_days = max(1, (last_dt - first_dt).days)
    n = len(parsed)
    thin_baseline = n < 30 or history_days < 60

    # --- per-merchant / per-mcc accumulators ---
    amounts_by_merchant: dict[str, list[float]] = defaultdict(list)
    amounts_by_mcc: dict[str, list[float]] = defaultdict(list)
    weekdays_by_merchant: dict[str, list[int]] = defaultdict(list)   # 0=Mon
    hours_by_merchant: dict[str, list[int]] = defaultdict(list)
    terminals_by_merchant: dict[str, set] = defaultdict(set)
    known_merchants: set[str] = set()
    weekly_amounts: dict[str, float] = defaultdict(float)  # ISO week → total

    for t in parsed:
        mid = t.get("merchant_id") or ""
        mcc = t.get("mcc") or ""
        amt = float(t.get("amount") or 0)
        tid = t.get("terminal_id") or ""
        dt = t["_dt"]
        week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"

        if mid:
            known_merchants.add(mid)
            amounts_by_merchant[mid].append(amt)
            weekdays_by_merchant[mid].append(dt.weekday())
            hours_by_merchant[mid].append(dt.hour)
            if tid:
                terminals_by_merchant[mid].add(tid)
        if mcc:
            amounts_by_mcc[mcc].append(amt)
        weekly_amounts[week_key] += amt

    def _stats(vals: list[float]) -> dict:
        if not vals:
            return {"median": 0.0, "p90": 0.0, "count": 0}
        s = sorted(vals)
        med = statistics.median(s)
        idx = max(0, int(len(s) * 0.9) - 1)
        return {"median": round(med, 2), "p90": round(s[idx], 2), "count": len(s)}

    def _mode_weekday(days: list[int]) -> list[int]:
        """Return the most common weekday(s) — ties included."""
        if not days:
            return []
        counts = defaultdict(int)
        for d in days:
            counts[d] += 1
        max_c = max(counts.values())
        return sorted(k for k, v in counts.items() if v == max_c)

    amount_stats_per_merchant = {mid: _stats(v) for mid, v in amounts_by_merchant.items()}
    amount_stats_per_mcc = {mcc: _stats(v) for mcc, v in amounts_by_mcc.items()}
    weekday_per_merchant = {mid: _mode_weekday(v) for mid, v in weekdays_by_merchant.items()}
    hour_range_per_merchant = {
        mid: {"min": min(v), "max": max(v)}
        for mid, v in hours_by_merchant.items() if v
    }
    known_terminals = {mid: sorted(ts) for mid, ts in terminals_by_merchant.items()}

    weekly_vals = list(weekly_amounts.values())
    weekly_volume = round(statistics.median(weekly_vals), 2) if weekly_vals else 0.0

    baseline_data = {
        "known_merchants": sorted(known_merchants),
        "known_terminals": known_terminals,
        "weekday_per_merchant": weekday_per_merchant,
        "hour_range_per_merchant": hour_range_per_merchant,
        "amount_stats_per_merchant": amount_stats_per_merchant,
        "amount_stats_per_mcc": amount_stats_per_mcc,
        "weekly_volume": weekly_volume,
        "history_days": history_days,
        "transaction_count": n,
        "thin_baseline": thin_baseline,
    }

    # --- save back to mock bank ---
    try:
        with _client() as c:
            r = c.put(
                f"/customers/{customer_id}/baseline",
                json={
                    "data": baseline_data,
                    "history_days": history_days,
                    "transaction_count": n,
                },
            )
        r.raise_for_status()
    except Exception as exc:
        return _err(f"Could not save baseline: {exc}")

    return {"ok": True, "baseline": baseline_data}


# ---------------------------------------------------------------------------
# Tool 3 — compare_to_baseline  (deterministic Python)
# ---------------------------------------------------------------------------

@tool
def compare_to_baseline(customer_id: str, transaction: dict) -> dict:
    """Compare a candidate transaction against the customer's saved baseline.

    Runs entirely in Python — no LLM involved.  Returns a list of named
    deviation signals, each with its weight, so the risk_agent can feed
    them straight into score_risk.

    Signals checked (name, weight) — weights are the canonical values from scoring.py:
      new_terminal_known_merchant (30)  — known merchant, unseen terminal
      new_merchant_known_category (20)  — unseen merchant, but known MCC
      new_merchant (30)                 — unseen merchant AND unseen MCC
      amount_above_p90 (20)             — amount > p90 for this merchant or MCC
      unusual_hour (20)                 — outside the observed hour range for merchant
      card_not_present_overseas (50)    — channel=card_not_present AND country != "US"
      velocity_spike (45)               — amount > 3× the customer's weekly median
      thin_baseline (5)                 — fewer than 30 txns or under 60 days

    Args:
        customer_id: The customer identifier, e.g. "C-DANA-001".
        transaction: A transaction dict with keys: merchant_id, terminal_id,
            mcc, amount, channel, country, timestamp (ISO-8601).

    Returns:
        {"ok": true, "signals": [{"name": ..., "weight": ...}, ...],
         "thin_baseline": bool} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    # --- fetch stored baseline ---
    try:
        with _client() as c:
            r = c.get(f"/customers/{customer_id}/baseline")
        r.raise_for_status()
        bl = r.json().get("data", {})
    except Exception as exc:
        return _err(f"Could not fetch baseline: {exc}")

    signals: list[dict] = []

    def add(name: str) -> None:
        signals.append({"name": name, "weight": SIGNAL_WEIGHTS[name]})

    mid = transaction.get("merchant_id") or ""
    tid = transaction.get("terminal_id") or ""
    mcc = transaction.get("mcc") or ""
    amount = float(transaction.get("amount") or 0)
    channel = transaction.get("channel") or ""
    country = transaction.get("country") or ""
    thin = bl.get("thin_baseline", True)

    known_merchants: list[str] = bl.get("known_merchants", [])
    known_terminals: dict[str, list[str]] = bl.get("known_terminals", {})
    amount_by_merchant: dict[str, dict] = bl.get("amount_stats_per_merchant", {})
    amount_by_mcc: dict[str, dict] = bl.get("amount_stats_per_mcc", {})
    hour_range: dict[str, dict] = bl.get("hour_range_per_merchant", {})
    weekly_volume: float = float(bl.get("weekly_volume") or 0)

    # --- merchant / terminal signals ---
    merchant_known = mid in known_merchants
    terminal_known = tid and tid in known_terminals.get(mid, [])

    if merchant_known and tid and not terminal_known:
        add("new_terminal_known_merchant")
    elif not merchant_known:
        if mcc in (bl.get("amount_stats_per_mcc") or {}):
            add("new_merchant_known_category")
        else:
            add("new_merchant")

    # --- amount signal ---
    stats = amount_by_merchant.get(mid) or amount_by_mcc.get(mcc)
    if stats and stats.get("p90", 0) > 0 and amount > stats["p90"]:
        add("amount_above_p90")

    # --- hour signal ---
    try:
        hour = datetime.fromisoformat(
            transaction.get("timestamp", "").replace("Z", "+00:00")
        ).hour
        hr = hour_range.get(mid)
        if hr and not (hr["min"] <= hour <= hr["max"]):
            add("unusual_hour")
    except Exception:
        pass

    # --- overseas CNP ---
    if channel == "card_not_present" and country not in ("US", ""):
        add("card_not_present_overseas")

    # --- velocity spike: amount > 3× weekly median ---
    if weekly_volume > 0 and amount > 3 * weekly_volume:
        add("velocity_spike")

    # --- thin baseline flag ---
    if thin:
        add("thin_baseline")

    return {"ok": True, "signals": signals, "thin_baseline": thin}


# ---------------------------------------------------------------------------
# Tool 4 — learn_merchant
# ---------------------------------------------------------------------------

@tool
def learn_merchant(
    customer_id: str,
    merchant_id: str,
    terminal_id: str,
    question_id: str,
) -> dict:
    """Add a merchant / terminal to the customer's baseline after a confirmed "me" reply.

    Only runs if the linked in-app question has reply="me" AND verified=True.
    This enforces in code that we never silently expand the baseline on an
    unverified or "not_me" answer.

    Fetches the current baseline, adds the merchant and terminal to the known
    sets, and saves the updated baseline back.

    Args:
        customer_id: The customer identifier.
        merchant_id: The merchant to add to the known-merchant set.
        terminal_id: The terminal to add under that merchant.
        question_id: The in-app question that Dana answered "me" + verified.

    Returns:
        {"ok": true, "learned": true} on success,
        {"ok": false, "error": "..."} if the question is not verified/me, or
        on any API failure.
    """
    # --- check question is verified "me" ---
    try:
        with _client() as c:
            qr = c.get(f"/questions/{question_id}")
        qr.raise_for_status()
        q = qr.json()
    except Exception as exc:
        return _err(f"Could not fetch question {question_id}: {exc}")

    if q.get("reply") != "me":
        return _err(
            f"Question {question_id} reply is '{q.get('reply')}', not 'me' — "
            "will not update baseline."
        )
    if not q.get("verified"):
        return _err(
            f"Question {question_id} is not verified — "
            "will not update baseline."
        )

    # --- fetch current baseline ---
    try:
        with _client() as c:
            br = c.get(f"/customers/{customer_id}/baseline")
        br.raise_for_status()
        bl_resp = br.json()
        bl = bl_resp.get("data", {})
    except Exception as exc:
        return _err(f"Could not fetch baseline: {exc}")

    # --- update in-memory ---
    known = set(bl.get("known_merchants", []))
    known.add(merchant_id)
    bl["known_merchants"] = sorted(known)

    terminals: dict[str, list] = bl.get("known_terminals", {})
    t_set = set(terminals.get(merchant_id, []))
    if terminal_id:
        t_set.add(terminal_id)
    terminals[merchant_id] = sorted(t_set)
    bl["known_terminals"] = terminals

    # --- save back ---
    try:
        with _client() as c:
            pr = c.put(
                f"/customers/{customer_id}/baseline",
                json={
                    "data": bl,
                    "history_days": bl_resp.get("history_days"),
                    "transaction_count": bl_resp.get("transaction_count"),
                },
            )
        pr.raise_for_status()
    except Exception as exc:
        return _err(f"Could not save updated baseline: {exc}")

    return {"ok": True, "learned": True, "merchant_id": merchant_id, "terminal_id": terminal_id}
