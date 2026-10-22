# data/ — Synthetic Novamind Data

All data in this directory is **fully synthetic**. No real customer records, bank accounts,
or transactions were used. Names, amounts, merchants, and identifiers were invented for
prototype purposes only.

## How it was generated

Run [`generate.py`](generate.py) from the repo root:

```bash
python3 novamind/data/generate.py
```

The script uses a **fixed random seed (42)**, so re-running it always produces identical output.
It requires only the Python 3 standard library — no extra packages needed.

## Files

| File | Description |
|------|-------------|
| `generate.py` | Source of truth. Edit this to change the data, then re-run. |
| `customer_dana.json` | Single customer record for Dana Reyes (`C-DANA-001`), one business account, one card, and her `essential_payees` list. |
| `transactions_dana.json` | ~360 transactions covering 6 months of history ending yesterday. See spending patterns below. |
| `scenarios.json` | 8 test transactions, one per scenario (S1–S8), each with `expected_branch`, `simulated_reply`, and `reply_verified` fields so the scenario runner can execute without a human in the loop. |

## Spending patterns baked into transactions_dana.json

| Pattern | Detail |
|---------|--------|
| NorthSide Supply card purchase | Every **Tuesday**, $250–$420, terminal `NS-T01` (MCC 5251) |
| NorthSide Supply transfer | Every **Friday**, $800–$1 400 (essential payee) |
| GreatPack Packaging | Every **Monday**, $90–$160, terminal `GP-T01` (MCC 5112) |
| ClearView Glass | **Biweekly Wednesday** (even ISO weeks), $180–$310 (MCC 5251) |
| Metro Fixtures | **Biweekly Thursday** (odd ISO weeks), $120–$220 (MCC 5251) |
| Coffee (Corner Brew) | Most weekday mornings, $4–$9 |
| Fuel (Sunridge Fuel) | ~3× per week, $35–$58 |
| Groceries (FreshMart) | Mon/Wed/Fri afternoons, $18–$58 |
| Rent transfer | **1st of each month**, $2 200 (essential payee, Greenway Properties) |
| Phone bill | **1st of each month**, $75–$90 CNP (Horizon Mobile) |
| Utility bill | **5th of each month**, $120–$200 CNP (City Utilities) |

## Scenario index

| ID | Shape | Expected branch |
|----|-------|-----------------|
| S1_low | $42 at usual grocery store | clear |
| S2_moderate_me | NS Supply Tuesday, new terminal NS-T07; Dana says "me" | ask → release → terminal learned |
| S3_moderate_not_me | Unknown merchant; Dana says "not me" | ask → partial hold → case opened |
| S4_high | CNP overseas electronics at 3am, $1 950 | partial hold → case → analyst queued |
| S5_repeat_approvals | Three moderate txns in 2 hours, all "me" | 3rd approval escalates (edge rule 1) |
| S6_no_reply | Moderate txn, no reply | retry second channel → hold kept → analyst queued |
| S7_thin_baseline | Same as S2 but only 3 weeks of history | ask (threshold lowered to 20, edge rule 3) |
| S8_scam_reply | Reply from unverified channel / prompt injection attempt | not verified → nothing released → escalate |
