"""End-to-end demo of the ADIB Enterprise AI platform pattern.
Run:  python demo.py      (no installs, no API keys, synthetic data only)
"""
import json
import textwrap

from agents.tbml_agent import TBMLAgent
from core.bootstrap import build_platform, register_tbml
from core.gateway import mask_pii
from core.governance import GovernanceError
from evals.run_evals import run as run_evals


def step(n, title):
    print(f"\n{'=' * 78}\n STEP {n}: {title}\n{'=' * 78}")


p = build_platform(ledger_path="audit_ledger.jsonl")
agent = TBMLAgent(p["registry"], p["tools"], p["gateway"], p["policies"], p["review"])

step(1, "Governance first - an unapproved use case cannot run")
register_tbml(p, pass_gates=False)
try:
    agent.investigate("T-1003")
except GovernanceError as e:
    print(" BLOCKED:", e)
from core.governance import GATES  # noqa: E402
ev = {"intake": "Value case: investigation cycle time", "risk_tiering": "Tier 3: regulatory outcome",
      "data_privacy": "DPO sign-off, UAE-hosted, PII masked", "sharia_ethics": "ISSC referral path agreed",
      "evaluation": "Golden-set evals passed"}
for g in GATES[:5]:
    p["registry"].pass_gate("UC-TBML-001", g, "ai-review-board", ev[g])
    print(f" Gate passed: {g:14} -> status {p['registry'].get('UC-TBML-001').status}")

step(2, "AI Gateway - customer PII never reaches the model")
sample = "CFO Emirates ID 784-1985-1234567-1, IBAN AE070331234567890123456, mobile +971 50 123 4567"
masked, found = mask_pii(sample)
print(" Before:", sample)
print(" After :", masked)
print(" Masked:", found)

step(3, "Investigate a high-risk trade (T-1003)")
r = agent.investigate("T-1003")
print(f" Flags : {r.flags}\n Score : {r.score}/100\n Action: {r.action} (proposed, not executed)")
for f, c in r.citations.items():
    print(f"   {f:24} cited: {c}")
print(" Narrative:", textwrap.fill(r.narrative, 76, subsequent_indent="   "))
print(" Human review ticket:", r.review_ticket)

step(4, "Human-in-the-loop - the investigator decides")
d = p["review"].decide(r.review_ticket, "investigator:fincrime-07", "APPROVED", "Third-party payer and high-risk route confirmed")
print(" Decision:", d["status"], "by", d["reviewer"])

step(5, "Sharia path - Murabaha on prohibited goods (T-1005)")
r5 = agent.investigate("T-1005")
print(f" Action: {r5.action} -> ticket {r5.review_ticket}; cited: {r5.citations['SHARIA_PROHIBITED_GOODS']}")

step(6, "Least privilege - the agent tries to release a payment")
try:
    p["tools"].call(agent.AGENT_ID, p["registry"].get("UC-TBML-001").granted_scopes, "release_payment", trade_id="T-1003")
except PermissionError as e:
    print(" DENIED:", e)

step(7, "CBUAE: customer requests human review of an AI-assisted outcome")
print(" Ticket:", p["review"].customer_requests_review("T-1002", "CUST-88213", "mobile app"))

step(8, "Tamper-evident audit ledger")
ok, _ = p["ledger"].verify()
print(f" {len(p['ledger'].entries)} entries, chain intact: {ok}")
victim = p["ledger"].events("human_decision")[0]
victim["payload"]["decision"] = "REJECTED"   # someone edits history...
ok, seq = p["ledger"].verify()
print(f" After editing entry #{victim['seq']}: intact={ok}, first broken entry=#{seq}")
victim["payload"]["decision"] = "APPROVED"

step(9, "Gate 5 evaluation on the golden set")
run_evals()
print("\nAudit trail written to audit_ledger.jsonl")
