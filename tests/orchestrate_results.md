# Orchestrate scenario results (live agents)

Run: 2026-10-30

| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |
|---|---|---|---|---|---|---|---|---|
| S1 | S-TXN-001 | 0 | low | clear | None | None | clear | PASS |
| S2 | S-TXN-002 | 30 | moderate | release | None | None | release | PASS |
| S3 | S-TXN-003 | 30 | moderate | escalate | CASE-BDCD244ABF | HOLD-EBCB495C29 | escalate | PASS |
| S4 | S-TXN-004 | 80 | high | escalate | CASE-DB9B3539F7 | HOLD-549596C49F | escalate | PASS |
| S5 | S-TXN-005a | 30 | moderate | release | None | None | release | PASS |
| S5 | S-TXN-005b | 50 | moderate | release | None | HOLD-E3F1D66F39 | release | PASS |
| S5 | S-TXN-005c | 50 | moderate | escalate | CASE-B5D2CEE6DE | HOLD-FC877835A5 | escalate | PASS |
| S6 | S-TXN-006 | 30 | moderate | escalate | CASE-EA4C7EBBF0 | HOLD-0F5185BF6F | escalate | PASS |
| S7 | S-TXN-007 | 35 | moderate | release | None | None | release | PASS |
| S8 | S-TXN-008 | 30 | moderate | escalate | CASE-EA02F8D2FA | HOLD-D5DA274524 | escalate | PASS |

## Response time (seconds)

Targets: first assessment <= 45 s, continue after reply <= 60 s, total per transaction <= 150 s.

| Scenario | Txn | Assess | Continue | Total | Within target |
|---|---|---|---|---|---|
| S1 | S-TXN-001 | 16 | - | 16 | yes |
| S2 | S-TXN-002 | 18 | 16 | 34 | yes |
| S3 | S-TXN-003 | 18 | 8 | 27 | yes |
| S4 | S-TXN-004 | 19 | - | 19 | yes |
| S5 | S-TXN-005a | 23 | 18 | 42 | yes |
| S5 | S-TXN-005b | 33 | 16 | 49 | yes |
| S5 | S-TXN-005c | 21 | 17 | 38 | yes |
| S6 | S-TXN-006 | 18 | 25 | 43 | yes |
| S7 | S-TXN-007 | 17 | 17 | 34 | yes |
| S8 | S-TXN-008 | 22 | 16 | 38 | yes |

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
