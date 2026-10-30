# Orchestrate scenario results (live agents)

Run: 2026-10-30

| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |
|---|---|---|---|---|---|---|---|---|
| S1 | S-TXN-001 | 0 | low | clear | None | None | clear | PASS |
| S2 | S-TXN-002 | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005a | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005b | 50 | moderate | release | None | HOLD-4A6045C524 | release | PASS |
| S5 | S-TXN-005c | 50 | moderate | escalate | CASE-9F592275DF | HOLD-41D17BCB72 | escalate | PASS |
| S8 | S-TXN-008 | 30 | moderate | escalate | CASE-D76DA1B9CC | HOLD-7AF84AF781 | escalate | PASS |

## Response time (seconds)

Targets: first assessment <= 45 s, continue after reply <= 60 s, total per transaction <= 150 s.

| Scenario | Txn | Assess | Continue | Total | Within target |
|---|---|---|---|---|---|
| S1 | S-TXN-001 | 18 | - | 18 | yes |
| S2 | S-TXN-002 | 21 | 16 | 38 | yes |
| S5 | S-TXN-005a | 26 | 17 | 48 | yes |
| S5 | S-TXN-005b | 21 | 18 | 39 | yes |
| S5 | S-TXN-005c | 20 | 29 | 54 | yes |
| S8 | S-TXN-008 | 19 | 13 | 37 | yes |

## Hand-off integrity (bank records vs scenario)

| Scenario | Txn | Result |
|---|---|---|
| S1 | S-TXN-001 | OK |
| S2 | S-TXN-002 | OK |
| S5 | S-TXN-005a | OK |
| S5 | S-TXN-005b | OK |
| S5 | S-TXN-005c | OK |
| S8 | S-TXN-008 | OK |
