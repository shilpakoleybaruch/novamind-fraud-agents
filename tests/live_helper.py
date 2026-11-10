#!/usr/bin/env python3
"""Helper for running S5-S8 by hand in the LIVE chat of watsonx Orchestrate.

Usage (from the novamind folder):
  python3 tests/live_helper.py start S5     # reset Dana, print the first message (S5, S6, S7, S8)
  python3 tests/live_helper.py msg S5b      # print the message for one payment (S5a S5b S5c S6 S7 S8)
  python3 tests/live_helper.py reply S5a    # Dana answers the pending question, prints the 'continue' message
  python3 tests/live_helper.py expire S6    # Dana never answers: expire the question, prints 'continue' message
  python3 tests/live_helper.py check S5a    # compare the bank's records with what should have happened
"""
import json, os, sqlite3, sys, urllib.request, urllib.error
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOMER = "C-DANA-001"


def load_env():
    env = {}
    for line in open(os.path.join(ROOT, ".env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.replace("export ", "").strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
BANK = ENV["MOCK_BANK_URL"].rstrip("/")
KEY = ENV["MOCK_BANK_API_KEY"]
DB = os.path.join(ROOT, "data", "mock_bank.db")


def bank(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BANK + path, method=method, data=data,
                                 headers={"X-API-Key": KEY, "Content-Type": "application/json",
                                          "User-Agent": "novamind-test/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def db():
    return sqlite3.connect("file:%s?mode=ro" % DB, uri=True)


SC = json.load(open(os.path.join(ROOT, "data", "scenarios.json")))
TX = {}
for s in SC:
    if "transactions" in s:
        for t, suffix in zip(s["transactions"], "abc"):
            TX["S5" + suffix] = (s, t)
    else:
        TX["S" + s["scenario_id"][1]] = (s, s["transaction"])

EXPECT = {"S5a": "release", "S5b": "release", "S5c": "escalate",
          "S6": "escalate", "S7": "release", "S8": "escalate"}


def message(tid):
    s, t = TX[tid]
    return "New transaction for customer %s, please assess it: %s" % (
        CUSTOMER, json.dumps(t, separators=(",", ":")))


def latest_question(txn_id):
    c = db()
    row = c.execute("select question_id, status from questions where txn_id=? "
                    "order by created_at desc limit 1", (txn_id,)).fetchone()
    c.close()
    return row


def cmd_start(sid):
    first = {"S5": "S5a", "S6": "S6", "S7": "S7", "S8": "S8"}[sid]
    code, out = bank("POST", "/admin/reset/%s" % CUSTOMER, {})
    print("reset:", code)
    if sid == "S7":
        code, out = bank("POST", "/admin/set-thin-baseline/%s" % CUSTOMER, {})
        print("set-thin-baseline:", code)
    c = db()
    n = c.execute("select count(*) from questions where customer_id=? and reply='me' and verified=1 "
                  "and answered_at > datetime('now','-1 day')", (CUSTOMER,)).fetchone()[0]
    c.close()
    print("verified 'me' approvals still counted in the last 24h: %d" % n)
    if sid == "S5" and n:
        print("WARNING: S5 expects 0. Older approvals from earlier tests will make the 2nd payment escalate. Tell Claude.")
    print("\nPaste this into the LIVE chat with risk_agent:\n")
    print(message(first))


def cmd_reply(tid):
    s, t = TX[tid]
    q = latest_question(t["txn_id"])
    if not q:
        sys.exit("No question found for %s. Did the agent ask Dana? Check its reply." % t["txn_id"])
    qid = q[0]
    body = {"reply": s["simulated_reply"], "verified": bool(s["reply_verified"]), "channel": "in_app"}
    if s.get("reply_text"):
        body["reply_text"] = s["reply_text"]
    code, out = bank("POST", "/questions/%s/simulate-reply" % qid, body)
    print("simulate-reply %s -> HTTP %s" % (qid, code))
    if code >= 300:
        sys.exit(out[:200])
    if s["reply_verified"]:
        cont = "Dana has answered question %s (reply: %s, verified). Please continue." % (qid, s["simulated_reply"])
    else:
        cont = "Dana has answered question %s. Please continue." % qid
    print("\nPaste this into the SAME Live chat:\n")
    print(cont)


def cmd_expire(tid):
    s, t = TX[tid]
    q = latest_question(t["txn_id"])
    if not q:
        sys.exit("No question found for %s." % t["txn_id"])
    qid = q[0]
    code, out = bank("POST", "/questions/%s/simulate-expire" % qid, {})
    print("simulate-expire %s -> HTTP %s" % (qid, code))
    if code >= 300:
        sys.exit(out[:200])
    print("\nPaste this into the SAME Live chat:\n")
    print("Question %s has expired with no reply. Please continue." % qid)


def cmd_check(tid):
    s, t = TX[tid]
    txn = t["txn_id"]
    c = db()
    d = c.execute("select decision from risk_decisions where txn_id=? order by created_at desc limit 1", (txn,)).fetchone()
    active = c.execute("select count(*) from holds where txn_id=? and status='active'", (txn,)).fetchone()[0]
    released = c.execute("select count(*) from holds where txn_id=? and status='released'", (txn,)).fetchone()[0]
    case = c.execute("select case_id, status from cases where txn_id=?", (txn,)).fetchone()
    q = c.execute("select question_id, status, reply, verified from questions where txn_id=? "
                  "order by created_at desc limit 1", (txn,)).fetchone()
    audit_n = c.execute("select count(*) from audit_log where txn_id=?", (txn,)).fetchone()[0]
    c.close()
    want = EXPECT[tid]
    decision = d[0] if d else None
    if want == "release":
        ok = decision == "release" and active == 0 and case is None
    else:
        ok = case is not None and released == 0
    line = "%s %s | expected %s | last decision %s | active holds %d | released holds %d | case %s | question %s | audit rows %d" % (
        "PASS" if ok else "FAIL", tid, want, decision, active, released, case, q, audit_n)
    print(line)
    path = os.path.join(ROOT, "tests", "live_scenarios_results.md")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("# S5-S8 on the Live agents (run by hand in the Live chat)\n\n")
        f.write("- %s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), line))
    print("Saved to tests/live_scenarios_results.md")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "start":
        cmd_start(arg)
    elif cmd == "msg":
        print(message(arg))
    elif cmd == "reply":
        cmd_reply(arg)
    elif cmd == "expire":
        cmd_expire(arg)
    elif cmd == "check":
        cmd_check(arg)
    else:
        sys.exit(__doc__)
