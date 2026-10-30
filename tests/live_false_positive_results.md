# Live false-positive test (real agents)

Run: 2026-10-30

Legitimate but unusual payments sent to the risk agent. Expected: weak cases clear, stronger ones ask Dana, none is held, escalated or released.

| Payment | Expected | Actual | Score | Seconds | Hand-off | Result |
|---|---|---|---|---|---|---|
| New terminal at a known supplier, usual amount and hour | ask | ask | 30 | 18 | OK | PASS |
| Seasonal restock: bigger than usual at a known supplier | clear | clear | 20 | 16 | OK | PASS |
| New legitimate supplier in a known category, normal amount | clear | clear | 20 | 15 | OK | PASS |
| Early coffee at 5:30 am | clear | clear | 20 | 16 | OK | PASS |
| Late grocery run at 10 pm | clear | clear | 20 | 15 | OK | PASS |
| New shop in a new category, small amount | ask | ask | 30 | 27 | OK | PASS |
| New terminal at a known supplier, larger restock | ask | ask | 30 | 18 | OK | PASS |
| Online order from a US supplier she already uses | clear | clear | 0 | 14 | OK | PASS |

8 of 8 as expected. Payments that ask Dana leave a pending question (no block).
