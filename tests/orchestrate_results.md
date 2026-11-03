# Orchestrate scenario results (live agents)

Run: 2026-11-03

| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |
|---|---|---|---|---|---|---|---|---|
| S1 | S-TXN-001 | 0 | low | clear | None | None | clear | PASS |
| S2 | S-TXN-002 | 30 | moderate | release | None | None | release | PASS |
| S3 | S-TXN-003 | 30 | moderate | escalate | CASE-CB7FE5B8B2 | HOLD-B31A05FD74 | escalate | PASS |
| S4 | S-TXN-004 | 80 | high | escalate | CASE-A71431176D | HOLD-6041C81E10 | escalate | PASS |
| S5 | S-TXN-005a | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005b | 50 | moderate | release | None | HOLD-7F375413D3 | release | PASS |
| S5 | S-TXN-005c | 50 | moderate | escalate | CASE-26A132E9DE | HOLD-C7E9240EC9 | escalate | PASS |
| S6 | S-TXN-006 | 30 | moderate | escalate | CASE-F44F9F14C1 | HOLD-4BBBF36328 | escalate | PASS |
| S7 | S-TXN-007 | 35 | moderate | release | None | None | release | PASS |
| S8 | S-TXN-008 | 30 | moderate | escalate | CASE-AD73008702 | HOLD-F63A2BA6E1 | escalate | PASS |

## Response time (seconds)

Targets: first assessment <= 45 s, continue after reply <= 60 s, total per transaction <= 150 s.

| Scenario | Txn | Assess | Continue | Total | Within target |
|---|---|---|---|---|---|
| S1 | S-TXN-001 | 18 | - | 18 | yes |
| S2 | S-TXN-002 | 21 | 21 | 42 | yes |
| S3 | S-TXN-003 | 20 | 13 | 33 | yes |
| S4 | S-TXN-004 | 20 | - | 21 | yes |
| S5 | S-TXN-005a | 20 | 15 | 36 | yes |
| S5 | S-TXN-005b | 20 | 18 | 39 | yes |
| S5 | S-TXN-005c | 21 | - | 21 | yes |
| S6 | S-TXN-006 | 21 | 16 | 37 | yes |
| S7 | S-TXN-007 | 21 | 17 | 38 | yes |
| S8 | S-TXN-008 | 21 | 11 | 32 | yes |

## Hand-off integrity (bank records vs scenario)

| Scenario | Txn | Result |
|---|---|---|
| S1 | S-TXN-001 | OK |
| S2 | S-TXN-002 | OK |
| S3 | S-TXN-003 | OK |
| S4 | S-TXN-004 | OK |
| S5 | S-TXN-005a | OK |
| S5 | S-TXN-005b | OK |
| S5 | S-TXN-005c | OK |
| S6 | S-TXN-006 | OK |
| S7 | S-TXN-007 | OK |
| S8 | S-TXN-008 | OK |
