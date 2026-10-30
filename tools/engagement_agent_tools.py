"""Orchestrate tools for engagement_agent.

Composes and delivers one plain-language in-app question to Dana, then reads
her reply.  This agent has NO access to account state — it cannot place holds,
release funds, or open cases.

The question text must:
  - use only details from Dana's own transaction history
  - never include a link
  - never mention details a scammer could look up (account numbers, card numbers)
  - be plain and calm — no scare tactics

Connection injected by Orchestrate: novamind_mock_bank
  MOCK_BANK_URL      — base URL of the mock bank API
  MOCK_BANK_API_KEY  — value for the X-API-Key header
"""
from __future__ import annotations

import os

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
    if isinstance(msg, Exception):
        return {"ok": False, "error": f"{type(msg).__name__}: {msg}{detail}"}
    return {"ok": False, "error": str(msg)}


# ---------------------------------------------------------------------------
# Tool 1 — send_in_app_question
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def send_in_app_question(
    customer_id: str,
    txn_id: str,
    authorization_id: str,
    merchant_name: str,
    amount: float,
    reason_text: str,
    question_text: str,
) -> dict:
    """Create and send an in-app question for Dana to confirm a suspicious charge.

    The question appears inside Dana's banking app (no SMS, no email, no link).
    The returned page_url is for demo / analyst monitoring only — it is NEVER
    sent to Dana in any message.

    The question_text should be written by the LLM and must:
      - use only details from Dana's own transaction history (e.g. "you usually
        shop at NorthSide Supply on Tuesdays")
      - not include a URL or link
      - not reveal account numbers, card numbers, or any detail a scammer could
        exploit
      - be phrased calmly — no scare tactics

    Args:
        customer_id: The customer to ask, e.g. "C-DANA-001".
        txn_id: The transaction being queried.
        authorization_id: The risk_agent authorization_id for this question.
        merchant_name: Human-readable merchant name shown on the question screen.
        amount: Transaction amount shown on the question screen.
        reason_text: Plain-language reason shown on the question screen explaining
            why this charge looks unusual (written by the LLM).
        question_text: Full question text, e.g. "You usually shop at NorthSide
            Supply on Tuesdays at around $320. Did you make this payment today
            from a new terminal?"

    Returns:
        {"ok": true, "question_id": "Q-...", "page_url": "https://..."}
        on success (page_url is for demo use only), or
        {"ok": false, "error": "..."} on failure.
    """
    payload = {
        "customer_id": customer_id,
        "txn_id": txn_id,
        "authorization_id": authorization_id,
        "question_text": question_text,
        "merchant_name": merchant_name,
        "amount": amount,
        "plain_reason": reason_text,
    }
    try:
        with _client() as c:
            r = c.post("/questions", json=payload)
        r.raise_for_status()
        data = r.json()
        return {
            "ok": True,
            "question_id": data["question_id"],
            "page_url": data.get("page_url"),
        }
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 2 — get_question_status
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def get_question_status(question_id: str) -> dict:
    """Check whether Dana has answered the in-app question yet.

    The risk_agent polls this after sending a question to decide whether to
    proceed with a release, escalate for non-reply (edge rule 2), or wait.

    Status values returned by the mock bank:
      "pending"  — no reply yet
      "answered" — Dana replied; check reply ("me" | "not_me") and verified (bool)
      "expired"  — question timed out without a reply

    Args:
        question_id: The question ID returned by send_in_app_question.

    Returns:
        {
          "ok": true,
          "question_id": "...",
          "status": "pending" | "answered" | "expired",
          "reply": "me" | "not_me" | null,
          "verified": bool,
          "channel": "in_app" | "push" | "external" | null,
          "second_channel_retried": bool
        }
        on success, or {"ok": false, "error": "..."} on failure.
    """
    try:
        with _client() as c:
            r = c.get(f"/questions/{question_id}")
        r.raise_for_status()
        data = r.json()
        return {
            "ok": True,
            "question_id": data["question_id"],
            "status": data["status"],
            "reply": data.get("reply"),
            "verified": data.get("verified", False),
            "channel": data.get("channel"),
            "second_channel_retried": data.get("second_channel_retried", False),
        }
    except Exception as exc:
        return _err(exc)


# ---------------------------------------------------------------------------
# Tool 3 — retry_second_channel
# ---------------------------------------------------------------------------

@tool(expected_credentials=_BANK_CREDS)
def retry_second_channel(question_id: str) -> dict:
    """Trigger a simulated push-notification retry for an unanswered question.

    Edge rule 2: if Dana hasn't replied within 15 minutes, retry on a second
    channel (simulated push notification).  If there is still no reply, the
    hold is kept and an analyst is queued.

    This tool marks the retry in the mock bank so the timeline on the case
    view shows the second-channel attempt.  It does NOT release the hold or
    close the case.

    Args:
        question_id: The question ID that has not yet been answered.

    Returns:
        {"ok": true, "question_id": "...", "second_channel_retried": true}
        on success, or {"ok": false, "error": "..."} on failure.
    """
    try:
        with _client() as c:
            r = c.post(f"/questions/{question_id}/retry")
        r.raise_for_status()
        data = r.json()
        return {
            "ok": True,
            "question_id": data["question_id"],
            "second_channel_retried": data.get("second_channel_retried", True),
        }
    except Exception as exc:
        return _err(exc)
