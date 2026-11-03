"""Last step of the journey: analyst resolves the latest open case, then we check the bank and Dana's page.
Usage: python3 tests/run_journey.py [fraud_confirmed|legitimate]"""
import glob, os, re, sqlite3, sys, json, urllib.request, urllib.error

outcome = sys.argv[1] if len(sys.argv) > 1 else "fraud_confirmed"
BASE = os.environ["MOCK_BANK_URL"].rstrip("/")
KEY = os.environ["MOCK_BANK_API_KEY"]
src = open("mock_bank/main.py").read()
m = re.search(r'name="([^"]+)"', src[src.find("require_api_key") - 400: src.find("def require_api_key") + 400]) \
    or re.search(r'APIKeyHeader\(name="([^"]+)"', src)
HDR = m.group(1) if m else "X-API-Key"
db_path = os.path.abspath(glob.glob("data/mock_bank.db")[0])
db = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
db.row_factory = sqlite3.Row
tables = [r[0] for r in db.execute("select name from sqlite_master where type='table'")]
qt = next(t for t in tables if t.startswith("question"))
at = next(t for t in tables if t.startswith("audit"))

results = []
def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (" - " + detail if detail else ""))

def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={HDR: KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

case = db.execute("select * from cases where status != 'resolved' order by created_at desc limit 1").fetchone()
if not case:
    sys.exit("No open case found. Run a scenario that ends in a case first (for example the 'not me' one).")
cid, txn = case["case_id"], case["txn_id"]
print("Case", cid, "txn", txn, "outcome", outcome)

hold0 = db.execute("select * from holds where txn_id=? order by created_at desc limit 1", (txn,)).fetchone()
check("hold exists and is active before resolve", bool(hold0) and hold0["status"] == "active")

code, text = call("POST", "/cases/%s/resolve" % cid, {"outcome": outcome, "analyst": "demo-analyst"})
check("resolve call accepted", code == 200, "HTTP %s" % code)

db.close()
db = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
db.row_factory = sqlite3.Row
c2 = db.execute("select * from cases where case_id=?", (cid,)).fetchone()
check("case status resolved with resolved_at", c2["status"] == "resolved" and c2["resolved_at"] is not None)
h2 = db.execute("select * from holds where txn_id=? order by created_at desc limit 1", (txn,)).fetchone()
if outcome == "legitimate":
    check("hold released by analyst", h2["status"] == "released" and "analyst" in (h2["released_by"] or ""))
else:
    check("hold stays active (payment stays blocked)", h2["status"] == "active")
a = db.execute("select count(*) from %s where case_id=? and action='case_resolved'" % at, (cid,)).fetchone()[0]
check("audit trail has case_resolved", a >= 1)

q = db.execute("select * from %s where txn_id=? order by created_at desc limit 1" % qt, (txn,)).fetchone()
if q:
    code, page = call("GET", "/app/question/%s?t=%s" % (q["question_id"], q["page_token"]))
    want = "was yours" if outcome == "legitimate" else "was not yours"
    check("Dana's page shows the final outcome", code == 200 and want in page, "HTTP %s" % code)
else:
    check("Dana's page shows the final outcome", False, "no question row for txn")

with open("tests/journey_results.md", "w") as f:
    f.write("# Journey: analyst resolves case (%s)\n\nCase %s, txn %s\n\n" % (outcome, cid, txn))
    for n, ok, d in results:
        f.write("- %s %s %s\n" % ("PASS" if ok else "FAIL", n, d))
print("\n%d/%d passed. Saved tests/journey_results.md" % (sum(1 for r in results if r[1]), len(results)))
