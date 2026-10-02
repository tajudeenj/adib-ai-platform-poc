"""LLMOps evaluation harness: run the agent on a golden set and report the
metrics the AI Review Board signs off at Gate 5. Runs in CI on every change."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.tbml_agent import TBMLAgent  # noqa: E402
from core.bootstrap import build_platform, register_tbml  # noqa: E402
from core.governance import ADVERSE_ACTIONS  # noqa: E402

THRESHOLDS = {"action_accuracy": 0.90, "citation_coverage": 1.0, "hitl_compliance": 1.0, "pii_leak_rate": 0.0}


def run(verbose=True):
    p = build_platform()
    register_tbml(p)
    agent = TBMLAgent(p["registry"], p["tools"], p["gateway"], p["policies"], p["review"])
    golden = json.loads((Path(__file__).parent / "golden_set.json").read_text())
    rows, correct, cited, flags_total, adverse, adverse_with_ticket = [], 0, 0, 0, 0, 0
    for tid, expected in golden.items():
        r = agent.investigate(tid)
        ok = r.action == expected
        correct += ok
        flags_total += len(r.flags)
        cited += sum(1 for c in r.citations.values() if c)
        if r.action in ADVERSE_ACTIONS:
            adverse += 1
            adverse_with_ticket += bool(r.review_ticket)
        rows.append((tid, expected, r.action, r.score, ok))
    calls = p["ledger"].events("llm_call")
    raw_pii_logged = sum(1 for e in p["ledger"].entries if "784-" in json.dumps(e) or "AE07" in json.dumps(e))
    m = {"cases": len(golden),
         "action_accuracy": round(correct / len(golden), 2),
         "citation_coverage": round(cited / flags_total, 2) if flags_total else 1.0,
         "hitl_compliance": round(adverse_with_ticket / adverse, 2) if adverse else 1.0,
         "pii_leak_rate": raw_pii_logged / max(1, len(calls)),
         "pii_items_masked": sum(sum(e["payload"]["pii_masked"].values()) for e in calls),
         "ledger_intact": p["ledger"].verify()[0]}
    passed = all((m[k] >= v) if k != "pii_leak_rate" else (m[k] <= v) for k, v in THRESHOLDS.items())
    if verbose:
        print(f"{'Trade':8} {'Expected':16} {'Agent':16} {'Score':>5}  Result")
        for tid, exp, act, sc, ok in rows:
            print(f"{tid:8} {exp:16} {act:16} {sc:>5}  {'PASS' if ok else 'FAIL'}")
        print("\nMetrics:", json.dumps(m, indent=1))
        print("\nGate 5 (evaluation):", "PASSED" if passed else "FAILED", "- thresholds", THRESHOLDS)
    return m, passed


if __name__ == "__main__":
    _, ok = run()
    sys.exit(0 if ok else 1)
