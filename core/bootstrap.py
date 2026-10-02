"""Wires the platform services together - the 'shared platform' every use case reuses."""
from core.gateway import AIGateway
from core.governance import UseCase, UseCaseRegistry, HumanReviewQueue, GATES
from core.ledger import AuditLedger
from core.rag import PolicyIndex
from core.tools import build_default_tools


def build_platform(ledger_path=None):
    ledger = AuditLedger(ledger_path)
    registry = UseCaseRegistry(ledger)
    return {"ledger": ledger, "registry": registry, "tools": build_default_tools(ledger),
            "gateway": AIGateway(registry, ledger), "policies": PolicyIndex(),
            "review": HumanReviewQueue(ledger)}


def register_tbml(p, pass_gates=True):
    uc = UseCase(id="UC-TBML-001", name="TBML Investigation Agent", business_owner="Head of Trade Finance Compliance",
                 tier=3, data_classes=["customer", "transaction", "trade documents"],
                 granted_scopes={"trade:read", "screening:read", "pricing:read", "risk:read"}, token_budget=20000)
    p["registry"].register(uc, "chief-ai-office")
    if pass_gates:
        evidence = {"intake": "Value case: investigation cycle time", "risk_tiering": "Tier 3: regulatory outcome",
                    "data_privacy": "DPO sign-off, UAE-hosted, PII masked", "sharia_ethics": "ISSC referral path agreed",
                    "evaluation": "Golden-set evals passed"}
        approvers = {"intake": "business-owner", "risk_tiering": "ai-review-board", "data_privacy": "dpo",
                     "sharia_ethics": "sharia-coordination", "evaluation": "model-risk"}
        for g in GATES[:5]:
            p["registry"].pass_gate(uc.id, g, approvers[g], evidence[g])
    return uc
