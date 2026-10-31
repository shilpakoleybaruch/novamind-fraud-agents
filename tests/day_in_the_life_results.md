# Day-in-the-life test (live agents, no reset between payments)

Run: 2026-10-30

| Payment | What happens | Expected | Actual | Score | Case | Hold | Seconds | Hand-off | Result |
|---|---|---|---|---|---|---|---|---|---|
| S-TXN-D01 | Morning coffee at the usual place | clear | clear | 20 | - | - | 16 | OK | PASS |
| S-TXN-D02 | Usual packaging order | clear | clear | 0 | - | - | 16 | OK | PASS |
| S-TXN-D11 | New cafe, Dana has not answered yet (waits, nothing blocked) | ask | ask | 30 | - | - | 28 | OK | PASS |
| S-TXN-D03 | New terminal at NorthSide Supply, Dana confirms | release | release | 30 | - | - | 31 | OK | PASS |
| S-TXN-D04 | Same NorthSide terminal again (should now be known) | clear | ask | 30 | - | - | 21 | OK | FAIL |
| S-TXN-D05 | New salon, Dana says it was not her | escalate | escalate | 30 | CASE-DFFED2EC26 | HOLD-7761DD9B1F | 28 | OK | PASS |
| S-TXN-D06 | Another new NorthSide terminal, Dana confirms (2nd approval) | release | release | 30 | - | - | 46 | OK | PASS |
| S-TXN-D07 | New GreatPack terminal, Dana confirms (3rd approval in 24 h) | escalate | escalate | 30 | CASE-A0CFCC3174 | HOLD-A02F2655AE | 38 | OK | PASS |
| S-TXN-D08 | Large overseas online payment to an unknown merchant | escalate | escalate | 90 | CASE-E4674F73D9 | HOLD-C90D6E2481 | 18 | OK | PASS |
| S-TXN-D09 | New florist, reply cannot be verified | escalate | escalate | 30 | CASE-5C701DA341 | HOLD-EC5731188A | 29 | OK | PASS |
| S-TXN-D10 | New bakery after three approvals today: goes straight to an analyst | escalate | escalate | 30 | CASE-F0E43742C5 | HOLD-E01AEA2C13 | 23 | OK | PASS |

10 of 11 as expected.
