#!/usr/bin/env python3
"""Live false-positive test: legitimate but unusual payments through the real risk agent.
Expected: none is held, escalated or released; weak cases clear, stronger ones ask Dana."""
import datetime, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run_orchestrate_scenarios as r

ROOT = r.ROOT
BASE = {"customer_id": "C-DANA-001", "account_id": "ACC-DANA-CHQ-001", "card_id": "CARD-DANA-001",
        "currency": "USD", "city": "Riverside", "country": "US"}

CASES = [
    ("S-TXN-FP1", "New terminal at a known supplier, usual amount and hour", "ask",
     {"merchant_name": "NorthSide Supply", "merchant_id": "M-NS-001", "terminal_id": "NS-T07", "mcc": "5251", "amount": 340.0, "channel": "card_present", "timestamp": "2026-10-20T10:00:00Z"}),
    ("S-TXN-FP2", "Seasonal restock: bigger than usual at a known supplier", "clear",
     {"merchant_name": "GreatPack Packaging", "merchant_id": "M-GP-002", "terminal_id": "GP-T01", "mcc": "5112", "amount": 300.0, "channel": "card_present", "timestamp": "2026-10-20T10:00:00Z"}),
    ("S-TXN-FP3", "New legitimate supplier in a known category, normal amount", "clear",
     {"merchant_name": "Zeta Packaging", "merchant_id": "M-Z-555", "terminal_id": "Z-T1", "mcc": "5112", "amount": 130.0, "channel": "card_present", "timestamp": "2026-10-20T10:00:00Z"}),
    ("S-TXN-FP4", "Early coffee at 5:30 am", "clear",
     {"merchant_name": "Corner Brew Coffee", "merchant_id": "M-CB-010", "terminal_id": "CB-T01", "mcc": "5812", "amount": 7.0, "channel": "card_present", "timestamp": "2026-10-20T05:30:00Z"}),
    ("S-TXN-FP5", "Late grocery run at 10 pm", "clear",
     {"merchant_name": "FreshMart Grocery", "merchant_id": "M-FM-012", "terminal_id": "FM-T01", "mcc": "5411", "amount": 45.0, "channel": "card_present", "timestamp": "2026-10-20T22:00:00Z"}),
    ("S-TXN-FP6", "New shop in a new category, small amount", "ask",
     {"merchant_name": "Quartz Salon", "merchant_id": "M-Q-300", "terminal_id": "Q-T1", "mcc": "7230", "amount": 60.0, "channel": "card_present", "timestamp": "2026-10-20T11:00:00Z"}),
    ("S-TXN-FP7", "New terminal at a known supplier, larger restock", "ask",
     {"merchant_name": "NorthSide Supply", "merchant_id": "M-NS-001", "terminal_id": "NS-T08", "mcc": "5251", "amount": 500.0, "channel": "card_present", "timestamp": "2026-10-20T10:00:00Z"}),
    ("S-TXN-FP8", "Online order from a US supplier she already uses", "clear",
     {"merchant_name": "GreatPack Packaging", "merchant_id": "M-GP-002", "terminal_id": "GP-T01", "mcc": "5112", "amount": 140.0, "channel": "card_not_present", "timestamp": "2026-10-20T10:00:00Z"}),
]


def main():
    print("reset:", r.bank("POST", "/admin/reset/C-DANA-001")[0], flush=True)
    marks = r.db_marks()
    b = r.Chat("baseline_agent", "Call compute_baseline for customer_id C-DANA-001. Do not summarize. Paste the raw tool output.")
    print("baseline ok:", '"ok": true' in r.agent_text(b.first), flush=True)
    b.close()
    rows = []
    for txn_id, label, expected, fields in CASES:
        txn = dict(BASE, txn_id=txn_id, **fields)
        msg = "New transaction for customer C-DANA-001, please assess it: " + json.dumps(txn, separators=(",", ":"))
        t0 = time.time()
        ch = r.Chat("risk_agent", msg)
        secs = time.time() - t0
        txt = r.agent_text(ch.first)
        ch.close()
        res = r.parse(txt)
        got = res.get("branch")
        if got is None and ("pending" in txt.lower() or r.find_qid(txt)):
            got = "ask"
        iss = r.handoff_issues(txn_id, marks)
        ok = got == expected and not iss
        rows.append((label, expected, got or "(none)", res.get("score") or "-", "%d" % secs,
                     "OK" if not iss else "; ".join(iss), "PASS" if ok else "FAIL"))
        print("%s %-58s expected %-5s got %-9s score %s, %d s, handoff %s -> %s" % (
            txn_id, label[:58], expected, got, res.get("score"), secs, "OK" if not iss else "ISSUES", "PASS" if ok else "FAIL"), flush=True)
    passed = sum(1 for x in rows if x[6] == "PASS")
    lines = ["# Live false-positive test (real agents)", "", "Run: %s" % datetime.date.today(), "",
             "Legitimate but unusual payments sent to the risk agent. Expected: weak cases clear, stronger ones ask Dana, none is held, escalated or released.",
             "", "| Payment | Expected | Actual | Score | Seconds | Hand-off | Result |", "|---|---|---|---|---|---|---|"]
    lines += ["| %s |" % " | ".join(x) for x in rows]
    lines += ["", "%d of %d as expected. Payments that ask Dana leave a pending question (no block)." % (passed, len(rows))]
    (ROOT / "tests" / "live_false_positive_results.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()