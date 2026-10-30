# Day-in-the-life test (live agents, no reset between payments)

Run: 2026-10-30

| Payment | What happens | Expected | Actual | Score | Case | Hold | Seconds | Hand-off | Result |
|---|---|---|---|---|---|---|---|---|---|
| S-TXN-D01 | Morning coffee at the usual place | clear | clear | 20 | - | - | 15 | OK | PASS |
| S-TXN-D02 | Usual packaging order | clear | clear | 0 | - | - | 13 | OK | PASS |
| S-TXN-D11 | New cafe, Dana has not answered yet (waits, nothing blocked) | ask | ask | 30 | - | - | 18 | OK | PASS |
| S-TXN-D03 | New terminal at NorthSide Supply, Dana confirms | release | release | 30 | - | - | 39 | OK | PASS |
| S-TXN-D04 | Same NorthSide terminal again (should now be known) | clear | clear | 0 | - | - | 14 | OK | PASS |
| S-TXN-D05 | New salon, Dana says it was not her | escalate | escalate | 30 | CASE-887D22F879 | HOLD-B6CBDBA6D8 | 37 | OK | PASS |
| S-TXN-D06 | Another new NorthSide terminal, Dana confirms (2nd approval) | release | release | 30 | - | - | 33 | OK | PASS |
| S-TXN-D07 | New GreatPack terminal, Dana confirms (3rd approval in 24 h) | escalate | escalate | 30 | CASE-A29FCD7CF3 | HOLD-B6922826B0 | 39 | OK | PASS |
| S-TXN-D08 | Large overseas online payment to an unknown merchant | escalate | escalate | 90 | CASE-0CADF22FFF | HOLD-DDE4C68DF3 | 19 | OK | PASS |
| S-TXN-D09 | New florist, reply cannot be verified | escalate | escalate | 30 | CASE-8D975392F0 | HOLD-B94D417696 | 27 | OK | PASS |
| S-TXN-D10 | New bakery after three approvals today: goes straight to an analyst | escalate | escalate | 30 | CASE-332016B941 | HOLD-0EB8448C2E | 19 | OK | PASS |

11 of 11 as expected.
