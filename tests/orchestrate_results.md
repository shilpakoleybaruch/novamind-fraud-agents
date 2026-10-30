# Orchestrate scenario results (live agents)

Run: 2026-10-30

| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |
|---|---|---|---|---|---|---|---|---|
| S1 | S-TXN-001 | 0 | low | clear | None | None | clear | PASS |
| S2 | S-TXN-002 | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005a | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005b | 50 | moderate | release | None | HOLD-BDF4FB782F | release | PASS |
| S5 | S-TXN-005c | 50 | moderate | escalate | CASE-5D0BEED562 | HOLD-1EF26E0424 | escalate | PASS |
| S8 | S-TXN-008 | 30 | moderate | escalate | CASE-FF3093139D | HOLD-27C732B275 | escalate | PASS |

## Response time (seconds)

Targets: first assessment <= 45 s, continue after reply <= 60 s, total per transaction <= 150 s.

| Scenario | Txn | Assess | Continue | Total | Within target |
|---|---|---|---|---|---|
| S1 | S-TXN-001 | 16 | - | 16 | yes |
| S2 | S-TXN-002 | 25 | 16 | 45 | yes |
| S5 | S-TXN-005a | 25 | 18 | 48 | yes |
| S5 | S-TXN-005b | 28 | 30 | 63 | yes |
| S5 | S-TXN-005c | 25 | 18 | 44 | yes |
| S8 | S-TXN-008 | 71 | 14 | 86 | yes |

## Hand-off integrity (bank records vs scenario)

| Scenario | Txn | Result |
|---|---|---|
| S1 | S-TXN-001 | OK |
| S2 | S-TXN-002 | OK |
| S5 | S-TXN-005a | OK |
| S5 | S-TXN-005b | OK |
| S5 | S-TXN-005c | OK |
| S8 | S-TXN-008 | OK |
