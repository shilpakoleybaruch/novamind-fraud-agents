"""Seed the SQLite database from data/ JSON files.

Called automatically on first startup when tables are empty.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from models import Baseline, Customer, Transaction

# Resolve data/ — honour SEED_DATA_DIR env var (set in Docker image) or fall back to repo path
_DATA_DIR = Path(os.environ.get("SEED_DATA_DIR", "")) or Path(__file__).parent.parent / "data"


def _parse_dt(s: str) -> datetime:
    """Parse ISO-8601 UTC string to a naive UTC datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def seed_if_empty(session: Session) -> bool:
    """Seed the DB from JSON files. Returns True if seeding happened."""
    if session.query(Customer).count() > 0:
        return False  # already seeded

    # ---- Customer ---------------------------------------------------------
    customer_path = _DATA_DIR / "customer_dana.json"
    with open(customer_path) as f:
        raw = json.load(f)

    account = raw["accounts"][0]
    card = account["cards"][0]

    customer = Customer(
        customer_id=raw["customer_id"],
        name=raw["name"],
        account_id=account["account_id"],
        card_id=card["card_id"],
        essential_payees_json=json.dumps(raw.get("essential_payees", [])),
        contact_json=json.dumps(raw.get("contact", {})),
    )
    session.add(customer)

    # ---- Transactions -------------------------------------------------------
    txn_path = _DATA_DIR / "transactions_dana.json"
    with open(txn_path) as f:
        txns_raw = json.load(f)

    for t in txns_raw:
        txn = Transaction(
            txn_id=t["txn_id"],
            customer_id=t["customer_id"],
            account_id=t["account_id"],
            card_id=t.get("card_id"),
            timestamp=_parse_dt(t["timestamp"]),
            merchant_name=t.get("merchant_name"),
            merchant_id=t.get("merchant_id"),
            terminal_id=t.get("terminal_id"),
            mcc=t.get("mcc"),
            amount=t["amount"],
            currency=t.get("currency", "USD"),
            channel=t.get("channel"),
            city=t.get("city"),
            country=t.get("country"),
        )
        session.add(txn)

    # ---- Baseline stub ------------------------------------------------------
    # A minimal baseline is created so the baseline_agent can update it later.
    total_txns = len(txns_raw)
    if total_txns:
        sorted_txns = sorted(txns_raw, key=lambda x: x["timestamp"])
        first_dt = _parse_dt(sorted_txns[0]["timestamp"])
        last_dt = _parse_dt(sorted_txns[-1]["timestamp"])
        history_days = max(1, (last_dt - first_dt).days)
    else:
        history_days = 0

    baseline = Baseline(
        customer_id=raw["customer_id"],
        data_json=json.dumps({}),
        history_days=history_days,
        transaction_count=total_txns,
    )
    session.add(baseline)

    session.commit()
    print(f"[seed] Seeded {total_txns} transactions for customer {raw['customer_id']}.")
    return True
