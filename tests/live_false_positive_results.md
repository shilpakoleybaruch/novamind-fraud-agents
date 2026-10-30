# Live false-positive test (real agents)

Run: 2026-10-30

Legitimate but unusual payments sent to the risk agent. Expected: weak cases clear, stronger ones ask Dana, none is held, escalated or released.

| Payment | Expected | Actual | Score | Seconds | Hand-off | Result |
|---|---|---|---|---|---|---|
| New terminal at a known supplier, usual amount and hour | ask | (none) | - | 0 | no audit rows | FAIL |
| Seasonal restock: bigger than usual at a known supplier | clear | (none) | - | 0 | no audit rows | FAIL |
| New legitimate supplier in a known category, normal amount | clear | (none) | - | 0 | no audit rows | FAIL |
| Early coffee at 5:30 am | clear | (none) | - | 0 | no audit rows | FAIL |
| Late grocery run at 10 pm | clear | (none) | - | 0 | no audit rows | FAIL |
| New shop in a new category, small amount | ask | (none) | - | 0 | no audit rows | FAIL |
| New terminal at a known supplier, larger restock | ask | (none) | - | 0 | no audit rows | FAIL |
| Online order from a US supplier she already uses | clear | (none) | - | 0 | no audit rows | FAIL |

0 of 8 as expected. Payments that ask Dana leave a pending question (no block).
