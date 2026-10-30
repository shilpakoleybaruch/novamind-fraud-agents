# False-positive test (replay of Dana's history)

Run: 2026-10-30

Data: 352 synthetic transactions for C-DANA-001 (2026-04-20 to 2026-10-19), treated as legitimate. First 246 form the starting history; the latest 106 are scored one by one with the real baseline and scoring code (no LLM, no bank).

| Mode | Scored | Cleared | Asked Dana (moderate) | Held (high) | False-positive rate |
|---|---|---|---|---|---|
| Frozen baseline (never learns) | 106 | 106 | 0 | 0 | 0.0% |
| Learning baseline (adds each earlier txn) | 106 | 106 | 0 | 0 | 0.0% |

## Why transactions were flagged (frozen mode)

Nothing was flagged.

## Why transactions were flagged (learning mode)

Nothing was flagged.

## Sanity check: made-up fraud patterns (should NOT be cleared)

| Pattern | Signals | Score | Level | Caught |
|---|---|---|---|---|
| Overseas card-not-present at a brand-new merchant, 3 am | new_merchant, card_not_present_overseas | 80 | high | yes |
| Very large amount at a known supplier (velocity) | amount_above_p90, velocity_spike | 65 | moderate | yes |
| New terminal at a known shop, 3 am, large amount | new_terminal_known_merchant, amount_above_p90, unusual_hour | 70 | high | yes |
| New merchant in a known category, large card-present amount | new_merchant_known_category, amount_above_p90 | 40 | moderate | yes |
| Overseas card-not-present at a known merchant | card_not_present_overseas | 50 | moderate | yes |

## Legitimate but unusual payments (what the customer would experience)

| Payment | Signals | Score | Outcome |
|---|---|---|---|
| New terminal at a known supplier, usual amount and hour | new_terminal_known_merchant | 30 | asks Dana (no block) |
| Seasonal restock: bigger than usual at a known supplier | amount_above_p90 | 20 | cleared |
| New legitimate supplier in a known category, normal amount | new_merchant_known_category | 20 | cleared |
| Early coffee, 5:30 am (outside her usual hours) | unusual_hour | 20 | cleared |
| Late grocery run, 10 pm | unusual_hour | 20 | cleared |
| New shop in a new category, small amount | new_merchant | 30 | asks Dana (no block) |
| New terminal at a known supplier, larger restock | new_terminal_known_merchant | 30 | asks Dana (no block) |
| Online order from a US supplier she already uses | none | 0 | cleared |

Caught 5 of 5 made-up patterns.

Limits: the history is synthetic and assumed legitimate; the fraud patterns are illustrative, not real attack data. The test measures the rules, not real-world accuracy.
