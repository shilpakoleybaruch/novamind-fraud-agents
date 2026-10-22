"""SQLAlchemy ORM models for the Novamind mock bank (SQLite)."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Customers & Transactions
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    account_id = Column(String, nullable=False)
    card_id = Column(String, nullable=False)
    # JSON-serialised list of essential payee dicts
    essential_payees_json = Column(Text, nullable=False, default="[]")
    # JSON-serialised contact prefs
    contact_json = Column(Text, nullable=False, default="{}")

    @property
    def essential_payees(self) -> list:
        return json.loads(self.essential_payees_json)

    @property
    def contact(self) -> dict:
        return json.loads(self.contact_json)


class Transaction(Base):
    __tablename__ = "transactions"

    txn_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)
    account_id = Column(String, nullable=False)
    card_id = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    merchant_name = Column(String, nullable=True)
    merchant_id = Column(String, nullable=True)
    terminal_id = Column(String, nullable=True)
    mcc = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="USD")
    channel = Column(String, nullable=True)      # card_present | card_not_present | transfer
    city = Column(String, nullable=True)
    country = Column(String, nullable=True)
    # set after scoring
    risk_score = Column(Float, nullable=True)


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

class Baseline(Base):
    __tablename__ = "baselines"

    baseline_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False, unique=True)
    # JSON blob — flexible schema, updated by baseline_agent
    data_json = Column(Text, nullable=False, default="{}")
    history_days = Column(Integer, nullable=True)
    transaction_count = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def data(self) -> dict:
        return json.loads(self.data_json)


# ---------------------------------------------------------------------------
# Risk Decisions
# ---------------------------------------------------------------------------

class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    authorization_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)
    txn_id = Column(String, ForeignKey("transactions.txn_id"), nullable=False)
    score = Column(Float, nullable=False)
    level = Column(String, nullable=False)   # low | moderate | high
    # clear | ask | hold | release | escalate
    decision = Column(String, nullable=False)
    signals_json = Column(Text, nullable=False, default="[]")
    branch = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    actor = Column(String, nullable=False, default="risk_agent")
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def signals(self) -> list:
        return json.loads(self.signals_json)


# ---------------------------------------------------------------------------
# Questions (in-app engagement)
# ---------------------------------------------------------------------------

class Question(Base):
    __tablename__ = "questions"

    question_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)
    txn_id = Column(String, ForeignKey("transactions.txn_id"), nullable=False)
    authorization_id = Column(String, ForeignKey("risk_decisions.authorization_id"), nullable=False)
    question_text = Column(Text, nullable=False)
    merchant_name = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    plain_reason = Column(Text, nullable=True)
    # status: pending | answered | expired
    status = Column(String, nullable=False, default="pending")
    # reply: me | not_me | null
    reply = Column(String, nullable=True)
    # verified: True only if reply came via in-app screen session
    verified = Column(Boolean, nullable=False, default=False)
    channel = Column(String, nullable=True)   # in_app | push | external
    page_token = Column(String, nullable=False)   # URL token for the HTML page
    second_channel_retried = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------

class Hold(Base):
    __tablename__ = "holds"

    hold_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)
    txn_id = Column(String, ForeignKey("transactions.txn_id"), nullable=False)
    authorization_id = Column(String, ForeignKey("risk_decisions.authorization_id"), nullable=False)
    # transaction | merchant | card_not_present
    scope = Column(String, nullable=False)
    # active | released
    status = Column(String, nullable=False, default="active")
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)
    released_by = Column(String, nullable=True)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

class Case(Base):
    __tablename__ = "cases"

    case_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)
    txn_id = Column(String, ForeignKey("transactions.txn_id"), nullable=True)
    authorization_id = Column(String, ForeignKey("risk_decisions.authorization_id"), nullable=True)
    hold_id = Column(String, ForeignKey("holds.hold_id"), nullable=True)
    # open | analyst_queued | resolved | escalated
    status = Column(String, nullable=False, default="open")
    summary = Column(Text, nullable=True)
    analyst_queued_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    what_next = Column(Text, nullable=True)
    case_token = Column(String, nullable=False)   # URL token for case view page
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    actor = Column(String, nullable=False)        # agent name | "dana" | "analyst"
    action = Column(String, nullable=False)
    inputs_json = Column(Text, nullable=False, default="{}")
    result = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=True)
    txn_id = Column(String, nullable=True)

    @property
    def inputs(self) -> dict:
        return json.loads(self.inputs_json)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_engine(db_url: str = "sqlite:///./mock_bank.db"):
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    # Enable WAL mode for SQLite concurrency
    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
    return engine


def create_tables(engine):
    Base.metadata.create_all(engine)
