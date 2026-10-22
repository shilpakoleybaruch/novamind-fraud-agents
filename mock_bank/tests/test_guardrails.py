"""Guardrail tests for the Novamind mock bank API.

Tests the four server-side security boundaries:
  1. Release without verification is refused.
  2. Release on the 3rd approval within 24h is refused.
  3. An unverified reply (external channel) doesn't count as verified.
  4. Hold without a risk authorization (or wrong decision type) is refused.

Run from repo root:
  uv run --with fastapi --with "uvicorn[standard]" --with sqlalchemy \
         --with python-multipart --with pytest --with httpx \
         pytest mock_bank/tests/test_guardrails.py -v
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime

# Set env vars BEFORE importing the app so FastAPI/SQLAlchemy pick them up.
os.environ["MOCK_BANK_API_KEY"] = "test-secret"
os.environ["ENABLE_TEST_ENDPOINTS"] = "true"

# Point at a named temp file so all connections in the same process share state
# (SQLite in-memory "sqlite://" gives each connection its own DB).
import tempfile
_tmp_db = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from main import app, get_db
from models import (
    Base,
    Baseline,
    Case,
    Customer,
    Hold,
    Question,
    RiskDecision,
    Transaction,
    create_tables,
    get_engine,
)

# ---------------------------------------------------------------------------
# Shared test engine / session
# ---------------------------------------------------------------------------

TEST_ENGINE = get_engine(f"sqlite:///{_tmp_db}")
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

API_KEY = "test-secret"
HEADERS = {"X-API-Key": API_KEY}

CUSTOMER_ID = "C-TEST-001"
BASE_TXN_ID = f"TXN-BASE-{uuid.uuid4().hex[:6]}"


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    """Create tables and seed minimal test data once per module."""
    create_tables(TEST_ENGINE)
    app.dependency_overrides[get_db] = override_get_db

    with TestSession() as s:
        # Customer row
        s.add(Customer(
            customer_id=CUSTOMER_ID,
            name="Test User",
            account_id="ACC-TEST",
            card_id="CARD-TEST",
            essential_payees_json=json.dumps([]),
            contact_json=json.dumps({}),
        ))
        # One base transaction
        s.add(Transaction(
            txn_id=BASE_TXN_ID,
            customer_id=CUSTOMER_ID,
            account_id="ACC-TEST",
            timestamp=datetime.utcnow(),
            amount=250.0,
            currency="USD",
        ))
        s.commit()

    yield

    app.dependency_overrides.clear()
    # Clean up temp DB file
    try:
        os.unlink(_tmp_db)
    except OSError:
        pass


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _add_txn(txn_id: str) -> None:
    """Insert a transaction directly into the test DB."""
    with TestSession() as s:
        existing = s.query(Transaction).filter(Transaction.txn_id == txn_id).first()
        if existing:
            return
        s.add(Transaction(
            txn_id=txn_id,
            customer_id=CUSTOMER_ID,
            account_id="ACC-TEST",
            timestamp=datetime.utcnow(),
            amount=200.0,
            currency="USD",
        ))
        s.commit()


def _make_risk_decision(client, txn_id: str, decision: str) -> str:
    r = client.post("/risk-decisions", headers=HEADERS, json={
        "customer_id": CUSTOMER_ID,
        "txn_id": txn_id,
        "score": 75.0,
        "level": "high",
        "decision": decision,
        "signals": [],
        "reason": "test",
    })
    assert r.status_code == 201, r.text
    return r.json()["authorization_id"]


def _make_hold(client, txn_id: str, auth_id: str) -> str:
    r = client.post("/holds", headers=HEADERS, json={
        "customer_id": CUSTOMER_ID,
        "txn_id": txn_id,
        "authorization_id": auth_id,
        "scope": "transaction",
        "reason": "test hold",
    })
    assert r.status_code == 201, r.text
    return r.json()["hold_id"]


def _make_question(client, txn_id: str, auth_id: str) -> str:
    r = client.post("/questions", headers=HEADERS, json={
        "customer_id": CUSTOMER_ID,
        "txn_id": txn_id,
        "authorization_id": auth_id,
        "question_text": "Did you make this payment?",
        "merchant_name": "Test Merchant",
        "amount": 200.0,
    })
    assert r.status_code == 201, r.text
    return r.json()["question_id"]


def _simulate_reply(client, q_id: str, reply: str, verified: bool, channel: str = "in_app"):
    r = client.post(f"/questions/{q_id}/simulate-reply", headers=HEADERS, json={
        "reply": reply,
        "verified": verified,
        "channel": channel,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# TEST 1 — Release without verification is refused
# ---------------------------------------------------------------------------

class TestReleaseWithoutVerification:
    """Hold release must be rejected when the question reply is not verified."""

    def test_unverified_reply_blocks_release(self, client):
        """simulate-reply with verified=False → release returns 403."""
        txn_id = f"TXN-G1a-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)

        hold_auth = _make_risk_decision(client, txn_id, "hold")
        hold_id = _make_hold(client, txn_id, hold_auth)
        q_id = _make_question(client, txn_id, hold_auth)

        # Simulate unverified reply (channel=push, verified=False)
        data = _simulate_reply(client, q_id, "me", verified=False, channel="push")
        assert data["verified"] is False

        release_auth = _make_risk_decision(client, txn_id, "release")
        r = client.post(f"/holds/{hold_id}/release", headers=HEADERS, json={
            "authorization_id": release_auth,
            "actor": "action_agent",
        })
        assert r.status_code == 403
        assert "not verified" in r.json()["detail"].lower()

    def test_no_question_at_all_blocks_release(self, client):
        """No question at all → release returns 403."""
        txn_id = f"TXN-G1b-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)

        hold_auth = _make_risk_decision(client, txn_id, "hold")
        hold_id = _make_hold(client, txn_id, hold_auth)
        release_auth = _make_risk_decision(client, txn_id, "release")

        r = client.post(f"/holds/{hold_id}/release", headers=HEADERS, json={
            "authorization_id": release_auth,
        })
        assert r.status_code == 403

    def test_verified_inapp_reply_allows_release(self, client):
        """Verified in-app reply + ≤2 prior approvals → release succeeds."""
        txn_id = f"TXN-G1c-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)

        hold_auth = _make_risk_decision(client, txn_id, "hold")
        hold_id = _make_hold(client, txn_id, hold_auth)
        q_id = _make_question(client, txn_id, hold_auth)
        _simulate_reply(client, q_id, "me", verified=True, channel="in_app")

        release_auth = _make_risk_decision(client, txn_id, "release")
        r = client.post(f"/holds/{hold_id}/release", headers=HEADERS, json={
            "authorization_id": release_auth,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "released"


# ---------------------------------------------------------------------------
# TEST 2 — Release on the 3rd approval within 24h is refused
# ---------------------------------------------------------------------------

class TestThirdApprovalEscalates:
    """Edge rule 1: 3 or more verified 'me' approvals in 24h → refuse release."""

    def _do_verified_approval(self, client, label: str):
        """Create a txn, hold, verified 'me' reply — returns question_id."""
        txn_id = f"TXN-PRIOR-{label}-{uuid.uuid4().hex[:4]}"
        _add_txn(txn_id)
        auth = _make_risk_decision(client, txn_id, "ask")
        q_id = _make_question(client, txn_id, auth)
        _simulate_reply(client, q_id, "me", verified=True, channel="in_app")
        return txn_id

    def test_third_approval_blocked(self, client):
        """After 2 prior verified approvals, a 3rd release attempt → 403."""
        # Create 2 verified approvals in this 24h window
        self._do_verified_approval(client, "p1")
        self._do_verified_approval(client, "p2")

        # 3rd transaction: hold + verified reply
        txn_id = f"TXN-G2-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        hold_auth = _make_risk_decision(client, txn_id, "hold")
        hold_id = _make_hold(client, txn_id, hold_auth)
        q_id = _make_question(client, txn_id, hold_auth)
        _simulate_reply(client, q_id, "me", verified=True, channel="in_app")

        release_auth = _make_risk_decision(client, txn_id, "release")
        r = client.post(f"/holds/{hold_id}/release", headers=HEADERS, json={
            "authorization_id": release_auth,
        })
        assert r.status_code == 403
        detail = r.json()["detail"]
        assert "escalation" in detail.lower() or "3" in detail


# ---------------------------------------------------------------------------
# TEST 3 — simulate-reply stores exactly what the runner sends;
#           the in-app form enforces verified=True; other paths stay unverified.
# ---------------------------------------------------------------------------

class TestSimulateReplyExactStorage:
    """POST /questions/{id}/simulate-reply is test-only and must store
    reply and verified EXACTLY as given — no server-side override.

    This lets the scenario runner express:
      S2: reply=me,     verified=true   → hold releases
      S8: reply=me,     verified=false  → hold must NOT release (scam reply)
    """

    def test_s2_shape_stored_exactly(self, client):
        """S2: reply=me, verified=true, channel=in_app → stored as-is."""
        txn_id = f"TXN-S2-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")
        q_id = _make_question(client, txn_id, auth_id)

        data = _simulate_reply(client, q_id, "me", verified=True, channel="in_app")
        assert data["reply"] == "me"
        assert data["verified"] is True
        assert data["channel"] == "in_app"

    def test_s8_shape_stored_exactly(self, client):
        """S8: reply=me, verified=false, channel=external → stored as-is.
        The server must NOT upgrade verified to True just because reply='me'.
        """
        txn_id = f"TXN-S8-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")
        q_id = _make_question(client, txn_id, auth_id)

        data = _simulate_reply(client, q_id, "me", verified=False, channel="external")
        assert data["reply"] == "me"
        assert data["verified"] is False, (
            "simulate-reply must not upgrade verified=False; S8 scam reply must stay unverified"
        )

    def test_simulate_verified_false_push_stored_as_false(self, client):
        """verified=false on channel=push stays false (not overridden either way)."""
        txn_id = f"TXN-G3b-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")
        q_id = _make_question(client, txn_id, auth_id)

        data = _simulate_reply(client, q_id, "not_me", verified=False, channel="push")
        assert data["verified"] is False

    def test_simulate_verified_true_stored_as_true(self, client):
        """verified=true on any channel is stored as-is (runner controls the value)."""
        txn_id = f"TXN-G3c-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")
        q_id = _make_question(client, txn_id, auth_id)

        data = _simulate_reply(client, q_id, "me", verified=True, channel="push")
        assert data["verified"] is True

    def test_s8_unverified_reply_blocks_release(self, client):
        """S8 end-to-end: unverified reply (verified=false) must block hold release."""
        txn_id = f"TXN-S8e-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)

        hold_auth = _make_risk_decision(client, txn_id, "hold")
        hold_id = _make_hold(client, txn_id, hold_auth)
        q_id = _make_question(client, txn_id, hold_auth)

        # S8: scam-style reply — channel is external, verified=False
        data = _simulate_reply(client, q_id, "me", verified=False, channel="external")
        assert data["verified"] is False

        release_auth = _make_risk_decision(client, txn_id, "release")
        r = client.post(f"/holds/{hold_id}/release", headers=HEADERS, json={
            "authorization_id": release_auth,
        })
        assert r.status_code == 403
        assert "not verified" in r.json()["detail"].lower()

    def test_simulate_reply_disabled_when_flag_off(self, client):
        """simulate-reply returns 404 when ENABLE_TEST_ENDPOINTS is not 'true'."""
        txn_id = f"TXN-FLAG-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")
        q_id = _make_question(client, txn_id, auth_id)

        original = os.environ.get("ENABLE_TEST_ENDPOINTS")
        try:
            os.environ["ENABLE_TEST_ENDPOINTS"] = "false"
            r = client.post(f"/questions/{q_id}/simulate-reply", headers=HEADERS, json={
                "reply": "me",
                "verified": True,
                "channel": "in_app",
            })
            assert r.status_code == 404
        finally:
            # Restore so remaining tests still work
            if original is None:
                os.environ.pop("ENABLE_TEST_ENDPOINTS", None)
            else:
                os.environ["ENABLE_TEST_ENDPOINTS"] = original


class TestRealInAppFormAlwaysVerified:
    """POST /app/question/{id} (Dana's browser form) must always set verified=True.
    This is the boundary enforced by the real form handler, not simulate-reply.
    """

    def test_inapp_form_sets_verified_true_for_me(self, client):
        """Submitting 'me' via the HTML form always produces verified=True."""
        txn_id = f"TXN-FORM-a-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")

        # Create the question and get its page token
        r = client.post("/questions", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "question_text": "Did you make this?",
            "merchant_name": "Test Merchant",
            "amount": 99.0,
        })
        assert r.status_code == 201
        q_id = r.json()["question_id"]

        # Fetch the page token directly from the DB
        with TestSession() as s:
            from models import Question as Q
            q_row = s.query(Q).filter(Q.question_id == q_id).first()
            token = q_row.page_token

        # POST to the real form endpoint (no API key needed — token in URL)
        r2 = client.post(
            f"/app/question/{q_id}?t={token}",
            data={"reply": "me"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r2.status_code == 200

        # Verify the DB row was stored with verified=True
        with TestSession() as s:
            from models import Question as Q
            q_row = s.query(Q).filter(Q.question_id == q_id).first()
            assert q_row.reply == "me"
            assert q_row.verified is True
            assert q_row.channel == "in_app"

    def test_inapp_form_sets_verified_true_for_not_me(self, client):
        """Submitting 'not_me' via the HTML form always produces verified=True."""
        txn_id = f"TXN-FORM-b-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")

        r = client.post("/questions", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "question_text": "Did you make this?",
        })
        q_id = r.json()["question_id"]

        with TestSession() as s:
            from models import Question as Q
            q_row = s.query(Q).filter(Q.question_id == q_id).first()
            token = q_row.page_token

        r2 = client.post(
            f"/app/question/{q_id}?t={token}",
            data={"reply": "not_me"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r2.status_code == 200

        with TestSession() as s:
            from models import Question as Q
            q_row = s.query(Q).filter(Q.question_id == q_id).first()
            assert q_row.reply == "not_me"
            assert q_row.verified is True

    def test_inapp_form_rejects_wrong_token(self, client):
        """Token mismatch → 404, no reply stored."""
        txn_id = f"TXN-FORM-c-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")
        r = client.post("/questions", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "question_text": "Did you make this?",
        })
        q_id = r.json()["question_id"]

        r2 = client.post(
            f"/app/question/{q_id}?t=wrongtoken",
            data={"reply": "me"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r2.status_code == 404


# ---------------------------------------------------------------------------
# TEST 4 — Hold without risk authorization is refused
# ---------------------------------------------------------------------------

class TestHoldWithoutAuthorization:
    """POST /holds must reject if no matching risk decision or wrong decision type."""

    def test_hold_with_no_auth_refused(self, client):
        txn_id = f"TXN-G4a-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)

        r = client.post("/holds", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": "AUTH-DOESNOTEXIST",
            "scope": "transaction",
        })
        assert r.status_code == 403
        assert "authorization" in r.json()["detail"].lower()

    def test_hold_with_clear_decision_refused(self, client):
        """Auth exists but decision='clear' → must be rejected."""
        txn_id = f"TXN-G4b-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "clear")

        r = client.post("/holds", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "scope": "transaction",
        })
        assert r.status_code == 403

    def test_hold_with_ask_decision_refused(self, client):
        """Auth exists but decision='ask' → must be rejected."""
        txn_id = f"TXN-G4c-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "ask")

        r = client.post("/holds", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "scope": "transaction",
        })
        assert r.status_code == 403

    def test_hold_with_valid_hold_decision_succeeds(self, client):
        txn_id = f"TXN-G4d-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "hold")

        r = client.post("/holds", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "scope": "transaction",
        })
        assert r.status_code == 201
        assert "hold_id" in r.json()

    def test_hold_with_escalate_decision_succeeds(self, client):
        txn_id = f"TXN-G4e-{uuid.uuid4().hex[:6]}"
        _add_txn(txn_id)
        auth_id = _make_risk_decision(client, txn_id, "escalate")

        r = client.post("/holds", headers=HEADERS, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "scope": "transaction",
        })
        assert r.status_code == 201

    def test_invalid_api_key_rejected(self, client):
        r = client.post("/holds", headers={"X-API-Key": "wrong"}, json={
            "customer_id": CUSTOMER_ID,
            "txn_id": BASE_TXN_ID,
            "authorization_id": "AUTH-X",
            "scope": "transaction",
        })
        assert r.status_code == 403

    def test_missing_api_key_rejected(self, client):
        """Without the header FastAPI returns 422 (missing required header field)."""
        r = client.post("/holds", json={
            "customer_id": CUSTOMER_ID,
            "txn_id": BASE_TXN_ID,
            "authorization_id": "AUTH-X",
            "scope": "transaction",
        })
        assert r.status_code == 422
