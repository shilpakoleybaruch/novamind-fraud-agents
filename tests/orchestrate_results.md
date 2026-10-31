# Orchestrate scenario results (live agents)

Run: 2026-10-30

| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |
|---|---|---|---|---|---|---|---|---|
| S1 | S-TXN-001 | 0 | low | clear | None | None | clear | PASS |
| S2 | S-TXN-002 | 30 | moderate | release | None | None | release | PASS |
| S3 | S-TXN-003 | 30 | moderate | escalate | CASE-95169EB858 | HOLD-73F3FE2038 | escalate | PASS |
| S4 | S-TXN-004 | 80 | high | escalate | CASE-4FEDBAE5C9 | HOLD-4729244B93 | escalate | PASS |
| S5 | S-TXN-005a | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005b | 50 | moderate | release | None | HOLD-782211EEF9 | release | PASS |
| S5 | S-TXN-005c | 50 | moderate | escalate | CASE-8FC20ED80A | HOLD-AA63B11194 | escalate | PASS |
| S6 | S-TXN-006 | 30 | moderate | escalate | CASE-A09CC4FC35 | HOLD-1F28FBBB62 | escalate | PASS |
| S7 | S-TXN-007 | 35 | moderate | release | None | None | release | PASS |
| S8 | S-TXN-008 | 30 | moderate | escalate | CASE-D9DCFD7DC7 | HOLD-1D969476F9 | escalate | PASS |

## Response time (seconds)

Targets: first assessment <= 45 s, continue after reply <= 60 s, total per transaction <= 150 s.

| Scenario | Txn | Assess | Continue | Total | Within target |
|---|---|---|---|---|---|
| S1 | S-TXN-001 | 16 | - | 16 | yes |
| S2 | S-TXN-002 | 18 | 18 | 36 | yes |
| S3 | S-TXN-003 | 18 | 9 | 27 | yes |
| S4 | S-TXN-004 | 20 | - | 20 | yes |
| S5 | S-TXN-005a | 19 | 28 | 48 | yes |
| S5 | S-TXN-005b | 20 | 18 | 38 | yes |
| S5 | S-TXN-005c | 22 | 18 | 41 | yes |
| S6 | S-TXN-006 | 27 | 12 | 39 | yes |
| S7 | S-TXN-007 | 19 | 15 | 35 | yes |
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
