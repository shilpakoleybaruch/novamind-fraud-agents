#!/usr/bin/env python3
"""Failure / fallback test on the live agents. Interactive: you stop and restart the bank."""
import datetime, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run_orchestrate_scenarios as r

ROOT = r.ROOT


def txn_of(prefix):
    d = json.load(open(ROOT / "data" / "scenarios.json"))
    if isinstance(d, dict):
        d = d.get("scenarios") or list(d.values())
    s = [x for x in d if x.get("scenario_id", "").startswith(prefix)][0]
    return (s.get("transactions") or [s.get("transaction")])[0]


def bank_up():
    try:
        code, _ = r.bank("GET", "/customers/C-DANA-001/baseline")
        return code == 200
    except Exception:
        return False


def assess(txn):
    msg = "New transaction for customer C-DANA-001, please assess it: " + json.dumps(txn, separators=(",", ":"))
    t0 = time.time()
    ch = r.Chat("risk_agent", msg)
    secs = time.time() - t0
    txt = r.agent_text(ch.first)
    ch.close()
    return r.parse(txt), txt, secs


def baseline():
    b = r.Chat("baseline_agent", "Call compute_baseline for customer_id C-DANA-001. Do not summarize. Paste the raw tool output.")
    ok = '"ok": true' in r.agent_text(b.first)
    b.close()
    return ok


def main():
    s1, s2 = txn_of("S1"), txn_of("S2")
    assert bank_up(), "The bank is not reachable. Start it (and the tunnel) first."
    print("reset:", r.bank("POST", "/admin/reset/C-DANA-001")[0])
    print("baseline built:", baseline())
    input("\nSTEP 1: go to Terminal 1 (the bank) and press Ctrl+C to stop it. Then press Enter here... ")
    if bank_up():
        print("The bank still answers. Stop it first, then rerun.")
        return
    rows = []
    for label, txn in (("Bank down: normal purchase (S1)", s1), ("Bank down: unusual purchase (S2)", s2)):
        print("\n---", label, flush=True)
        res, txt, secs = assess(txn)
        safe = res.get("branch") not in ("clear", "release")
        rows.append((label, "not cleared or released", res.get("branch") or "(no JSON)", "%d" % secs,
                     "PASS" if safe else "FAIL", txt[:200].replace("|", "/")))
        print("   branch %s, %d s -> %s" % (res.get("branch"), secs, "PASS" if safe else "FAIL"))
        print("   agent said:", txt[:200])
    input("\nSTEP 2: restart the bank in Terminal 1 (press the up arrow, then Enter). Wait for 'Uvicorn running', then press Enter here... ")
    for _ in range(15):
        if bank_up():
            break
        time.sleep(2)
    else:
        print("The bank is still not reachable; recovery test skipped.")
    if bank_up():
        print("\n--- Recovery", flush=True)
        r.bank("POST", "/admin/reset/C-DANA-001")
        baseline()
        res, txt, secs = assess(s1)
        ok = res.get("branch") == "clear"
        rows.append(("Bank back up: normal purchase (S1)", "clear", res.get("branch") or "(no JSON)", "%d" % secs,
                     "PASS" if ok else "FAIL", txt[:200].replace("|", "/")))
        print("   branch %s, %d s -> %s" % (res.get("branch"), secs, "PASS" if ok else "FAIL"))
    lines = ["# Failure and fallback test (live agents)", "", "Run: %s" % datetime.date.today(), "",
             "| Test | Expected | Actual branch | Seconds | Result | What the agent said |", "|---|---|---|---|---|---|"]
    lines += ["| %s |" % " | ".join(row) for row in rows]
    (ROOT / "tests" / "failure_test_results.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
