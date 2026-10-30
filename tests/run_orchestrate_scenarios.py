#!/usr/bin/env python3
"""Run S1, S2, S5, S8 against the real agents in watsonx Orchestrate (mycloud).
Usage: python3 tests/run_orchestrate_scenarios.py [S1 S2 S5 S8]"""
import datetime, json, os, pathlib, pty, re, select, sqlite3, sys, time
import urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
TURN_TIMEOUT = 240
EXPECTED = {"S1": ["clear"], "S2": ["release"], "S5": ["release", "release", "escalate"], "S8": ["escalate"]}
os.environ["COLUMNS"] = "220"
T_ASSESS, T_CONT, T_TOTAL = 45, 60, 150  # target seconds


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
BANK = ENV["MOCK_BANK_URL"].rstrip("/")
KEY = ENV["MOCK_BANK_API_KEY"]


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


class Chat:
    def __init__(self, agent, first_msg):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvp("orchestrate", ["orchestrate", "chat", "ask", "--agent-name", agent, first_msg])
        self.first = self._read()

    def _read(self):
        buf, end = "", time.time() + TURN_TIMEOUT
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 1)
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                buf += data.decode("utf-8", "ignore")
                clean = ANSI.sub("", buf).replace("\r", "")
                if "You:" in clean or "[ERROR]" in clean:
                    break
        return ANSI.sub("", buf).replace("\r", "")

    def say(self, msg):
        os.write(self.fd, (msg + "\n").encode())
        return self._read()

    def close(self):
        try:
            os.kill(self.pid, 9)
        except Exception:
            pass
        try:
            os.close(self.fd)
        except Exception:
            pass
        for _ in range(25):
            try:
                done, _s = os.waitpid(self.pid, os.WNOHANG)
                if done:
                    break
            except Exception:
                break
            time.sleep(0.2)


def agent_text(raw):
    seg = raw.split("🤖")[-1] if "🤖" in raw else raw
    lines = []
    for l in seg.splitlines():
        l = l.strip().strip("│╭╮╰╯─").strip()
        if l and "You:" not in l:
            lines.append(l)
    return " ".join(lines)


def field(txt, name):
    found = re.findall(r'"%s"\s*:\s*(?:"([^"]*)"|(null)|([\w.\-]+))' % name, txt)
    if not found:
        return None
    s, null, other = found[-1]
    return None if null else (s or other)


def parse(txt):
    return {k: field(txt, k) for k in ("txn_id", "score", "level", "branch", "case_id", "hold_id", "reason")} | {"raw": txt[:300]}


def find_qid(txt):
    m = re.findall(r"Q-[0-9A-F]{10}", txt)
    return m[-1] if m else None


def run_txn(txn, reply, verified, reply_text):
    msg = "New transaction for customer C-DANA-001, please assess it: " + json.dumps(txn, separators=(",", ":"))
    t0 = time.time()
    ch = Chat("risk_agent", msg)
    t_assess = time.time() - t0
    try:
        t = agent_text(ch.first)
        res = parse(t)
        res["t_assess"] = t_assess
        if (res["branch"] == "ask" or (res["branch"] is None and (find_qid(t) or "pending" in t.lower()))) and reply:
            qid = find_qid(t)
            if not qid:
                qid = find_qid(agent_text(ch.say("What is the question_id you sent to Dana for %s? Reply with only the id." % txn["txn_id"])))
            if not qid:
                res["note"] = "no question_id"
                return res
            body = {"reply": reply, "verified": bool(verified), "channel": "in_app"}
            if reply_text:
                body["reply_text"] = reply_text
            code, out = bank("POST", "/questions/%s/simulate-reply" % qid, body)
            if code >= 300:
                res["note"] = "simulate-reply %s %s" % (code, out[:120])
                return res
            cont = ("Dana has answered question %s (reply: %s, verified). Please continue." % (qid, reply)
                    if verified else "Dana has answered question %s. Please continue." % qid)
            t1 = time.time()
            res = parse(agent_text(ch.say(cont)))
            res["qid"] = qid
            res["t_assess"] = t_assess
            res["t_continue"] = time.time() - t1
        return res
    finally:
        ch.close()


def db_marks():
    """Highest row number per table, so the check only sees rows from this run."""
    out = {}
    try:
        db = sqlite3.connect("file:%s?mode=ro" % (ROOT / "data" / "mock_bank.db"), uri=True)
        for t in ("risk_decisions", "questions", "holds", "cases", "audit_log"):
            out[t] = db.execute("select coalesce(max(rowid),0) from %s" % t).fetchone()[0]
        db.close()
    except Exception:
        pass
    return out


def handoff_issues(txn_id, marks=None, customer="C-DANA-001"):
    """Read the bank's own records for one transaction and flag lost or wrong info."""
    issues = []
    fl = lambda t: " and rowid > %d" % (marks or {}).get(t, 0)
    try:
        db = sqlite3.connect("file:%s?mode=ro" % (ROOT / "data" / "mock_bank.db"), uri=True)
        cols = {}
        for (name,) in db.execute("select name from sqlite_master where type='table'"):
            cols[name] = [r[1] for r in db.execute("pragma table_info(%s)" % name)]
        decisions = set()
        rd = cols.get("risk_decisions", [])
        if "authorization_id" in rd and "txn_id" in rd:
            decisions = {r[0] for r in db.execute("select authorization_id from risk_decisions where txn_id=?" + fl("risk_decisions"), (txn_id,))}
        for tname in ("risk_decisions", "questions", "holds", "cases"):
            c = cols.get(tname, [])
            if "txn_id" not in c:
                continue
            if "customer_id" in c:
                for (cust,) in db.execute("select distinct customer_id from %s where txn_id=?%s" % (tname, fl(tname)), (txn_id,)):
                    if cust != customer:
                        issues.append("%s.customer_id=%s" % (tname, cust))
            if tname in ("holds", "cases") and "authorization_id" in c and decisions:
                for (a,) in db.execute("select authorization_id from %s where txn_id=?%s" % (tname, fl(tname)), (txn_id,)):
                    if a not in decisions:
                        issues.append("%s uses unknown authorization" % tname)
        if db.execute("select count(*) from audit_log where txn_id=?" + fl("audit_log"), (txn_id,)).fetchone()[0] == 0:
            issues.append("no audit rows")
        db.close()
    except Exception as e:
        issues.append("check error: %s" % e)
    return issues


def passed(res, want):
    b, case = res.get("branch"), res.get("case_id")
    if b != want:
        return False
    if want == "release" and case:
        return False
    if want == "escalate" and not case:
        return False
    return True


def main():
    wanted = sys.argv[1:] or list(EXPECTED)
    data = json.load(open(ROOT / "data" / "scenarios.json"))
    if isinstance(data, dict):
        data = data.get("scenarios") or list(data.values())
    rows = []
    extra = []
    for s in data:
        sid = s.get("scenario_id", "").split("_")[0]
        if sid not in wanted or sid not in EXPECTED:
            continue
        print("\n=== %s: reset + baseline" % sid, flush=True)
        print("reset:", bank("POST", "/admin/reset/C-DANA-001")[0], flush=True)
        marks = db_marks()
        b = Chat("baseline_agent", "Call compute_baseline for customer_id C-DANA-001. Do not summarize. Paste the raw tool output.")
        btxt = agent_text(b.first)
        b.close()
        if '"ok": true' not in btxt:
            print("WARNING baseline reply:", btxt[:200], flush=True)
        txns = s.get("transactions") or [s.get("transaction")]
        for i, txn in enumerate(txns):
            print("--- %s %s" % (sid, txn["txn_id"]), flush=True)
            _t = time.time()
            res = run_txn(txn, s.get("simulated_reply"), s.get("reply_verified"), s.get("reply_text"))
            res["t_total"] = time.time() - _t
            want = EXPECTED[sid][i]
            iss = handoff_issues(txn["txn_id"], marks)
            ta, tc, tt = res.get("t_assess"), res.get("t_continue"), res.get("t_total")
            fmt = lambda v: "-" if v is None else "%d" % round(v)
            within = "yes" if tt is not None and tt <= T_TOTAL else "no"
            extra.append({"sid": sid, "txn": txn["txn_id"], "a": fmt(ta), "c": fmt(tc), "t": fmt(tt),
                          "w": within, "h": "OK" if not iss else "; ".join(iss)})
            print("   time: assess %s s, continue %s s, total %s s (target %d) | handoff: %s" % (
                fmt(ta), fmt(tc), fmt(tt), T_TOTAL, "OK" if not iss else "; ".join(iss)), flush=True)
            ok = passed(res, want)
            print("   got %s (score %s, case %s, hold %s) want %s -> %s %s" % (
                res.get("branch"), res.get("score"), res.get("case_id"), res.get("hold_id"), want,
                "PASS" if ok else "FAIL", res.get("note", "")), flush=True)
            print("   reason:", res.get("reason"), flush=True)
            if not ok and not res.get("branch"):
                print("   raw:", res.get("raw"), flush=True)
            rows.append((sid, txn["txn_id"], res.get("score"), res.get("level"), res.get("branch"),
                         res.get("case_id"), res.get("hold_id"), want, ok))
    lines = ["# Orchestrate scenario results (live agents)", "", "Run: %s" % datetime.date.today(), "",
             "| Scenario | Txn | Score | Level | Branch | Case | Hold | Expected | Result |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (*r[:8], "PASS" if r[8] else "FAIL"))
    lines += ["", "## Response time (seconds)", "",
              "Targets: first assessment <= %d s, continue after reply <= %d s, total per transaction <= %d s." % (T_ASSESS, T_CONT, T_TOTAL),
              "", "| Scenario | Txn | Assess | Continue | Total | Within target |", "|---|---|---|---|---|---|"]
    for e in extra:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (e["sid"], e["txn"], e["a"], e["c"], e["t"], e["w"]))
    lines += ["", "## Hand-off integrity (bank records vs scenario)", "", "| Scenario | Txn | Result |", "|---|---|---|"]
    for e in extra:
        lines.append("| %s | %s | %s |" % (e["sid"], e["txn"], e["h"]))
    (ROOT / "tests" / "orchestrate_results.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
