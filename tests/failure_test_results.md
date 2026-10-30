# Failure and fallback test (live agents)

Run: 2026-10-30

| Test | Expected | Actual branch | Seconds | Result | What the agent said |
|---|---|---|---|---|---|
| Bank down: normal purchase (S1) | not cleared or released | escalate | 9 | PASS | risk_agent { "status": "manual_review", "branch": "escalate", "reason": "Bank unreachable; no action taken, needs manual review." } |
| Bank down: unusual purchase (S2) | not cleared or released | escalate | 8 | PASS | risk_agent { "status": "manual_review", "branch": "escalate", "reason": "Bank unreachable; no action taken, needs manual review." } |
| Bank back up: normal purchase (S1) | clear | clear | 15 | PASS | risk_agent { "txn_id": "S-TXN-001", "score": 0, "level": "low", "branch": "clear", "decision_ids": ["AUTH-258BDD676C20"], "case_id": null, "hold_id": null, "customer_message": null, "reason": "Transac |
