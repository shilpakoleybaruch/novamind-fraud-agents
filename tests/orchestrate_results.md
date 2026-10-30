# Orchestrate scenario results (live agents)

Run: 2026-10-30

| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |
|---|---|---|---|---|---|---|---|---|
| S1 | S-TXN-001 | 0 | low | clear | None | None | clear | PASS |
| S2 | S-TXN-002 | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005a | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005b | 50 | moderate | release | None | HOLD-846410997D | release | PASS |
| S5 | S-TXN-005c | 50 | moderate | escalate | CASE-2EE63C5E31 | HOLD-8079B54125 | escalate | PASS |
| S8 | S-TXN-008 | 30 | moderate | escalate | CASE-6244EC2260 | HOLD-F7DBDA690E | escalate | PASS |

## Response time (seconds)

Targets: first assessment <= 45 s, continue after reply <= 60 s, total per transaction <= 150 s.

| Scenario | Txn | Assess | Continue | Total | Within target |
|---|---|---|---|---|---|
| S1 | S-TXN-001 | 16 | - | 16 | yes |
| S2 | S-TXN-002 | 17 | 17 | 48 | yes |
| S5 | S-TXN-005a | 18 | 20 | 39 | yes |
| S5 | S-TXN-005b | 17 | 17 | 35 | yes |
| S5 | S-TXN-005c | 26 | 18 | 45 | yes |
| S8 | S-TXN-008 | 18 | 13 | 31 | yes |

## Hand-off integrity (bank records vs scenario)

| Scenario | Txn | Result |
|---|---|---|
| S1 | S-TXN-001 | OK |
| S2 | S-TXN-002 | OK |
| S5 | S-TXN-005a | OK |
| S5 | S-TXN-005b | OK |
| S5 | S-TXN-005c | OK |
| S8 | S-TXN-008 | OK |
