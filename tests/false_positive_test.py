#!/usr/bin/env python3
"""False-positive test: replay Dana's own history through the REAL baseline and
scoring code (no bank, no LLM). Writes tests/false_positive_report.md."""
import collections, datetime, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import scoring  # noqa: E402

SPLIT = 0.7


class FakeResp:
    def __init__(self, d): self._d = d
    def raise_for_status(self): pass
    def json(self): return self._d


class FakeClient:
    def __init__(self, store): self.s = store
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, path, **kw):
        if path.endswith("/baseline"):
            return FakeResp({"data": self.s.get("baseline", {})})
        raise RuntimeError("unexpected GET " + path)
    def put(self, path, json=None, **kw):
        self.s["baseline"] = json["data"]
        return FakeResp({})


def load_ns():
    src = (ROOT / "tools" / "baseline_agent_tools.py").read_text()
    src = src.replace("@tool(expected_credentials=_BANK_CREDS)\n", "")
    ns = {"__name__": "baseline_replay"}
    exec(compile(src, "baseline_agent_tools.py", "exec"), ns)
    return ns


NS = load_ns()


def build(history):
    store = {}
    NS["_client"] = lambda: FakeClient(store)
    NS["_fetch_history"] = lambda cid, days=180: {"ok": True, "transactions": [dict(t) for t in history]}
    out = NS["compute_baseline"]("C-DANA-001", force=True)
    assert out.get("ok"), out
    return store["baseline"]


def score(baseline, txn):
    store = {"baseline": baseline}
    NS["_client"] = lambda: FakeClient(store)
    r = NS["compare_to_baseline"]("C-DANA-001", txn)
    assert r.get("ok"), r
    sc = scoring.score_risk(r["signals"], r["thin_baseline"], 0)
    return [s["name"] for s in r["signals"]], sc["score"], sc["level"]


def main():
    d = json.load(open(ROOT / "data" / "transactions_dana.json"))
    d = d if isinstance(d, list) else d.get("transactions", d)
    d = sorted(d, key=lambda t: t["timestamp"])
    cut = int(len(d) * SPLIT)
    train, test = d[:cut], d[cut:]
    frozen = build(train)
    results = {"frozen": [], "learning": []}
    for i, t in enumerate(test):
        names, sc, lvl = score(frozen, t)
        results["frozen"].append((t, names, sc, lvl))
        names, sc, lvl = score(build(d[:cut + i]), t)
        results["learning"].append((t, names, sc, lvl))

    lines = ["# False-positive test (replay of Dana's history)", "",
             "Run: %s" % datetime.date.today(), "",
             "Data: %d synthetic transactions for C-DANA-001 (%s to %s), treated as legitimate. "
             "First %d form the starting history; the latest %d are scored one by one with the real "
             "baseline and scoring code (no LLM, no bank)." % (
                 len(d), d[0]["timestamp"][:10], d[-1]["timestamp"][:10], len(train), len(test)),
             "", "| Mode | Scored | Cleared | Asked Dana (moderate) | Held (high) | False-positive rate |",
             "|---|---|---|---|---|---|"]
    for mode, label in (("frozen", "Frozen baseline (never learns)"), ("learning", "Learning baseline (adds each earlier txn)")):
        rs = results[mode]
        low = sum(1 for r in rs if r[3] == "low")
        mod = sum(1 for r in rs if r[3] == "moderate")
        hi = sum(1 for r in rs if r[3] == "high")
        lines.append("| %s | %d | %d | %d | %d | %.1f%% |" % (label, len(rs), low, mod, hi, 100.0 * (mod + hi) / len(rs)))
        print("%-45s scored %d  cleared %d  asked %d  held %d  FP rate %.1f%%" % (label, len(rs), low, mod, hi, 100.0 * (mod + hi) / len(rs)))

    for mode, label in (("frozen", "frozen"), ("learning", "learning")):
        flagged = [r for r in results[mode] if r[3] != "low"]
        cnt = collections.Counter(n for r in flagged for n in r[1])
        lines += ["", "## Why transactions were flagged (%s mode)" % label, ""]
        if not flagged:
            lines.append("Nothing was flagged.")
        else:
            lines += ["| Signal | Times |", "|---|---|"] + ["| %s | %d |" % (k, v) for k, v in cnt.most_common()]
            lines += ["", "Examples:", "", "| Date | Merchant | Terminal | Amount | Signals | Score |", "|---|---|---|---|---|---|"]
            for t, names, sc, lvl in flagged[:8]:
                lines.append("| %s | %s | %s | %.2f | %s | %d |" % (
                    t["timestamp"][:16], t["merchant_name"], t["terminal_id"], float(t["amount"]), ", ".join(names), sc))

    full = build(d)
    fraud = [
        ("Overseas card-not-present at a brand-new merchant, 3 am", {"merchant_id": "M-X-900", "terminal_id": "X-T1", "mcc": "5999", "amount": 420.0, "channel": "card_not_present", "country": "RO", "timestamp": "2026-10-20T03:10:00Z"}),
        ("Very large amount at a known supplier (velocity)", {"merchant_id": "M-NS-001", "terminal_id": "NS-T01", "mcc": "5251", "amount": 9000.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T09:00:00Z"}),
        ("New terminal at a known shop, 3 am, large amount", {"merchant_id": "M-FM-012", "terminal_id": "FM-T09", "mcc": "5411", "amount": 400.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T03:00:00Z"}),
        ("New merchant in a known category, large card-present amount", {"merchant_id": "M-Y-777", "terminal_id": "Y-T1", "mcc": "5251", "amount": 650.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T10:00:00Z"}),
        ("Overseas card-not-present at a known merchant", {"merchant_id": "M-GP-002", "terminal_id": "GP-T01", "mcc": "5112", "amount": 120.0, "channel": "card_not_present", "country": "DE", "timestamp": "2026-10-20T10:00:00Z"}),
    ]
    lines += ["", "## Sanity check: made-up fraud patterns (should NOT be cleared)", "",
              "| Pattern | Signals | Score | Level | Caught |", "|---|---|---|---|---|"]
    caught = 0
    for label, t in fraud:
        names, sc, lvl = score(full, t)
        ok = lvl != "low"
        caught += ok
        lines.append("| %s | %s | %d | %s | %s |" % (label, ", ".join(names) or "none", sc, lvl, "yes" if ok else "NO"))
        print("fraud: %-60s %-45s %3d %-8s %s" % (label[:60], ", ".join(names)[:45], sc, lvl, "caught" if ok else "MISSED"))
    odd = [
        ("New terminal at a known supplier, usual amount and hour", {"merchant_id": "M-NS-001", "terminal_id": "NS-T07", "mcc": "5251", "amount": 340.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T10:00:00Z"}),
        ("Seasonal restock: bigger than usual at a known supplier", {"merchant_id": "M-GP-002", "terminal_id": "GP-T01", "mcc": "5112", "amount": 300.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T10:00:00Z"}),
        ("New legitimate supplier in a known category, normal amount", {"merchant_id": "M-Z-555", "terminal_id": "Z-T1", "mcc": "5112", "amount": 130.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T10:00:00Z"}),
        ("Early coffee, 5:30 am (outside her usual hours)", {"merchant_id": "M-CB-010", "terminal_id": "CB-T01", "mcc": "5812", "amount": 7.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T05:30:00Z"}),
        ("Late grocery run, 10 pm", {"merchant_id": "M-FM-012", "terminal_id": "FM-T01", "mcc": "5411", "amount": 45.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T22:00:00Z"}),
        ("New shop in a new category, small amount", {"merchant_id": "M-Q-300", "terminal_id": "Q-T1", "mcc": "7230", "amount": 60.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T11:00:00Z"}),
        ("New terminal at a known supplier, larger restock", {"merchant_id": "M-NS-001", "terminal_id": "NS-T08", "mcc": "5251", "amount": 500.0, "channel": "card_present", "country": "US", "timestamp": "2026-10-20T10:00:00Z"}),
        ("Online order from a US supplier she already uses", {"merchant_id": "M-GP-002", "terminal_id": "GP-T01", "mcc": "5112", "amount": 140.0, "channel": "card_not_present", "country": "US", "timestamp": "2026-10-20T10:00:00Z"}),
    ]
    lines += ["", "## Legitimate but unusual payments (what the customer would experience)", "",
              "| Payment | Signals | Score | Outcome |", "|---|---|---|---|"]
    outcome = {"low": "cleared", "moderate": "asks Dana (no block)", "high": "held"}
    for label, t in odd:
        names, sc, lvl = score(full, t)
        lines.append("| %s | %s | %d | %s |" % (label, ", ".join(names) or "none", sc, outcome[lvl]))
        print("legit-unusual: %-58s %3d %s" % (label[:58], sc, outcome[lvl]))
    lines += ["", "Caught %d of %d made-up patterns." % (caught, len(fraud)),
              "", "Limits: the history is synthetic and assumed legitimate; the fraud patterns are illustrative, "
              "not real attack data. The test measures the rules, not real-world accuracy."]
    (ROOT / "tests" / "false_positive_report.md").write_text("\n".join(lines) + "\n")
    print("wrote tests/false_positive_report.md")


if __name__ == "__main__":
    main()
