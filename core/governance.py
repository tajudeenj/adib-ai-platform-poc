"""Six-gate governance, risk tiering and human-in-the-loop.

Maps to: Six-gate governance (deck), CBUAE Guidance Note on responsible AI (Feb 2026:
human oversight, board accountability, customer right to request human review),
and the Internal Sharia Supervision Committee referral path.
"""
from dataclasses import dataclass, field

GATES = ["intake", "risk_tiering", "data_privacy", "sharia_ethics", "evaluation", "approval"]

TIER_CONTROLS = {
    1: {"label": "Low", "human_approval": False, "citations_required": False, "sharia_review": False},
    2: {"label": "Medium", "human_approval": False, "citations_required": True, "sharia_review": False},
    3: {"label": "High", "human_approval": True, "citations_required": True, "sharia_review": True},
}

# Actions an agent may PROPOSE but never EXECUTE without a named human approver.
ADVERSE_ACTIONS = {"ESCALATE_STR", "HOLD_TRANSACTION", "REFER_SHARIA", "DECLINE"}


class GovernanceError(Exception):
    pass


@dataclass
class UseCase:
    id: str
    name: str
    business_owner: str
    tier: int
    data_classes: list
    granted_scopes: set
    token_budget: int
    gates_passed: list = field(default_factory=list)

    @property
    def status(self):
        if all(g in self.gates_passed for g in GATES):
            return "PRODUCTION"
        if all(g in self.gates_passed for g in GATES[:5]):
            return "PILOT"
        return "BLOCKED"

    @property
    def controls(self):
        return TIER_CONTROLS[self.tier]


class UseCaseRegistry:
    """The AI / model inventory. Nothing runs unless it is registered here."""

    def __init__(self, ledger):
        self.ledger = ledger
        self._items = {}

    def register(self, uc: UseCase, registered_by):
        self._items[uc.id] = uc
        self.ledger.append("usecase_registered", registered_by,
                           {"use_case": uc.id, "tier": uc.tier, "owner": uc.business_owner,
                            "scopes": sorted(uc.granted_scopes)})
        return uc

    def pass_gate(self, uc_id, gate, approver, evidence):
        uc = self.get(uc_id)
        expected = GATES[len(uc.gates_passed)]
        if gate != expected:
            raise GovernanceError(f"Gate order violated: expected '{expected}', got '{gate}'")
        uc.gates_passed.append(gate)
        self.ledger.append("gate_passed", approver, {"use_case": uc_id, "gate": gate, "evidence": evidence})

    def get(self, uc_id):
        if uc_id not in self._items:
            raise GovernanceError(f"Use case '{uc_id}' is not in the AI inventory")
        return self._items[uc_id]

    def require_runnable(self, uc_id):
        uc = self.get(uc_id)
        if uc.status == "BLOCKED":
            missing = [g for g in GATES[:5] if g not in uc.gates_passed]
            raise GovernanceError(f"'{uc_id}' is BLOCKED. Gates outstanding: {missing}")
        return uc


class HumanReviewQueue:
    """Human-in-the-loop. Adverse actions wait here for a named, accountable reviewer."""

    def __init__(self, ledger):
        self.ledger = ledger
        self.items = {}

    def request(self, case_id, proposal, requested_by, reason):
        ticket = f"HR-{len(self.items) + 1:04d}"
        self.items[ticket] = {"case_id": case_id, "proposal": proposal, "status": "PENDING", "reason": reason}
        self.ledger.append("human_review_requested", requested_by,
                           {"ticket": ticket, "case_id": case_id, "proposed_action": proposal, "reason": reason})
        return ticket

    def decide(self, ticket, reviewer, decision, rationale):
        if decision not in {"APPROVED", "REJECTED", "MODIFIED"}:
            raise ValueError("decision must be APPROVED, REJECTED or MODIFIED")
        item = self.items[ticket]
        item.update(status=decision, reviewer=reviewer, rationale=rationale)
        self.ledger.append("human_decision", reviewer,
                           {"ticket": ticket, "case_id": item["case_id"], "decision": decision, "rationale": rationale})
        return item

    def customer_requests_review(self, case_id, customer_ref, channel):
        """CBUAE expectation: a customer can ask for a human to review an AI-assisted decision."""
        return self.request(case_id, "CUSTOMER_REVIEW", f"customer:{customer_ref}",
                            f"Customer requested human review via {channel}")
