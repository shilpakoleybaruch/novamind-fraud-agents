"""Orchestrate tools for action_agent.

Places and releases partial holds, and opens / updates cases.  This is the
ONLY agent with account-write access.  Every action requires a valid
authorization_id from risk_agent before it executes.

The release guardrail is enforced server-side in the mock bank (the API
returns 403 unless verified=true + reply="me" + approvals < 3), so a
prompt-level instruction alone is never sufficient.

Connection injected by Orchestrate: novamind_mock_bank
  MOCK_BANK_URL      — base URL of the mock bank API
  MOCK_BANK_API_KEY  — value for the X-API-Key header
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.run import connections

_BANK_APP_ID = "novamind_mock_bank"
_BANK_CREDS = [{"app_id": _BANK_APP_ID, "type": ConnectionType.KEY_VALUE}]


def _bank_creds() -> tuple[str, str]:
    """(url, key) from the Orchestrate connection; env vars for local runs."""
    try:
        c = connections.key_value(_BANK_APP_ID)
        return c["MOCK_BANK_URL"], c["MOCK_BANK_API_KEY"]
    except Exception:
        return os.environ["MOCK_BANK_URL"], os.environ["MOCK_BANK_API_KEY"]

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    url, key = _bank_creds()
    url = url.rstrip("/")
    return httpx.Client(
        base_url=url,
        headers={"X-API-Key": key},
        timeout=15,
    )


def _err(msg) -> dict:
    resp = getattr(msg, "response", None)
    detail = ""
    if resp is not None:
        try:
            detail = f" | {resp.status_code}: {resp.text[:600]}"
        except Exception:
            pass
    if resp is not None and getattr(resp, "status_code", None) == 403 and "essential" in (getattr(resp, "text", "") or "").lower():
        return {"ok": True, "hold_placed": False, "essential_payee": True,
                "note": "ESSENTIAL_PAYEE: the bank never holds this payee, so no hold is needed. This is expected, not a failure."}
    if isinstance(msg, Exception):
        return {"ok": False, "error": f"{type(msg).__name__}: {msg}{detail}"}
    return {"ok": False, "error": str(msg)}


# ---------------------------------------------------------------------------
# Tool 1 — place_partial_hold
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def place_partial_hold(
    customer_id: str,
    txn_id: str,
    authorization_id: str,
    scope: str,
    reason: str,
) -> dict:
    """Place a partial hold on a suspicious transaction.

    A partial hold targets only the flagged transaction (or merchant / CNP
    channel, depending on scope).  Essential payees — supplier transfers and
    rent — are never blocked by the mock bank regardless of scope.

    The mock bank enforces that authorization_id must carry decision="hold" or
    "escalate".  This call will return an error (not raise) if that condition
    is not met.

    Scope values:
      "transaction"       — freeze this single transaction only
      "merchant"          — freeze all pending transactions at this merchant
      "card_not_present"  — freeze CNP channel only; card-present still works

    Args:
        customer_id: The customer whose account is affected.
        txn_id: The transaction being held.
        authorization_id: The risk_agent authorization_id with decision "hold"
            or "escalate".
        scope: One of "transaction" | "merchant" | "card_not_present".
        reason: Plain-language reason for the hold (written by LLM, stored in
            the audit log and shown on the case view).

    Returns:
        {"ok": true, "hold_id": "HOLD-...", "status": "active"} on success, or
        {"ok": false, "error": "..."} on failure or guardrail rejection.
    """
    payload = {
        "customer_id": customer_id,
        "txn_id": txn_id,
        "authorization_id": authorization_id,
        "scope": scope,
        "reason": reason,
    }
    try:
        with _client() as c:
            r = c.post("/holds", json=payload)
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "hold_id": data["hold_id"], "status": data["status"]}
    except httpx.HTTPStatusError as exc:
        # Surface the server's reason text (e.g. guardrail rejection message)
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return _err(f"Hold rejected ({exc.response.status_code}): {detail}")
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 2 — release_hold
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def release_hold(
    hold_id: str,
    authorization_id: str,
    question_id: str,
) -> dict:
    """Release a partial hold after Dana's verified in-app confirmation.

    The mock bank enforces ALL of the following before releasing:
      1. The authorization_id has decision="release" and references this hold's
         transaction.
      2. The linked question has reply="me" AND verified=True (in-app screen).
      3. The customer has fewer than 3 verified approvals in the last 24 hours.

    If any condition fails, the API returns 403 and this tool returns an error
    dict — it never raises.  The reason string in the error comes from the
    server and is safe to surface to the LLM for its next decision.

    Args:
        hold_id: The hold to release.
        authorization_id: A risk_agent authorization_id with decision="release".
        question_id: The in-app question that Dana answered "me" + verified.
            Passed for context only — the mock bank cross-checks it internally.

    Returns:
        {"ok": true, "hold_id": "...", "status": "released"} on success, or
        {"ok": false, "error": "..."} with the guardrail rejection reason.
    """
    payload = {
        "authorization_id": authorization_id,
        "actor": "action_agent",
    }
    try:
        with _client() as c:
            r = c.post(f"/holds/{hold_id}/release", json=payload)
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "hold_id": data["hold_id"], "status": data["status"]}
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return _err(f"Release rejected ({exc.response.status_code}): {detail}")
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 3 — open_case
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def open_case(
    customer_id: str,
    txn_id: str,
    summary: str,
    authorization_id: str,
    hold_id: Optional[str] = None,
) -> dict:
    """Open a fraud case for review and return the live case-view URL.

    Cases are opened for:
      - Moderate branch: Dana replied "not_me"
      - High branch: hold placed, analyst queued
      - Escalation: rapid approvals or unverified reply

    The case_url is the live timeline page (auto-refreshes every 5 s).  It is
    suitable for sharing with the analyst; do not send it to Dana.

    Args:
        customer_id: The affected customer.
        txn_id: The transaction under review.
        summary: One-sentence plain-language description of the situation
            (written by the LLM, shown at the top of the case view).
        authorization_id: The risk_agent authorization_id for this decision.
        hold_id: Optional — the hold_id if a hold has already been placed.

    Returns:
        {"ok": true, "case_id": "CASE-...", "status": "open",
         "case_url": "https://..."} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    payload: dict = {
        "customer_id": customer_id,
        "txn_id": txn_id,
        "authorization_id": authorization_id,
        "summary": summary,
    }
    if hold_id:
        payload["hold_id"] = hold_id
    try:
        with _client() as c:
            r = c.post("/cases", json=payload)
        r.raise_for_status()
        data = r.json()
        return {
            "ok": True,
            "case_id": data["case_id"],
            "status": data["status"],
            "case_url": data.get("case_url"),
        }
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 4 — update_case
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def update_case(
    case_id: str,
    step: str,
    reason: str,
    actor: str,
    next_step: str,
    expected_by: str,
) -> dict:
    """Add a progress update to an open case.

    Called at each meaningful workflow step (hold placed, question sent,
    reply received, analyst queued) to keep the live case-view timeline current.

    Args:
        case_id: The case to update.
        step: Short label for what just happened, e.g. "hold_placed",
            "question_sent", "reply_received", "analyst_queued".
        reason: Plain-language description of this step for the timeline.
        actor: Which agent performed this step, e.g. "action_agent",
            "engagement_agent", "risk_agent".
        next_step: Description of what will happen next.
        expected_by: Human-readable time estimate for the next step, e.g.
            "within 15 minutes" or "within 2 hours".

    Returns:
        {"ok": true, "case_id": "...", "status": "..."} on success, or
        {"ok": false, "error": "..."} on failure.
    """
    summary = f"[{actor}] {step}: {reason}"
    what_next = f"{next_step} ({expected_by})"
    try:
        with _client() as c:
            r = c.patch(
                f"/cases/{case_id}",
                json={"summary": summary, "what_next": what_next},
            )
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "case_id": data["case_id"], "status": data["status"]}
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 5 — queue_analyst
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def queue_analyst(case_id: str, context_summary: str) -> dict:
    """Escalate a case to the analyst queue and update the case status.

    Called when:
      - Risk score ≥ 70 (high branch)
      - Dana did not reply within the timeout window (edge rule 2)
      - Rapid approvals gate triggered (edge rule 3 — approvals_last_24h ≥ 3)
      - Any tool failure or conflicting signals (edge rule 4)

    Updates the case status to "analyst_queued" and sets the what_next field
    to indicate the expected review time (2 hours).

    Args:
        case_id: The case to escalate.
        context_summary: A brief plain-language summary for the analyst — what
            triggered the escalation, what hold is in place, what Dana said
            (if anything).

    Returns:
        {"ok": true, "case_id": "...", "status": "analyst_queued"} on success,
        or {"ok": false, "error": "..."} on failure.
    """
    try:
        with _client() as c:
            # First update the summary with analyst context
            r1 = c.patch(
                f"/cases/{case_id}",
                json={"summary": context_summary},
            )
            r1.raise_for_status()
            # Then queue the analyst
            r2 = c.post(f"/cases/{case_id}/analyst-queue")
        r2.raise_for_status()
        data = r2.json()
        return {"ok": True, "case_id": data["case_id"], "status": data["status"]}
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Combined tools: one call does the whole sequence (fewer LLM steps)
# ---------------------------------------------------------------------------

def _hold_attempt(c, customer_id, txn_id, authorization_id, reason):
    """Try to place a partial hold. Never raises; returns a small dict."""
    try:
        r = c.post("/holds", json={"customer_id": customer_id, "txn_id": txn_id,
                                   "authorization_id": authorization_id,
                                   "scope": "transaction", "reason": reason})
    except Exception as exc:
        return {"hold_placed": False, "hold_error": f"{type(exc).__name__}: {exc}"}
    if r.status_code in (200, 201):
        return {"hold_placed": True, "hold_id": r.json()["hold_id"]}
    if r.status_code == 403 and "essential" in r.text.lower():
        return {"hold_placed": False, "essential_payee": True}
    return {"hold_placed": False, "hold_error": f"{r.status_code}: {r.text[:300]}"}


@tool(expected_credentials=_BANK_CREDS)
def escalate_transaction(
    customer_id: str,
    txn_id: str,
    authorization_id: str,
    summary: str,
) -> dict:
    """Escalate a transaction in ONE call: place a partial hold (when the bank
    allows it), open a case and queue the analyst.

    A refused hold for an essential payee is expected and does not stop the
    case from being opened.

    Args:
        customer_id: The affected customer.
        txn_id: The transaction under review.
        authorization_id: The risk_agent authorization_id of the escalate
            (or hold) decision.
        summary: One plain sentence for the analyst.

    Returns:
        {"ok": true, "action": "escalated", "hold_placed": bool, "hold_id": ...,
         "case_id": "CASE-...", "case_status": "analyst_queued"} or
        {"ok": false, "error": "..."}.
    """
    try:
        with _client() as c:
            out = {"ok": True, "action": "escalated"}
            out.update(_hold_attempt(c, customer_id, txn_id, authorization_id,
                                     "Escalated for analyst review"))
            body = {"customer_id": customer_id, "txn_id": txn_id,
                    "authorization_id": authorization_id, "summary": summary}
            if out.get("hold_id"):
                body["hold_id"] = out["hold_id"]
            r = c.post("/cases", json=body)
            r.raise_for_status()
            case = r.json()
            out["case_id"] = case["case_id"]
            out["case_url"] = case.get("case_url")
            r1 = c.patch(f"/cases/{case['case_id']}",
                         json={"summary": f"[action_agent] escalated: {summary}"})
            r1.raise_for_status()
            r2 = c.post(f"/cases/{case['case_id']}/analyst-queue")
            r2.raise_for_status()
            out["case_status"] = r2.json().get("status")
            return out
    except Exception as exc:
        return _err(exc)


@tool(expected_credentials=_BANK_CREDS)
def release_transaction(
    customer_id: str,
    txn_id: str,
    hold_authorization_id: str,
    release_authorization_id: str,
    question_id: str,
) -> dict:
    """Release a transaction after Dana's verified 'me' reply, in ONE call:
    place a provisional hold, then release it.

    If the payee is essential the bank never holds it, so nothing needs
    releasing and the result is ok true with essential_payee true. The bank
    still enforces the release rules (verified reply, fewer than 3 approvals);
    a refusal comes back as ok false.

    Args:
        customer_id: The affected customer.
        txn_id: The transaction.
        hold_authorization_id: authorization_id of the 'hold' decision.
        release_authorization_id: authorization_id of the 'release' decision.
        question_id: The in-app question Dana answered.

    Returns:
        {"ok": true, "action": "released" | "no_hold_needed", ...} or
        {"ok": false, "action": "...", "error"/"refusal_reason": "..."}.
    """
    try:
        with _client() as c:
            h = _hold_attempt(c, customer_id, txn_id, hold_authorization_id,
                              "Provisional hold pending release")
            if h.get("essential_payee"):
                return {"ok": True, "action": "no_hold_needed",
                        "essential_payee": True, "hold_placed": False,
                        "note": "Essential payee: never held, nothing to release."}
            if not h.get("hold_placed"):
                return {"ok": False, "action": "hold_failed",
                        "error": h.get("hold_error", "hold failed")}
            hold_id = h["hold_id"]
            r = c.post(f"/holds/{hold_id}/release",
                       json={"authorization_id": release_authorization_id,
                             "actor": "action_agent"})
            if r.status_code >= 400:
                return {"ok": False, "action": "release_refused", "hold_id": hold_id,
                        "refusal_reason": f"{r.status_code}: {r.text[:300]}"}
            return {"ok": True, "action": "released", "hold_id": hold_id,
                    "status": r.json().get("status")}
    except Exception as exc:
        return _err(exc)
