"""Mock Bank API — FastAPI + SQLite

Simulates core banking: transaction state, holds, cases, in-app messaging.
Also serves the Dana question page and the live case view (HTML).

Auth: every endpoint requires header  X-API-Key: <MOCK_BANK_API_KEY>
EXCEPT the two HTML pages, which use a per-question / per-case token in the URL.
"""
from __future__ import annotations

import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from models import (
    AuditLog,
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
from seed import seed_if_empty

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./mock_bank.db")
engine = get_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

MOCK_BANK_API_KEY = os.environ.get("MOCK_BANK_API_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables(engine)
    with SessionLocal() as session:
        seed_if_empty(session)
    yield


app = FastAPI(title="Novamind Mock Bank API", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_api_key(x_api_key: str = Header(...)):
    if not MOCK_BANK_API_KEY:
        raise HTTPException(500, "MOCK_BANK_API_KEY not configured on server")
    if x_api_key != MOCK_BANK_API_KEY:
        raise HTTPException(403, "Invalid API key")


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def audit(
    db: Session,
    actor: str,
    action: str,
    inputs: dict,
    result: str,
    reason: str | None = None,
    case_id: str | None = None,
    txn_id: str | None = None,
):
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        actor=actor,
        action=action,
        inputs_json=json.dumps(inputs),
        result=result,
        reason=reason,
        case_id=case_id,
        txn_id=txn_id,
    )
    db.add(entry)
    db.commit()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class BaselineIn(BaseModel):
    data: dict = Field(default_factory=dict)
    history_days: Optional[int] = None
    transaction_count: Optional[int] = None


class ScoreContextIn(BaseModel):
    txn_id: str
    customer_id: str
    account_id: Optional[str] = None
    card_id: Optional[str] = None
    timestamp: Optional[str] = None
    merchant_name: Optional[str] = None
    merchant_id: Optional[str] = None
    terminal_id: Optional[str] = None
    mcc: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = "USD"
    channel: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None


class RiskDecisionIn(BaseModel):
    authorization_id: Optional[str] = None   # caller may supply or we generate
    customer_id: str
    txn_id: str
    score: float
    level: str  # low | moderate | high
    decision: str  # clear | ask | hold | release | escalate
    signals: list = Field(default_factory=list)
    branch: Optional[str] = None
    reason: Optional[str] = None
    actor: str = "risk_agent"


class QuestionIn(BaseModel):
    customer_id: str
    txn_id: str
    authorization_id: str
    question_text: str
    merchant_name: Optional[str] = None
    amount: Optional[float] = None
    plain_reason: Optional[str] = None


class SimulateReplyIn(BaseModel):
    reply: str          # me | not_me
    verified: bool
    channel: str = "in_app"


class HoldIn(BaseModel):
    customer_id: str
    txn_id: str
    authorization_id: str
    scope: str          # transaction | merchant | card_not_present
    reason: Optional[str] = None


class ReleaseIn(BaseModel):
    authorization_id: str
    actor: str = "action_agent"


class CaseIn(BaseModel):
    customer_id: str
    txn_id: Optional[str] = None
    authorization_id: Optional[str] = None
    hold_id: Optional[str] = None
    summary: Optional[str] = None
    what_next: Optional[str] = None


class CasePatch(BaseModel):
    status: Optional[str] = None
    summary: Optional[str] = None
    what_next: Optional[str] = None


# ---------------------------------------------------------------------------
# Customers / Transactions
# ---------------------------------------------------------------------------

@app.get("/customers/{customer_id}/transactions", dependencies=[Depends(require_api_key)])
def get_transactions(
    customer_id: str,
    days: int = Query(default=90, ge=1),
    db: Session = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    txns = (
        db.query(Transaction)
        .filter(Transaction.customer_id == customer_id, Transaction.timestamp >= cutoff)
        .order_by(Transaction.timestamp.desc())
        .all()
    )
    return [_txn_dict(t) for t in txns]


def _txn_dict(t: Transaction) -> dict:
    return {
        "txn_id": t.txn_id,
        "customer_id": t.customer_id,
        "account_id": t.account_id,
        "card_id": t.card_id,
        "timestamp": t.timestamp.isoformat() + "Z",
        "merchant_name": t.merchant_name,
        "merchant_id": t.merchant_id,
        "terminal_id": t.terminal_id,
        "mcc": t.mcc,
        "amount": t.amount,
        "currency": t.currency,
        "channel": t.channel,
        "city": t.city,
        "country": t.country,
        "risk_score": t.risk_score,
    }


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

@app.get("/customers/{customer_id}/baseline", dependencies=[Depends(require_api_key)])
def get_baseline(customer_id: str, db: Session = Depends(get_db)):
    bl = db.query(Baseline).filter(Baseline.customer_id == customer_id).first()
    if not bl:
        raise HTTPException(404, "Baseline not found")
    return {
        "customer_id": bl.customer_id,
        "data": bl.data,
        "history_days": bl.history_days,
        "transaction_count": bl.transaction_count,
        "updated_at": bl.updated_at.isoformat() + "Z" if bl.updated_at else None,
    }


@app.put("/customers/{customer_id}/baseline", dependencies=[Depends(require_api_key)])
def put_baseline(customer_id: str, body: BaselineIn, db: Session = Depends(get_db)):
    bl = db.query(Baseline).filter(Baseline.customer_id == customer_id).first()
    if bl:
        bl.data_json = json.dumps(body.data)
        if body.history_days is not None:
            bl.history_days = body.history_days
        if body.transaction_count is not None:
            bl.transaction_count = body.transaction_count
        bl.updated_at = datetime.utcnow()
    else:
        bl = Baseline(
            customer_id=customer_id,
            data_json=json.dumps(body.data),
            history_days=body.history_days,
            transaction_count=body.transaction_count,
            updated_at=datetime.utcnow(),
        )
        db.add(bl)
    db.commit()
    audit(db, "baseline_agent", "baseline_updated",
          {"customer_id": customer_id}, "ok")
    return {"customer_id": customer_id, "updated": True}


# ---------------------------------------------------------------------------
# Score context
# ---------------------------------------------------------------------------

@app.post("/transactions/score-context", dependencies=[Depends(require_api_key)])
def score_context(body: ScoreContextIn, db: Session = Depends(get_db)):
    """Return the transaction plus approval count in last 24h and essential payees."""
    # Upsert the candidate transaction so it's in the DB for later references
    txn = db.query(Transaction).filter(Transaction.txn_id == body.txn_id).first()
    if not txn:
        ts = (
            datetime.fromisoformat(body.timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
            if body.timestamp
            else datetime.utcnow()
        )
        txn = Transaction(
            txn_id=body.txn_id,
            customer_id=body.customer_id,
            account_id=body.account_id or "",
            card_id=body.card_id,
            timestamp=ts,
            merchant_name=body.merchant_name,
            merchant_id=body.merchant_id,
            terminal_id=body.terminal_id,
            mcc=body.mcc,
            amount=body.amount or 0.0,
            currency=body.currency or "USD",
            channel=body.channel,
            city=body.city,
            country=body.country,
        )
        db.add(txn)
        db.commit()

    # Count verified "me" approvals in last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    approvals_24h = (
        db.query(Question)
        .filter(
            Question.customer_id == body.customer_id,
            Question.reply == "me",
            Question.verified == True,
            Question.answered_at >= since,
        )
        .count()
    )

    # Essential payees
    customer = db.query(Customer).filter(Customer.customer_id == body.customer_id).first()
    essential_payees = customer.essential_payees if customer else []

    return {
        "transaction": _txn_dict(txn),
        "approvals_last_24h": approvals_24h,
        "essential_payees": essential_payees,
    }


# ---------------------------------------------------------------------------
# Risk Decisions
# ---------------------------------------------------------------------------

VALID_DECISIONS = {"clear", "ask", "hold", "release", "escalate"}


@app.post("/risk-decisions", dependencies=[Depends(require_api_key)], status_code=201)
def create_risk_decision(body: RiskDecisionIn, db: Session = Depends(get_db)):
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(422, f"decision must be one of {VALID_DECISIONS}")

    auth_id = body.authorization_id or f"AUTH-{uuid.uuid4().hex[:12].upper()}"

    # Ensure transaction exists
    txn = db.query(Transaction).filter(Transaction.txn_id == body.txn_id).first()
    if not txn:
        raise HTTPException(404, f"Transaction {body.txn_id} not found")

    rd = RiskDecision(
        authorization_id=auth_id,
        customer_id=body.customer_id,
        txn_id=body.txn_id,
        score=body.score,
        level=body.level,
        decision=body.decision,
        signals_json=json.dumps(body.signals),
        branch=body.branch,
        reason=body.reason,
        actor=body.actor,
        created_at=datetime.utcnow(),
    )
    db.add(rd)
    db.commit()

    audit(db, body.actor, "risk_decision_created",
          {"txn_id": body.txn_id, "score": body.score, "decision": body.decision},
          "created", reason=body.reason, txn_id=body.txn_id)

    return {"authorization_id": auth_id}


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

@app.post("/questions", dependencies=[Depends(require_api_key)], status_code=201)
def create_question(body: QuestionIn, db: Session = Depends(get_db)):
    # Validate authorization exists
    rd = db.query(RiskDecision).filter(
        RiskDecision.authorization_id == body.authorization_id
    ).first()
    if not rd:
        raise HTTPException(404, "authorization_id not found")

    qid = f"Q-{uuid.uuid4().hex[:10].upper()}"
    token = secrets.token_urlsafe(24)

    q = Question(
        question_id=qid,
        customer_id=body.customer_id,
        txn_id=body.txn_id,
        authorization_id=body.authorization_id,
        question_text=body.question_text,
        merchant_name=body.merchant_name,
        amount=body.amount,
        plain_reason=body.plain_reason,
        status="pending",
        page_token=token,
        created_at=datetime.utcnow(),
    )
    db.add(q)
    db.commit()

    audit(db, "engagement_agent", "question_created",
          {"question_id": qid, "txn_id": body.txn_id}, "created",
          txn_id=body.txn_id)

    # Build the demo link (never sent to Dana in an actual message)
    base_url = os.environ.get("BASE_URL", "http://localhost:8000")
    page_url = f"{base_url}/app/question/{qid}?t={token}"

    return {"question_id": qid, "page_url": page_url}


@app.get("/questions/{question_id}", dependencies=[Depends(require_api_key)])
def get_question(question_id: str, db: Session = Depends(get_db)):
    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    return _question_dict(q)


def _question_dict(q: Question) -> dict:
    return {
        "question_id": q.question_id,
        "customer_id": q.customer_id,
        "txn_id": q.txn_id,
        "authorization_id": q.authorization_id,
        "question_text": q.question_text,
        "merchant_name": q.merchant_name,
        "amount": q.amount,
        "plain_reason": q.plain_reason,
        "status": q.status,
        "reply": q.reply,
        "verified": q.verified,
        "channel": q.channel,
        "second_channel_retried": q.second_channel_retried,
        "created_at": q.created_at.isoformat() + "Z",
        "answered_at": q.answered_at.isoformat() + "Z" if q.answered_at else None,
    }


@app.post("/questions/{question_id}/retry", dependencies=[Depends(require_api_key)])
def retry_question(question_id: str, db: Session = Depends(get_db)):
    """Mark second-channel retry (simulated push notification)."""
    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    if q.status != "pending":
        raise HTTPException(409, f"Question status is '{q.status}', retry not applicable")
    q.second_channel_retried = True
    db.commit()
    audit(db, "engagement_agent", "question_retry_push",
          {"question_id": question_id}, "retried", txn_id=q.txn_id)
    return {"question_id": question_id, "second_channel_retried": True}


@app.post("/questions/{question_id}/simulate-reply", dependencies=[Depends(require_api_key)])
def simulate_reply(question_id: str, body: SimulateReplyIn, db: Session = Depends(get_db)):
    """Test-only endpoint used by the scenario runner.

    Only active when ENABLE_TEST_ENDPOINTS=true.  Returns 404 otherwise so
    this surface is never reachable in a real deployment.

    Stores reply and verified EXACTLY as supplied — no override.
    This lets the runner drive S2 (reply=me, verified=true) and S8
    (reply=me, verified=false) without the server second-guessing it.

    The channel-based verification rule is enforced on the real in-app
    form (POST /app/question/{id}) and on any future real-reply path.
    It does NOT apply here.
    """
    if os.environ.get("ENABLE_TEST_ENDPOINTS", "").lower() != "true":
        raise HTTPException(404, "Not found")

    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    if body.reply not in {"me", "not_me"}:
        raise HTTPException(422, "reply must be 'me' or 'not_me'")

    # Store exactly what the test runner specifies — no modification.
    q.reply = body.reply
    q.verified = body.verified
    q.channel = body.channel
    q.status = "answered"
    q.answered_at = datetime.utcnow()
    db.commit()

    audit(db, "scenario_runner", "simulate_reply",
          {"question_id": question_id, "reply": body.reply,
           "verified": body.verified, "channel": body.channel},
          "answered", txn_id=q.txn_id)

    return _question_dict(q)


# ---------------------------------------------------------------------------
# Holds  (GUARDRAIL-CRITICAL)
# ---------------------------------------------------------------------------

@app.post("/holds", dependencies=[Depends(require_api_key)], status_code=201)
def create_hold(body: HoldIn, db: Session = Depends(get_db)):
    """GUARDRAIL: requires a risk decision with decision='hold' or 'escalate'."""
    rd = db.query(RiskDecision).filter(
        RiskDecision.authorization_id == body.authorization_id
    ).first()

    if not rd:
        _reject_hold(db, body, "no_authorization", "No risk authorization found")

    if rd.decision not in {"hold", "escalate"}:
        _reject_hold(
            db, body,
            "wrong_decision_type",
            f"Authorization decision is '{rd.decision}'; must be 'hold' or 'escalate'",
        )

    # Ensure transaction exists
    txn = db.query(Transaction).filter(Transaction.txn_id == body.txn_id).first()
    if not txn:
        raise HTTPException(404, f"Transaction {body.txn_id} not found")

    # Check essential payees — partial hold must never block them
    customer = db.query(Customer).filter(Customer.customer_id == body.customer_id).first()
    if customer:
        for ep in customer.essential_payees:
            if txn.merchant_id and ep.get("payee_id") and \
               (txn.merchant_name or "").lower() == ep.get("name", "").lower():
                raise HTTPException(
                    403,
                    f"Cannot place hold on essential payee '{ep['name']}'"
                )

    hold_id = f"HOLD-{uuid.uuid4().hex[:10].upper()}"
    hold = Hold(
        hold_id=hold_id,
        customer_id=body.customer_id,
        txn_id=body.txn_id,
        authorization_id=body.authorization_id,
        scope=body.scope,
        status="active",
        reason=body.reason,
        created_at=datetime.utcnow(),
    )
    db.add(hold)
    db.commit()

    audit(db, "action_agent", "hold_placed",
          {"hold_id": hold_id, "txn_id": body.txn_id, "scope": body.scope},
          "placed", reason=body.reason, txn_id=body.txn_id)

    return {"hold_id": hold_id, "status": "active"}


def _reject_hold(db: Session, body: HoldIn, result: str, reason: str):
    audit(db, "action_agent", "hold_rejected",
          {"txn_id": body.txn_id, "authorization_id": body.authorization_id},
          result, reason=reason, txn_id=body.txn_id)
    raise HTTPException(403, reason)


@app.post("/holds/{hold_id}/release", dependencies=[Depends(require_api_key)])
def release_hold(hold_id: str, body: ReleaseIn, db: Session = Depends(get_db)):
    """GUARDRAIL: ALL three conditions must be true to release a hold.

    1. The authorization_id decision is "release" and references this hold's txn.
    2. The linked question has reply="me" AND verified=True.
    3. The customer has fewer than 3 verified approvals in the last 24h.
    """
    hold = db.query(Hold).filter(Hold.hold_id == hold_id).first()
    if not hold:
        raise HTTPException(404, "Hold not found")
    if hold.status == "released":
        return {"hold_id": hold_id, "status": "already_released"}

    # --- Condition 1: authorization must exist, be "release", reference same txn ---
    rd = db.query(RiskDecision).filter(
        RiskDecision.authorization_id == body.authorization_id
    ).first()

    def reject(reason: str, code: int = 403):
        audit(db, body.actor, "release_rejected",
              {"hold_id": hold_id, "authorization_id": body.authorization_id},
              "rejected", reason=reason, txn_id=hold.txn_id)
        raise HTTPException(code, detail=reason)

    if not rd:
        reject("No matching authorization found")
    if rd.decision != "release":
        reject(f"Authorization decision is '{rd.decision}', not 'release'")
    if rd.txn_id != hold.txn_id:
        reject("Authorization references a different transaction")

    # --- Condition 2: linked question verified ---
    question = (
        db.query(Question)
        .filter(
            Question.txn_id == hold.txn_id,
            Question.customer_id == hold.customer_id,
        )
        .order_by(Question.created_at.desc())
        .first()
    )

    if not question:
        reject("No in-app question found for this transaction")
    if question.reply != "me":
        reject(f"Question reply is '{question.reply}', not 'me'")
    if not question.verified:
        reject("Question reply is not verified (must come via the in-app screen)")

    # --- Condition 3: fewer than 3 approvals in last 24h ---
    since = datetime.utcnow() - timedelta(hours=24)
    approvals_24h = (
        db.query(Question)
        .filter(
            Question.customer_id == hold.customer_id,
            Question.reply == "me",
            Question.verified == True,
            Question.answered_at >= since,
        )
        .count()
    )
    if approvals_24h >= 3:
        reject(
            f"Customer has {approvals_24h} verified approvals in the last 24h "
            "(≥3 triggers escalation, not release)"
        )

    # All conditions met — release
    hold.status = "released"
    hold.released_at = datetime.utcnow()
    hold.released_by = body.actor
    db.commit()

    audit(db, body.actor, "hold_released",
          {"hold_id": hold_id, "authorization_id": body.authorization_id},
          "released", txn_id=hold.txn_id)

    return {"hold_id": hold_id, "status": "released"}


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

@app.post("/cases", dependencies=[Depends(require_api_key)], status_code=201)
def create_case(body: CaseIn, db: Session = Depends(get_db)):
    case_id = f"CASE-{uuid.uuid4().hex[:10].upper()}"
    case_token = secrets.token_urlsafe(24)

    case = Case(
        case_id=case_id,
        customer_id=body.customer_id,
        txn_id=body.txn_id,
        authorization_id=body.authorization_id,
        hold_id=body.hold_id,
        status="open",
        summary=body.summary,
        what_next=body.what_next,
        case_token=case_token,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(case)
    db.commit()

    audit(db, "action_agent", "case_created",
          {"case_id": case_id, "txn_id": body.txn_id},
          "created", txn_id=body.txn_id, case_id=case_id)

    base_url = os.environ.get("BASE_URL", "http://localhost:8000")
    return {
        "case_id": case_id,
        "status": "open",
        "case_url": f"{base_url}/app/case/{case_id}?t={case_token}",
    }


@app.patch("/cases/{case_id}", dependencies=[Depends(require_api_key)])
def patch_case(case_id: str, body: CasePatch, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    if body.status:
        case.status = body.status
    if body.summary:
        case.summary = body.summary
    if body.what_next:
        case.what_next = body.what_next
    case.updated_at = datetime.utcnow()
    db.commit()

    audit(db, "action_agent", "case_updated",
          {"case_id": case_id, "updates": body.model_dump(exclude_none=True)},
          "updated", case_id=case_id)

    return {"case_id": case_id, "status": case.status}


@app.get("/cases/{case_id}", dependencies=[Depends(require_api_key)])
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    return _case_dict(case)


def _case_dict(c: Case) -> dict:
    return {
        "case_id": c.case_id,
        "customer_id": c.customer_id,
        "txn_id": c.txn_id,
        "authorization_id": c.authorization_id,
        "hold_id": c.hold_id,
        "status": c.status,
        "summary": c.summary,
        "what_next": c.what_next,
        "analyst_queued_at": c.analyst_queued_at.isoformat() + "Z" if c.analyst_queued_at else None,
        "resolved_at": c.resolved_at.isoformat() + "Z" if c.resolved_at else None,
        "created_at": c.created_at.isoformat() + "Z",
        "updated_at": c.updated_at.isoformat() + "Z",
    }


@app.post("/cases/{case_id}/analyst-queue", dependencies=[Depends(require_api_key)])
def analyst_queue(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    case.status = "analyst_queued"
    case.analyst_queued_at = datetime.utcnow()
    case.what_next = "A fraud analyst will review this within 2 hours."
    case.updated_at = datetime.utcnow()
    db.commit()

    audit(db, "action_agent", "analyst_queued",
          {"case_id": case_id}, "queued", case_id=case_id)

    return {"case_id": case_id, "status": "analyst_queued"}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@app.get("/audit", dependencies=[Depends(require_api_key)])
def get_audit(
    case_id: Optional[str] = Query(default=None),
    txn_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if case_id:
        q = q.filter(AuditLog.case_id == case_id)
    if txn_id:
        q = q.filter(AuditLog.txn_id == txn_id)
    entries = q.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "log_id": e.log_id,
            "timestamp": e.timestamp.isoformat() + "Z",
            "actor": e.actor,
            "action": e.action,
            "inputs": e.inputs,
            "result": e.result,
            "reason": e.reason,
            "case_id": e.case_id,
            "txn_id": e.txn_id,
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Admin / test helpers  (ENABLE_TEST_ENDPOINTS guard)
# ---------------------------------------------------------------------------

@app.post("/admin/reset/{customer_id}", dependencies=[Depends(require_api_key)])
def admin_reset(customer_id: str, db: Session = Depends(get_db)):
    """Delete all mutable state for a customer and reset their baseline stub.

    Only available when ENABLE_TEST_ENDPOINTS=true.  Returns 404 otherwise.

    Removed per reset:
      - AuditLog rows for the customer (by txn_id cross-reference)
      - Question, Hold, Case rows linked to the customer
      - RiskDecision rows linked to the customer
      - Baseline data (reset to empty dict, preserving the row)

    Preserved:
      - Customer row
      - Transaction history rows (history stays; holds/decisions are wiped)
    """
    if os.environ.get("ENABLE_TEST_ENDPOINTS", "").lower() != "true":
        raise HTTPException(404, "Not found")

    # Collect all txn_ids for this customer (for audit log cleanup)
    txn_ids = [
        row.txn_id
        for row in db.query(Transaction.txn_id)
        .filter(Transaction.customer_id == customer_id)
        .all()
    ]

    # Delete audit log entries tied to this customer's transactions or cases
    if txn_ids:
        db.query(AuditLog).filter(AuditLog.txn_id.in_(txn_ids)).delete(
            synchronize_session=False
        )
    # Also sweep case-linked audit rows (case_id references)
    case_ids = [
        row.case_id
        for row in db.query(Case.case_id)
        .filter(Case.customer_id == customer_id)
        .all()
    ]
    if case_ids:
        db.query(AuditLog).filter(AuditLog.case_id.in_(case_ids)).delete(
            synchronize_session=False
        )

    # Delete holds, cases, questions, risk decisions for this customer
    db.query(Hold).filter(Hold.customer_id == customer_id).delete(
        synchronize_session=False
    )
    db.query(Case).filter(Case.customer_id == customer_id).delete(
        synchronize_session=False
    )
    db.query(Question).filter(Question.customer_id == customer_id).delete(
        synchronize_session=False
    )
    db.query(RiskDecision).filter(
        RiskDecision.customer_id == customer_id
    ).delete(synchronize_session=False)

    # Reset baseline to empty stub (preserve row; tools will recompute)
    bl = db.query(Baseline).filter(Baseline.customer_id == customer_id).first()
    if bl:
        bl.data_json = "{}"
        bl.updated_at = datetime.utcnow()

    # Scenario transactions (S-TXN*) must not leak into recomputed baselines
    db.query(Transaction).filter(
        Transaction.customer_id == customer_id,
        Transaction.txn_id.like("S-TXN%"),
    ).delete(synchronize_session=False)

    db.commit()
    return {"ok": True, "customer_id": customer_id, "reset": True}


# ---------------------------------------------------------------------------
# HTML Pages  (NO API key — token in URL)
# ---------------------------------------------------------------------------

def _load_template(name: str) -> str:
    from pathlib import Path
    p = Path(__file__).parent / "templates" / name
    return p.read_text()


@app.get("/app/question/{question_id}", response_class=HTMLResponse)
def question_page(question_id: str, t: str = Query(...), db: Session = Depends(get_db)):
    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q or q.page_token != t:
        return HTMLResponse("<h1>Not found or link expired.</h1>", status_code=404)

    # Check if answered — show outcome
    if q.status == "answered":
        if q.reply == "me":
            outcome = "Resolved. Your card is unblocked. This merchant is saved as a known supplier. Your supplier payments and rent transfer are unaffected."
        else:
            outcome = "Thank you. We've placed a partial hold on this charge only. Your supplier payments and rent transfer are unaffected. A case has been opened for review."
        return HTMLResponse(_render_outcome(q, outcome))

    template = _load_template("dana_question.html")
    return HTMLResponse(_render_question(template, q))


@app.post("/app/question/{question_id}", response_class=HTMLResponse)
async def question_page_submit(
    question_id: str,
    request: Request,
    t: str = Query(...),
    db: Session = Depends(get_db),
):
    """Handle Dana tapping a button on the question page (in-app verified reply)."""
    q = db.query(Question).filter(Question.question_id == question_id).first()
    if not q or q.page_token != t:
        return HTMLResponse("<h1>Not found or link expired.</h1>", status_code=404)
    if q.status == "answered":
        return HTMLResponse("<p>Already answered.</p>")

    form = await request.form()
    reply = form.get("reply")
    if reply not in {"me", "not_me"}:
        return HTMLResponse("<p>Invalid reply.</p>", status_code=400)

    # In-app screen submission is always verified
    q.reply = reply
    q.verified = True
    q.channel = "in_app"
    q.status = "answered"
    q.answered_at = datetime.utcnow()
    db.commit()

    audit(db, "dana", "question_answered_inapp",
          {"question_id": question_id, "reply": reply}, "answered",
          txn_id=q.txn_id)

    if reply == "me":
        outcome = "Resolved. Your card is unblocked. This merchant is saved as a known supplier. Your supplier payments and rent transfer are unaffected."
    else:
        outcome = "Thank you. We've placed a partial hold on this charge only. Your supplier payments and rent transfer are unaffected. A case has been opened for review."

    return HTMLResponse(_render_outcome(q, outcome))


def _render_question(template: str, q: Question) -> str:
    """Inject live values into the question template."""
    amount_str = f"${q.amount:,.2f}" if q.amount else "an amount"
    return (
        template
        .replace("{{question_id}}", q.question_id)
        .replace("{{page_token}}", q.page_token)
        .replace("{{merchant_name}}", q.merchant_name or "Unknown merchant")
        .replace("{{amount}}", amount_str)
        .replace("{{plain_reason}}", q.plain_reason or q.question_text)
    )


def _render_outcome(q: Question, message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Card Alert — Resolved</title>
<style>
  body {{font-family: -apple-system,'Segoe UI',system-ui,sans-serif;background:#f7f8fa;
         margin:0;display:flex;justify-content:center;align-items:flex-start;min-height:100vh}}
  .card {{background:#fff;border-radius:12px;padding:32px 24px;max-width:380px;
          width:100%;margin:40px 16px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
  h2 {{margin-top:0;font-size:1.25rem;color:#1f2328}}
  p {{color:#444;line-height:1.6}}
  .ok {{color:#1a7f37;font-weight:600}}
</style>
</head>
<body>
<div class="card">
  <p style="font-size:.75rem;color:#57606a;font-weight:600;letter-spacing:.08em;
             text-transform:uppercase">Verified in-app</p>
  <h2>Response recorded</h2>
  <p class="ok">{message}</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
  <p style="font-size:.75rem;color:#57606a">No links. Open your app to check any alert.</p>
</div>
</body>
</html>"""


@app.get("/app/case/{case_id}", response_class=HTMLResponse)
def case_page(case_id: str, t: str = Query(...), db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case or case.case_token != t:
        return HTMLResponse("<h1>Not found or link expired.</h1>", status_code=404)

    audit_entries = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )

    template = _load_template("case_view.html")
    return HTMLResponse(_render_case(template, case, audit_entries))


def _render_case(template: str, case: Case, entries: list) -> str:
    timeline_html = ""
    for e in entries:
        timeline_html += f"""
        <div class="step">
          <div class="step-time">{e.timestamp.strftime('%H:%M:%S UTC')}</div>
          <div class="step-actor">{e.actor}</div>
          <div class="step-action">{e.action.replace('_', ' ').title()}</div>
          {"<div class='step-reason'>" + (e.reason or "") + "</div>" if e.reason else ""}
        </div>"""

    status_css = case.status.replace("_", "-").lower()

    return (
        template
        .replace("{{case_id}}", case.case_id)
        .replace("{{case_status}}", case.status.replace("_", " ").title())
        .replace("{{case_status_css}}", status_css)
        .replace("{{summary}}", case.summary or "Under review.")
        .replace("{{what_next}}", case.what_next or "Awaiting next action.")
        .replace("{{timeline}}", timeline_html)
        .replace("{{updated_at}}", case.updated_at.strftime("%Y-%m-%d %H:%M UTC"))
    )
