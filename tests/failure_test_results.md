# Failure and fallback test (live agents)

Run: 2026-10-30

| Test | Expected | Actual branch | Seconds | Result | What the agent said |
|---|---|---|---|---|---|
| Bank down: normal purchase (S1) | not cleared or released | escalate | 9 | PASS | risk_agent { "status": "manual_review", "branch": "escalate", "reason": "Bank unreachable; no action taken, needs manual review." } |
| Bank down: unusual purchase (S2) | not cleared or released | escalate | 9 | PASS | risk_agent { "status": "manual_review", "branch": "escalate", "reason": "Bank unreachable; no action taken, needs manual review." } |
