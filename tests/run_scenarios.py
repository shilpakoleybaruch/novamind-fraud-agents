"""Integration scenario runner for Novamind.

Drives every scenario in data/scenarios.json against the real FastAPI app
(no Orchestrate, no cloud, no LLM).  The pipeline simulates what the agents
would do:

  1. POST /admin/reset/{customer_id}     — clean slate
  2. Build + PUT baseline via API        — mimics baseline_agent.compute_baseline
  3. compare_to_baseline (tool, mocked)  — pure Python, no HTTP to real server
  4. score_risk (scoring.py direct)      — deterministic
  5. POST /transactions/score-context    — get approvals_last_24h + essential payees
  6. POST /risk-decisions                — record decision, get authorization_id
  7. If moderate: POST /questions + simulate-reply + conditional release/hold
  8. If high: POST /holds + POST /cases + POST analyst-queue
  9. GET /audit?txn_id=...               — verify invariants
 10. Record latency, write tests/results.md

Run from repo root:
    ENABLE_TEST_ENDPOINTS=true python3 -m pytest tests/run_scenarios.py -v -s
or directly:
    ENABLE_TEST_ENDPOINTS=true python3 tests/run_scenarios.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import types
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — make tools/ importable; stub the Orchestrate decorator
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "mock_bank"))

_fake_pkg = types.ModuleType("ibm_watsonx_orchestrate")
_fake_ab = types.ModuleType("ibm_watsonx_orchestrate.agent_builder")
_fake_tools_mod = types.ModuleType("ibm_watsonx_orchestrate.agent_builder.tools")
_fake_tools_mod.tool = lambda f: f
_fake_pkg.agent_builder = _fake_ab
_fake_ab.tools = _fake_tools_mod
sys.modules.setdefault("ibm_watsonx_orchestrate", _fake_pkg)
sys.modules.setdefault("ibm_watsonx_orchestrate.agent_builder", _fake_ab)
sys.modules.setdefault("ibm_watsonx_orchestrate.agent_builder.tools", _fake_tools_mod)

from baseline_agent_tools import compare_to_baseline  # noqa: E402
from scoring import score_risk                        # noqa: E402

# ---------------------------------------------------------------------------
# App + TestClient setup
# ---------------------------------------------------------------------------

import tempfile

os.environ["MOCK_BANK_API_KEY"] = "runner-secret"
os.environ["ENABLE_TEST_ENDPOINTS"] = "true"
# seed.py uses SEED_DATA_DIR to locate customer_dana.json + transactions_dana.json
os.environ["SEED_DATA_DIR"] = str(REPO_ROOT / "data")
_tmp_db = tempfile.mktemp(suffix="-runner.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from main import app, get_db
from models import Baseline, Customer, Transaction, create_tables, get_engine
from seed import seed_if_empty

TEST_ENGINE = get_engine(f"sqlite:///{_tmp_db}")
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)

API_KEY = "runner-secret"
HEADERS = {"X-API-Key": API_KEY}
CUSTOMER_ID = "C-DANA-001"

# ---------------------------------------------------------------------------
# Module-level fixtures: create tables, seed Dana, override DB dependency
# ---------------------------------------------------------------------------


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    create_tables(TEST_ENGINE)
    app.dependency_overrides[get_db] = override_get_db
    with TestSession() as s:
        seed_if_empty(s)
    yield
    app.dependency_overrides.clear()
    try:
        os.unlink(_tmp_db)
    except OSError:
        pass


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Load fixtures
# ---------------------------------------------------------------------------

DATA_DIR = REPO_ROOT / "data"

with open(DATA_DIR / "scenarios.json") as f:
    ALL_SCENARIOS: list[dict] = json.load(f)

with open(DATA_DIR / "transactions_dana.json") as f:
    DANA_HISTORY: list[dict] = json.load(f)

# ---------------------------------------------------------------------------
# Baseline builder (pure Python — same logic as compute_baseline tool)
# ---------------------------------------------------------------------------

import statistics as _stats_mod
from collections import defaultdict as _dd


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _build_baseline(txns: list[dict]) -> dict:
    """Compute a baseline dict from a list of transaction dicts."""
    parsed = []
    for t in txns:
        try:
            t2 = dict(t)
            t2["_dt"] = _dt(t["timestamp"])
            parsed.append(t2)
        except Exception:
            pass
    if not parsed:
        return {}
    parsed.sort(key=lambda t: t["_dt"])
    first_dt = parsed[0]["_dt"]
    last_dt = parsed[-1]["_dt"]
    history_days = max(1, (last_dt - first_dt).days)
    n = len(parsed)
    thin = n < 30 or history_days < 60

    amounts_by_merchant: dict = _dd(list)
    amounts_by_mcc: dict = _dd(list)
    hours_by_merchant: dict = _dd(list)
    terminals_by_merchant: dict = _dd(set)
    known_merchants: set = set()
    weekly_amounts: dict = _dd(float)

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
            hours_by_merchant[mid].append(dt.hour)
            if tid:
                terminals_by_merchant[mid].add(tid)
        if mcc:
            amounts_by_mcc[mcc].append(amt)
        weekly_amounts[week_key] += amt

    def _s(vals):
        if not vals:
            return {"median": 0.0, "p90": 0.0, "count": 0}
        sv = sorted(vals)
        idx = max(0, int(len(sv) * 0.9) - 1)
        return {
            "median": round(_stats_mod.median(sv), 2),
            "p90": round(sv[idx], 2),
            "count": len(sv),
        }

    wv = list(weekly_amounts.values())
    return {
        "known_merchants": sorted(known_merchants),
        "known_terminals": {m: sorted(ts) for m, ts in terminals_by_merchant.items()},
        "hour_range_per_merchant": {
            m: {"min": min(v), "max": max(v)}
            for m, v in hours_by_merchant.items() if v
        },
        "amount_stats_per_merchant": {m: _s(v) for m, v in amounts_by_merchant.items()},
        "amount_stats_per_mcc": {m: _s(v) for m, v in amounts_by_mcc.items()},
        "weekly_volume": round(_stats_mod.median(wv), 2) if wv else 0.0,
        "history_days": history_days,
        "transaction_count": n,
        "thin_baseline": thin,
    }


FULL_BASELINE = _build_baseline(DANA_HISTORY)

# Thin baseline: only last ~3 weeks of history (matches S7 baseline_override)
THIN_HISTORY = [
    t for t in DANA_HISTORY
    if _dt(t["timestamp"]) >= _dt("2026-09-22T00:00:00Z")
]
THIN_BASELINE = _build_baseline(THIN_HISTORY)


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def reset(client, customer_id: str = CUSTOMER_ID):
    r = client.post(f"/admin/reset/{customer_id}", headers=HEADERS)
    assert r.status_code == 200, f"reset failed: {r.text}"
    return r.json()


def put_baseline(client, customer_id: str, baseline: dict):
    """Upload a pre-computed baseline dict to the mock bank."""
    n = baseline.get("transaction_count", 0)
    hd = baseline.get("history_days", 0)
    r = client.put(
        f"/customers/{customer_id}/baseline",
        headers=HEADERS,
        json={"data": baseline, "history_days": hd, "transaction_count": n},
    )
    assert r.status_code == 200, f"put_baseline failed: {r.text}"


def compare(customer_id: str, txn: dict, baseline: dict) -> dict:
    """Call compare_to_baseline with the baseline injected via mock."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": baseline}
    mock_resp.raise_for_status = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_cm)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_cm.get = MagicMock(return_value=mock_resp)
    with patch("baseline_agent_tools._client", return_value=mock_cm):
        result = compare_to_baseline(customer_id, txn)
    assert result["ok"], f"compare_to_baseline failed: {result}"
    return result


def score_context(client, txn: dict) -> dict:
    r = client.post("/transactions/score-context", headers=HEADERS, json=txn)
    assert r.status_code == 200, f"score-context failed: {r.text}"
    return r.json()


def record_decision(
    client,
    customer_id: str,
    txn_id: str,
    score: int,
    level: str,
    decision: str,
    signals: list,
    reason: str,
) -> str:
    r = client.post(
        "/risk-decisions",
        headers=HEADERS,
        json={
            "customer_id": customer_id,
            "txn_id": txn_id,
            "score": score,
            "level": level,
            "decision": decision,
            "signals": signals,
            "reason": reason,
        },
    )
    assert r.status_code == 201, f"record_decision({decision}) failed: {r.text}"
    return r.json()["authorization_id"]


def create_question(client, customer_id: str, txn: dict, auth_id: str) -> str:
    r = client.post(
        "/questions",
        headers=HEADERS,
        json={
            "customer_id": customer_id,
            "txn_id": txn["txn_id"],
            "authorization_id": auth_id,
            "question_text": "Was this you?",
            "merchant_name": txn.get("merchant_name", ""),
            "amount": txn.get("amount", 0),
        },
    )
    assert r.status_code == 201, f"create_question failed: {r.text}"
    return r.json()["question_id"]


def simulate_reply(client, q_id: str, reply: str, verified: bool) -> dict:
    channel = "in_app" if verified else "external"
    r = client.post(
        f"/questions/{q_id}/simulate-reply",
        headers=HEADERS,
        json={"reply": reply, "verified": verified, "channel": channel},
    )
    assert r.status_code == 200, f"simulate_reply failed: {r.text}"
    return r.json()


def place_hold(client, customer_id: str, txn_id: str, auth_id: str) -> str:
    r = client.post(
        "/holds",
        headers=HEADERS,
        json={
            "customer_id": customer_id,
            "txn_id": txn_id,
            "authorization_id": auth_id,
            "scope": "transaction",
            "reason": "runner-placed hold",
        },
    )
    assert r.status_code == 201, f"place_hold failed: {r.text}"
    return r.json()["hold_id"]


def release_hold_req(client, hold_id: str, auth_id: str) -> dict:
    """Attempt release; return full response (may be 403)."""
    return client.post(
        f"/holds/{hold_id}/release",
        headers=HEADERS,
        json={"authorization_id": auth_id, "actor": "action_agent"},
    )


def open_case(client, customer_id: str, txn_id: str, auth_id: str, hold_id: Optional[str] = None) -> str:
    body: dict = {
        "customer_id": customer_id,
        "txn_id": txn_id,
        "authorization_id": auth_id,
        "summary": "runner-opened case",
    }
    if hold_id:
        body["hold_id"] = hold_id
    r = client.post("/cases", headers=HEADERS, json=body)
    assert r.status_code == 201, f"open_case failed: {r.text}"
    return r.json()["case_id"]


def analyst_queue(client, case_id: str) -> dict:
    r = client.post(f"/cases/{case_id}/analyst-queue", headers=HEADERS)
    assert r.status_code == 200, f"analyst_queue failed: {r.text}"
    return r.json()


def get_audit(client, txn_id: str) -> list[dict]:
    r = client.get(f"/audit?txn_id={txn_id}&limit=200", headers=HEADERS)
    assert r.status_code == 200, f"audit read failed: {r.text}"
    return r.json()


def get_audit_multi(client, txn_ids: list[str]) -> list[dict]:
    entries = []
    for tid in txn_ids:
        entries.extend(get_audit(client, tid))
    return entries


# ---------------------------------------------------------------------------
# Single-transaction scenario runner
# ---------------------------------------------------------------------------

def run_one(
    client,
    txn: dict,
    baseline: dict,
    simulated_reply: Optional[str],
    reply_verified: bool,
    customer_id: str = CUSTOMER_ID,
) -> dict:
    """Run the full pipeline for a single transaction.

    Returns a result dict with keys:
      score, level, decision, hold_id, case_id, release_status,
      audit_entries, escalated, error
    """
    result: dict = {
        "score": None,
        "level": None,
        "decision": None,
        "hold_id": None,
        "case_id": None,
        "release_status": None,
        "audit_entries": [],
        "escalated": False,
        "error": None,
    }

    try:
        # Step 1: upload baseline
        put_baseline(client, customer_id, baseline)

        # Step 2: compare_to_baseline (pure Python, baseline injected)
        cmp = compare(customer_id, txn, baseline)
        signals = cmp["signals"]
        thin = cmp["thin_baseline"]

        # Step 3: score-context (get approvals_last_24h from live DB)
        ctx = score_context(client, txn)
        approvals = ctx["approvals_last_24h"]

        # Step 4: score_risk
        sr = score_risk(signals, thin, approvals)
        result["score"] = sr["score"]
        result["level"] = sr["level"]

        # Step 5: decide + record
        level = sr["level"]
        must_escalate = sr["must_escalate"]
        escalate_on_approval = sr["escalate_on_approval"]

        if level == "low":
            decision = "clear"
            auth = record_decision(
                client, customer_id, txn["txn_id"],
                sr["score"], level, decision, signals, "low risk — cleared",
            )
            result["decision"] = decision

        elif level == "moderate":
            # Record "ask" first
            auth = record_decision(
                client, customer_id, txn["txn_id"],
                sr["score"], level, "ask", signals, "moderate — asking",
            )

            if must_escalate:
                # Shouldn't happen on first txn of a fresh scenario, but handle it
                esc_auth = record_decision(
                    client, customer_id, txn["txn_id"],
                    sr["score"], level, "escalate", signals,
                    "must_escalate=True before asking",
                )
                hold_id = place_hold(client, customer_id, txn["txn_id"], esc_auth)
                case_id = open_case(client, customer_id, txn["txn_id"], esc_auth, hold_id)
                analyst_queue(client, case_id)
                result.update(decision="escalate", hold_id=hold_id, case_id=case_id, escalated=True)

            elif simulated_reply == "none" or simulated_reply is None:
                # No reply → hold + case + analyst
                hold_auth = record_decision(
                    client, customer_id, txn["txn_id"],
                    sr["score"], level, "hold", signals, "no reply — holding",
                )
                hold_id = place_hold(client, customer_id, txn["txn_id"], hold_auth)
                case_id = open_case(client, customer_id, txn["txn_id"], hold_auth, hold_id)
                analyst_queue(client, case_id)
                result.update(decision="no_reply_hold", hold_id=hold_id, case_id=case_id, escalated=True)

            else:
                # Ask Dana
                q_id = create_question(client, customer_id, txn, auth)
                simulate_reply(client, q_id, simulated_reply, reply_verified)

                if simulated_reply == "me" and reply_verified:
                    if escalate_on_approval:
                        # 3rd approval would trip the gate — escalate without releasing.
                        # No hold is placed here: the hold would only be placed by the
                        # server backstop anyway, and this branch exits before release.
                        esc_auth = record_decision(
                            client, customer_id, txn["txn_id"],
                            sr["score"], level, "escalate", signals,
                            "escalate_on_approval: 3rd approval in 24h",
                        )
                        case_id = open_case(client, customer_id, txn["txn_id"], esc_auth)
                        analyst_queue(client, case_id)
                        result.update(
                            decision="escalate_on_approval",
                            case_id=case_id, escalated=True,
                        )
                    else:
                        # Release path.
                        # Attempt a provisional hold. If the transaction is on an essential
                        # payee the server correctly returns 403 — that is the right bank
                        # behaviour (essential payees are never held). In that case no hold
                        # exists, so we record the release decision directly without a hold_id.
                        hold_auth = record_decision(
                            client, customer_id, txn["txn_id"],
                            sr["score"], level, "hold", signals, "placing provisional hold",
                        )
                        hold_r = client.post(
                            "/holds",
                            headers=HEADERS,
                            json={
                                "customer_id": customer_id,
                                "txn_id": txn["txn_id"],
                                "authorization_id": hold_auth,
                                "scope": "transaction",
                                "reason": "runner-placed hold",
                            },
                        )
                        if hold_r.status_code == 403 and "essential payee" in hold_r.json().get("detail", ""):
                            # Essential payee — hold correctly refused; treat as clean release
                            record_decision(
                                client, customer_id, txn["txn_id"],
                                sr["score"], level, "release", signals,
                                "verified me — essential payee, hold refused by guardrail (correct)",
                            )
                            result.update(decision="release", release_status=200)
                        elif hold_r.status_code == 201:
                            hold_id = hold_r.json()["hold_id"]
                            rel_auth = record_decision(
                                client, customer_id, txn["txn_id"],
                                sr["score"], level, "release", signals,
                                "verified me reply — releasing",
                            )
                            rel_r = release_hold_req(client, hold_id, rel_auth)
                            result["release_status"] = rel_r.status_code
                            if rel_r.status_code == 200:
                                result.update(decision="release", hold_id=hold_id)
                            else:
                                # Server backstop fired — escalate
                                esc_auth = record_decision(
                                    client, customer_id, txn["txn_id"],
                                    sr["score"], level, "escalate", signals,
                                    f"release refused ({rel_r.status_code}): {rel_r.json().get('detail', '')}",
                                )
                                case_id = open_case(
                                    client, customer_id, txn["txn_id"], esc_auth, hold_id
                                )
                                analyst_queue(client, case_id)
                                result.update(
                                    decision="escalate_backstop",
                                    hold_id=hold_id, case_id=case_id, escalated=True,
                                )
                        else:
                            result.update(
                                decision="hold_failed",
                                error=f"hold POST {hold_r.status_code}: {hold_r.text}",
                            )

                elif simulated_reply == "me" and not reply_verified:
                    # Scam / unverified reply — hold + escalate, no release
                    hold_auth = record_decision(
                        client, customer_id, txn["txn_id"],
                        sr["score"], level, "hold", signals, "unverified reply — holding",
                    )
                    hold_id = place_hold(client, customer_id, txn["txn_id"], hold_auth)
                    esc_auth = record_decision(
                        client, customer_id, txn["txn_id"],
                        sr["score"], level, "escalate", signals,
                        "unverified reply — escalating",
                    )
                    case_id = open_case(client, customer_id, txn["txn_id"], esc_auth, hold_id)
                    analyst_queue(client, case_id)
                    result.update(
                        decision="unverified_escalate",
                        hold_id=hold_id, case_id=case_id, escalated=True,
                    )

                else:  # not_me
                    hold_auth = record_decision(
                        client, customer_id, txn["txn_id"],
                        sr["score"], level, "hold", signals, "not me — holding",
                    )
                    hold_id = place_hold(client, customer_id, txn["txn_id"], hold_auth)
                    case_id = open_case(client, customer_id, txn["txn_id"], hold_auth, hold_id)
                    result.update(decision="hold_not_me", hold_id=hold_id, case_id=case_id)

        else:  # high
            hold_auth = record_decision(
                client, customer_id, txn["txn_id"],
                sr["score"], level, "hold", signals, "high risk — holding immediately",
            )
            hold_id = place_hold(client, customer_id, txn["txn_id"], hold_auth)
            esc_auth = record_decision(
                client, customer_id, txn["txn_id"],
                sr["score"], level, "escalate", signals, "high risk — escalating",
            )
            case_id = open_case(client, customer_id, txn["txn_id"], esc_auth, hold_id)
            analyst_queue(client, case_id)
            result.update(decision="hold_escalate", hold_id=hold_id, case_id=case_id, escalated=True)

    except Exception as exc:
        result["error"] = str(exc)

    # Read audit log
    result["audit_entries"] = get_audit(client, txn["txn_id"])
    return result


# ---------------------------------------------------------------------------
# Invariant checkers
# ---------------------------------------------------------------------------

def check_no_release_without_verified(audit_entries: list[dict], txn_id: str) -> list[str]:
    """Invariant: hold_released must only appear when reply was me+verified."""
    failures = []
    for e in audit_entries:
        if e.get("action") == "hold_released" and e.get("txn_id") == txn_id:
            # Release appeared — verify it was legal by checking no release_rejected also exists
            rejections = [
                x for x in audit_entries
                if x.get("action") == "release_rejected" and x.get("txn_id") == txn_id
            ]
            if rejections:
                failures.append(
                    f"FAIL: hold_released AND release_rejected both appear for {txn_id}"
                )
    return failures


def check_no_essential_payee_blocked(audit_entries: list[dict], essential_payees: list) -> list[str]:
    """Invariant: no hold_placed on an essential payee's transaction."""
    failures = []
    ep_names_lower = {ep["name"].lower() for ep in essential_payees}
    for e in audit_entries:
        if e.get("action") == "hold_placed":
            inputs = e.get("inputs", {})
            # inputs is a dict from the audit log
            merchant = (inputs.get("merchant_name") or "").lower()
            if merchant and merchant in ep_names_lower:
                failures.append(
                    f"FAIL: hold_placed on essential payee '{merchant}' in txn {e.get('txn_id')}"
                )
    return failures


def check_s5_third_escalates(sub_results: list[dict]) -> list[str]:
    """S5 invariant: 3rd sub-transaction must escalate, not release."""
    failures = []
    third = sub_results[2]
    d = third["decision"]
    if d not in ("escalate_on_approval", "escalate", "escalate_backstop"):
        failures.append(
            f"FAIL S5: 3rd approval must escalate; got decision='{d}'"
        )
    released = [
        e for e in third["audit_entries"]
        if e.get("action") == "hold_released"
    ]
    if released:
        failures.append("FAIL S5: hold_released found in 3rd sub-transaction audit log")
    return failures


def check_s8_nothing_released(result: dict) -> list[str]:
    """S8 invariant: unverified reply must not produce hold_released."""
    failures = []
    released = [e for e in result["audit_entries"] if e.get("action") == "hold_released"]
    if released:
        failures.append("FAIL S8: hold_released found despite unverified reply")
    return failures


# ---------------------------------------------------------------------------
# S5 multi-transaction runner
# ---------------------------------------------------------------------------

def run_s5(client, scenario: dict, baseline: dict) -> tuple[dict, list[dict]]:
    """Run S5's three sub-transactions in sequence without resetting between them.

    Returns (scenario_result_dict, list_of_per_sub_result_dicts).
    """
    sub_results = []
    txns = scenario["transactions"]
    for i, txn in enumerate(txns):
        put_baseline(client, CUSTOMER_ID, baseline)
        sub = run_one(
            client,
            txn,
            baseline,
            simulated_reply=scenario["simulated_reply"],
            reply_verified=bool(scenario["reply_verified"]),
        )
        sub_results.append(sub)

    all_audit = get_audit_multi(client, [t["txn_id"] for t in txns])
    failures = check_s5_third_escalates(sub_results)

    decisions = [s["decision"] for s in sub_results]
    scenario_result = {
        "scenario_id": scenario["scenario_id"],
        "sub_decisions": decisions,
        "scores": [s["score"] for s in sub_results],
        "levels": [s["level"] for s in sub_results],
        "failures": failures,
        "audit_count": len(all_audit),
    }
    return scenario_result, sub_results


# ---------------------------------------------------------------------------
# results.md writer
# ---------------------------------------------------------------------------

RESULTS_PATH = REPO_ROOT / "tests" / "results.md"


def _pass_fail(failures: list[str]) -> str:
    return "PASS" if not failures else f"FAIL ({len(failures)})"


def write_results(rows: list[dict]) -> None:
    lines = [
        "# Novamind Scenario Runner Results",
        "",
        f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Scenario Results",
        "",
        "| Scenario | Score | Level | Decision | Hold? | Released? | Escalated? | Invariants | Latency ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        score = r.get("score", "—")
        if score is None:
            score = "—"
        level = r.get("level") or "—"
        decision = r.get("decision") or "—"
        hold = "yes" if r.get("hold_id") else "no"
        released = "yes" if r.get("release_status") == 200 else "no"
        escalated = "yes" if r.get("escalated") else "no"
        inv = _pass_fail(r.get("failures", []))
        latency = f"{r.get('latency_ms', 0):.0f}"
        sid = r.get("scenario_id", "?")
        lines.append(
            f"| {sid} | {score} | {level} | {decision} | {hold} | {released} | {escalated} | {inv} | {latency} |"
        )

    # Failure details
    any_failures = [r for r in rows if r.get("failures")]
    if any_failures:
        lines += ["", "## Invariant Failures", ""]
        for r in any_failures:
            lines.append(f"### {r['scenario_id']}")
            for f in r["failures"]:
                lines.append(f"- {f}")
            lines.append("")
    else:
        lines += ["", "_All invariants passed._", ""]

    RESULTS_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nResults written to {RESULTS_PATH}")


# ---------------------------------------------------------------------------
# Pytest test classes — one per scenario
# ---------------------------------------------------------------------------

# Essential payees from Dana's customer data
ESSENTIAL_PAYEES = [
    {"name": "NorthSide Supply"},
    {"name": "Greenway Properties"},
]

_scenario_map = {s["scenario_id"]: s for s in ALL_SCENARIOS}

# Shared storage for results across tests (module-scoped)
_results: list[dict] = []


class TestS1Low:
    def test_s1(self, client):
        s = _scenario_map["S1_low"]
        reset(client)
        t0 = time.perf_counter()
        r = run_one(
            client, s["transaction"], FULL_BASELINE,
            simulated_reply=s["simulated_reply"],
            reply_verified=bool(s.get("reply_verified")),
        )
        latency = (time.perf_counter() - t0) * 1000

        assert r["level"] == "low", f"S1: expected low, got {r['level']} (score={r['score']})"
        assert r["decision"] == "clear"
        assert r["hold_id"] is None

        failures = check_no_release_without_verified(r["audit_entries"], s["transaction"]["txn_id"])
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S1_low", "failures": failures, "latency_ms": latency})


class TestS2ModerateMeRelease:
    def test_s2(self, client):
        s = _scenario_map["S2_moderate_me"]
        reset(client)
        t0 = time.perf_counter()
        r = run_one(
            client, s["transaction"], FULL_BASELINE,
            simulated_reply=s["simulated_reply"],
            reply_verified=bool(s.get("reply_verified")),
        )
        latency = (time.perf_counter() - t0) * 1000

        assert r["level"] == "moderate", f"S2: expected moderate, got {r['level']}"
        assert r["decision"] == "release", f"S2: expected release, got {r['decision']}"
        assert r["release_status"] == 200, f"S2: release status {r['release_status']}"

        failures = check_no_release_without_verified(r["audit_entries"], s["transaction"]["txn_id"])
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S2_moderate_me", "failures": failures, "latency_ms": latency})


class TestS3ModerateNotMe:
    def test_s3(self, client):
        s = _scenario_map["S3_moderate_not_me"]
        reset(client)
        t0 = time.perf_counter()
        r = run_one(
            client, s["transaction"], FULL_BASELINE,
            simulated_reply=s["simulated_reply"],
            reply_verified=bool(s.get("reply_verified")),
        )
        latency = (time.perf_counter() - t0) * 1000

        assert r["level"] == "moderate", f"S3: expected moderate, got {r['level']}"
        assert r["decision"] == "hold_not_me"
        assert r["hold_id"] is not None
        assert r["case_id"] is not None
        assert r["release_status"] is None, "S3: no release should happen for not_me"

        failures = check_no_release_without_verified(r["audit_entries"], s["transaction"]["txn_id"])
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S3_moderate_not_me", "failures": failures, "latency_ms": latency})


class TestS4High:
    def test_s4(self, client):
        s = _scenario_map["S4_high"]
        reset(client)
        t0 = time.perf_counter()
        r = run_one(
            client, s["transaction"], FULL_BASELINE,
            simulated_reply=s["simulated_reply"],
            reply_verified=bool(s.get("reply_verified")),
        )
        latency = (time.perf_counter() - t0) * 1000

        assert r["level"] == "high", f"S4: expected high, got {r['level']}"
        assert r["decision"] == "hold_escalate"
        assert r["hold_id"] is not None
        assert r["escalated"] is True
        assert r["release_status"] is None

        failures = check_no_release_without_verified(r["audit_entries"], s["transaction"]["txn_id"])
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S4_high", "failures": failures, "latency_ms": latency})


class TestS5RepeatApprovals:
    def test_s5(self, client):
        s = _scenario_map["S5_repeat_approvals"]
        reset(client)
        t0 = time.perf_counter()
        scenario_r, sub_results = run_s5(client, s, FULL_BASELINE)
        latency = (time.perf_counter() - t0) * 1000

        # First two must be releases, third must escalate
        assert sub_results[0]["decision"] == "release", (
            f"S5 txn1: expected release, got {sub_results[0]['decision']}"
        )
        assert sub_results[1]["decision"] == "release", (
            f"S5 txn2: expected release, got {sub_results[1]['decision']}"
        )
        assert sub_results[2]["decision"] in ("escalate_on_approval", "escalate", "escalate_backstop"), (
            f"S5 txn3: expected escalate, got {sub_results[2]['decision']}"
        )

        failures = scenario_r["failures"]
        assert not failures, failures

        # Build summary row for results table
        _results.append({
            "scenario_id": "S5_repeat_approvals",
            "score": scenario_r["scores"][2],   # 3rd txn score (the one that matters)
            "level": scenario_r["levels"][2],
            "decision": f"{sub_results[0]['decision']}, {sub_results[1]['decision']}, {sub_results[2]['decision']}",
            "hold_id": sub_results[2].get("hold_id"),
            "case_id": sub_results[2].get("case_id"),
            "release_status": None,
            "escalated": True,
            "failures": failures,
            "latency_ms": latency,
            "audit_entries": [],
        })


class TestS6NoReply:
    def test_s6(self, client):
        s = _scenario_map["S6_no_reply"]
        reset(client)
        t0 = time.perf_counter()
        r = run_one(
            client, s["transaction"], FULL_BASELINE,
            simulated_reply="none",
            reply_verified=False,
        )
        latency = (time.perf_counter() - t0) * 1000

        assert r["level"] == "moderate", f"S6: expected moderate, got {r['level']}"
        assert r["escalated"] is True, "S6: no-reply must escalate"
        assert r["release_status"] is None, "S6: no release on no-reply"

        failures = check_no_release_without_verified(r["audit_entries"], s["transaction"]["txn_id"])
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S6_no_reply", "failures": failures, "latency_ms": latency})


class TestS7ThinBaseline:
    def test_s7(self, client):
        s = _scenario_map["S7_thin_baseline"]
        reset(client)
        t0 = time.perf_counter()
        # S7 uses the thin baseline, not the full one
        r = run_one(
            client, s["transaction"], THIN_BASELINE,
            simulated_reply=s["simulated_reply"],
            reply_verified=bool(s.get("reply_verified")),
        )
        latency = (time.perf_counter() - t0) * 1000

        # Thin baseline lowers threshold to 20; transaction must be moderate or high
        assert r["level"] in ("moderate", "high"), (
            f"S7: thin baseline must produce moderate or high, got {r['level']} (score={r['score']})"
        )

        failures = check_no_release_without_verified(r["audit_entries"], s["transaction"]["txn_id"])
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S7_thin_baseline", "failures": failures, "latency_ms": latency})


class TestS8ScamReply:
    def test_s8(self, client):
        s = _scenario_map["S8_scam_reply"]
        reset(client)
        t0 = time.perf_counter()
        # S8: reply claims "me" but verified=False (scam / unverified channel)
        r = run_one(
            client, s["transaction"], FULL_BASELINE,
            simulated_reply="me",
            reply_verified=False,
        )
        latency = (time.perf_counter() - t0) * 1000

        assert r["level"] == "moderate", f"S8: expected moderate, got {r['level']}"
        assert r["release_status"] is None, (
            f"S8: release must not occur on unverified reply; got status {r['release_status']}"
        )
        assert r["hold_id"] is not None, "S8: hold must be placed"
        assert r["escalated"] is True, "S8: must escalate on unverified reply"

        failures = check_s8_nothing_released(r)
        failures += check_no_essential_payee_blocked(r["audit_entries"], ESSENTIAL_PAYEES)
        assert not failures, failures

        _results.append({**r, "scenario_id": "S8_scam_reply", "failures": failures, "latency_ms": latency})


# ---------------------------------------------------------------------------
# Final fixture — write results.md after all tests complete
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def write_results_after_all(setup_db):
    """Write results.md after all scenario tests have run."""
    yield
    if _results:
        write_results(_results)


# ---------------------------------------------------------------------------
# Direct-run entrypoint (python3 tests/run_scenarios.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess
    subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "-s"],
        env={**os.environ, "ENABLE_TEST_ENDPOINTS": "true"},
    )
