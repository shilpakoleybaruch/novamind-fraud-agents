#!/usr/bin/env python3
"""Day-in-the-life test: one continuous day for Dana, no reset between payments.
Checks branches, hand-off records and timing across a realistic sequence."""
import datetime, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run_orchestrate_scenarios as r

BASE = {"customer_id": "C-DANA-001", "account_id": "ACC-DANA-CHQ-001", "card_id": "CARD-DANA-001",
        "currency": "USD", "city": "Riverside", "country": "US", "channel": "card_present"}


def T(day, hour=10):
    return "2026-10-%02dT%02d:00:00Z" % (day, hour)


# (txn_id, what happens, expected branch, Dana's reply, verified, payment fields)
DAY = [
    ("S-TXN-D01", "Morning coffee at the usual place", "clear", None, None,
     {"merchant_name": "Corner Brew Coffee", "merchant_id": "M-CB-010", "terminal_id": "CB-T01", "mcc": "5812", "amount": 7.0, "timestamp": T(21)}),
    ("S-TXN-D02", "Usual packaging order", "clear", None, None,
     {"merchant_name": "GreatPack Packaging", "merchant_id": "M-GP-002", "terminal_id": "GP-T01", "mcc": "5112", "amount": 130.0, "timestamp": T(22)}),
    ("S-TXN-D11", "New cafe, Dana has not answered yet (waits, nothing blocked)", "ask", None, None,
     {"merchant_name": "Juniper Cafe", "merchant_id": "M-JC-302", "terminal_id": "JC-T1", "mcc": "5814", "amount": 18.0, "timestamp": T(20, 11)}),
    ("S-TXN-D03", "New terminal at NorthSide Supply, Dana confirms", "release", "me", True,
     {"merchant_name": "NorthSide Supply", "merchant_id": "M-NS-001", "terminal_id": "NS-T07", "mcc": "5251", "amount": 340.0, "timestamp": T(23)}),
    ("S-TXN-D04", "Same NorthSide terminal again (should now be known)", "clear", None, None,
     {"merchant_name": "NorthSide Supply", "merchant_id": "M-NS-001", "terminal_id": "NS-T07", "mcc": "5251", "amount": 340.0, "timestamp": T(24)}),
    ("S-TXN-D05", "New salon, Dana says it was not her", "escalate", "not_me", True,
     {"merchant_name": "Quartz Salon", "merchant_id": "M-Q-300", "terminal_id": "Q-T1", "mcc": "7230", "amount": 60.0, "timestamp": T(25, 11)}),
    ("S-TXN-D06", "Another new NorthSide terminal, Dana confirms (2nd approval)", "release", "me", True,
     {"merchant_name": "NorthSide Supply", "merchant_id": "M-NS-001", "terminal_id": "NS-T08", "mcc": "5251", "amount": 500.0, "timestamp": T(26)}),
    ("S-TXN-D07", "New GreatPack terminal, Dana confirms (3rd approval in 24 h)", "escalate", "me", True,
     {"merchant_name": "GreatPack Packaging", "merchant_id": "M-GP-002", "terminal_id": "GP-T09", "mcc": "5112", "amount": 130.0, "timestamp": T(27)}),
    ("S-TXN-D08", "Large overseas online payment to an unknown merchant", "escalate", "not_me", True,
     {"merchant_name": "Global Parts Ltd", "merchant_id": "M-X-900", "terminal_id": "X-ONLINE", "mcc": "5251", "amount": 1200.0,
      "channel": "card_not_present", "city": "London", "country": "GB", "timestamp": T(28)}),
    ("S-TXN-D09", "New florist, reply cannot be verified", "escalate", "me", False,
     {"merchant_name": "Maple Florist", "merchant_id": "M-MF-301", "terminal_id": "MF-T1", "mcc": "5992", "amount": 45.0, "timestamp": T(29, 11)}),
    ("S-TXN-D10", "New bakery after three approvals today: goes straight to an analyst", "escalate", None, None,
     {"merchant_name": "Willow Bakery", "merchant_id": "M-WB-303", "terminal_id": "WB-T1", "mcc": "5462", "amount": 22.0, "timestamp": T(30, 11)}),
]


def ok_branch(res, want):
    if want == "ask":
        pending = res.get("qid") or "pending" in str(res).lower()
        return res.get("branch") in (None, "ask") and bool(pending) and not res.get("case_id") and not res.get("hold_id")
    return r.passed(res, want)


def main():
    print("reset:", r.bank("POST", "/admin/reset/C-DANA-001")[0], flush=True)
    marks = r.db_marks()
    b = r.Chat("baseline_agent", "Call compute_baseline for customer_id C-DANA-001. Do not summarize. Paste the raw tool output.")
    print("baseline ok:", '"ok": true' in r.agent_text(b.first), flush=True)
    b.close()
    rows = []
    for txn_id, label, want, reply, verified, fields in DAY:
        txn = dict(BASE, txn_id=txn_id, **fields)
        t0 = time.time()
        res = r.run_txn(txn, reply, verified, None)
        total = time.time() - t0
        iss = r.handoff_issues(txn_id, marks)
        good = ok_branch(res, want) and not iss
        got = res.get("branch") or ("ask" if ok_branch(res, "ask") else "(none)")
        rows.append((txn_id, label, want, got, str(res.get("score") or "-"), res.get("case_id") or "-",
                     res.get("hold_id") or "-", "%d" % total, "OK" if not iss else "; ".join(iss),
                     "PASS" if good else "FAIL"))
        print("%s %-60s want %-8s got %-8s score %s, %d s, handoff %s -> %s" % (
            txn_id, label[:60], want, got, res.get("score"), total, "OK" if not iss else "ISSUES",
            "PASS" if good else "FAIL"), flush=True)
        if not good:
            print("   reason:", res.get("reason"), "| note:", res.get("note"), flush=True)
    n = sum(1 for x in rows if x[-1] == "PASS")
    lines = ["# Day-in-the-life test (live agents, no reset between payments)", "", "Run: %s" % datetime.date.today(), "",
             "| Payment | What happens | Expected | Actual | Score | Case | Hold | Seconds | Hand-off | Result |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    lines += ["| %s |" % " | ".join(x) for x in rows]
    lines += ["", "%d of %d as expected." % (n, len(rows))]
    (r.ROOT / "tests" / "day_in_the_life_results.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
