#!/usr/bin/env python3
"""Mentor point 1: Dana must not see 'Resolved' until the bank has actually released the hold.
Runs two real journeys through the Orchestrate agents (S2 confirm, S3 not-me) and reads
Dana's in-app page at each step."""
import datetime, json, pathlib, sqlite3, sys, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run_orchestrate_scenarios as r

DB = r.ROOT / "data" / "mock_bank.db"
BANK = "http://127.0.0.1:8000"


def _q(sql, args=()):
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def page(qid):
    tok = _q("select page_token from questions where question_id=?", (qid,))[0][0]
    return urllib.request.urlopen("%s/app/question/%s?t=%s" % (BANK, qid, tok), timeout=10).read().decode()


def journey(sid, reply, label):
    data = json.load(open(r.ROOT / "data" / "scenarios.json"))
    s = next(x for x in data if x["scenario_id"].startswith(sid + "_"))
    txn = s["transaction"]
    print("\n=== %s: reset + baseline" % label, flush=True)
    print("reset:", r.bank("POST", "/admin/reset/C-DANA-001")[0], flush=True)
    b = r.Chat("baseline_agent", "Call compute_baseline for customer_id C-DANA-001. Do not summarize. Paste the raw tool output.")
    r.agent_text(b.first); b.close()
    msg = "New transaction for customer C-DANA-001, please assess it: " + json.dumps(txn, separators=(",", ":"))
    ch = r.Chat("risk_agent", msg)
    out = []
    try:
        t = r.agent_text(ch.first)
        qid = r.find_qid(t) or r.find_qid(r.agent_text(ch.say("What is the question_id you sent to Dana for %s? Reply with only the id." % txn["txn_id"])))
        if not qid:
            return [("found the question id", False)]
        code, _ = r.bank("POST", "/questions/%s/simulate-reply" % qid, {"reply": reply, "verified": True, "channel": "in_app"})
        before = page(qid)
        out.append(("Dana tapped; agents have not run yet: page does NOT say 'Resolved'", "Resolved" not in before))
        res = r.parse(r.agent_text(ch.say("Dana has answered question %s (reply: %s, verified). Please continue." % (qid, reply))))
        after = page(qid)
        holds = [h[0] for h in _q("select status from holds where txn_id=?", (txn["txn_id"],))]
        if reply == "me":
            out.append(("agents released: branch is 'release'", res.get("branch") == "release"))
            out.append(("no hold left active in the bank", "active" not in holds))
            out.append(("page now says 'Resolved'", "Resolved" in after))
        else:
            case = res.get("case_id")
            out.append(("agents escalated: branch is 'escalate' with a case", res.get("branch") == "escalate" and bool(case)))
            out.append(("page shows the real case number", bool(case) and case in after))
            out.append(("page does NOT say 'Resolved'", "Resolved" not in after))
        return out
    finally:
        ch.close()


def main():
    rows = []
    only = sys.argv[1:]
    for sid, reply, label in (("S2", "me", "S2 Dana confirms"), ("S3", "not_me", "S3 Dana says not me")):
        if only and sid not in only:
            continue
        for name, ok in journey(sid, reply, label):
            print("  %-4s %s" % ("PASS" if ok else "FAIL", name), flush=True)
            rows.append((label, name, "PASS" if ok else "FAIL"))
    lines = ["# Success message only after the backend finished", "", "Run: %s" % datetime.date.today(), "",
             "| Journey | Check | Result |", "|---|---|---|"] + ["| %s | %s | %s |" % x for x in rows]
    lines += ["", "%d of %d checks passed." % (sum(1 for x in rows if x[2] == "PASS"), len(rows))]
    (r.ROOT / "tests" / "release_before_success_results.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
