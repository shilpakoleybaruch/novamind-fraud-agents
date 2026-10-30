# Day-in-the-life test (live agents, no reset between payments)

Run: 2026-10-30

| Payment | What happens | Expected | Actual | Score | Case | Hold | Seconds | Hand-off | Result |
|---|---|---|---|---|---|---|---|---|---|
| S-TXN-D01 | Morning coffee at the usual place | clear | clear | 20 | - | - | 16 | OK | PASS |
| S-TXN-D02 | Usual packaging order | clear | clear | 0 | - | - | 14 | OK | PASS |
| S-TXN-D11 | New cafe, Dana has not answered yet (waits, nothing blocked) | ask | ask | 30 | - | - | 22 | OK | PASS |
| S-TXN-D03 | New terminal at NorthSide Supply, Dana confirms | release | release | 30 | - | - | 37 | OK | PASS |
| S-TXN-D04 | Same NorthSide terminal again (should now be known) | clear | clear | 0 | - | - | 27 | OK | PASS |
| S-TXN-D05 | New salon, Dana says it was not her | escalate | escalate | 30 | CASE-31371A6C11 | HOLD-AD0DCD902E | 74 | OK | PASS |
| S-TXN-D06 | Another new NorthSide terminal, Dana confirms (2nd approval) | release | release | 30 | - | - | 47 | OK | PASS |
| S-TXN-D07 | New GreatPack terminal, Dana confirms (3rd approval in 24 h) | escalate | escalate | 30 | - | HOLD-24B1A86B9F | 40 | OK | FAIL |
| S-TXN-D08 | Large overseas online payment to an unknown merchant | escalate | escalate | 90 | CASE-601D64BA54 | HOLD-19928E7A66 | 21 | OK | PASS |
| S-TXN-D09 | New florist, reply cannot be verified | escalate | escalate | 0 | CASE-B8F7FA9D71 | HOLD-27A2F01690 | 18 | OK | PASS |
| S-TXN-D10 | New bakery after three approvals today: goes straight to an analyst | escalate | escalate | 30 | CASE-E7EE675154 | HOLD-9B058BFE4A | 21 | OK | PASS |

10 of 11 as expected.
