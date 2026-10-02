"""TBML Investigation Agent - the lighthouse use case.

Flow: read trade -> screen parties and vessel -> price, route, payer and goods checks
-> Sharia check -> retrieve policy with citations -> LLM narrative via the gateway
-> propose action -> adverse actions go to a human reviewer. The agent never executes
an adverse action itself.
"""
from dataclasses import dataclass, field

from core.governance import ADVERSE_ACTIONS

WEIGHTS = {"SANCTIONS_MATCH": 100, "OVER_INVOICING": 35, "UNDER_INVOICING": 35, "VAGUE_GOODS": 25,
           "HIGH_RISK_JURISDICTION": 30, "MULTIPLE_TRANSSHIPMENT": 15, "THIRD_PARTY_PAYMENT": 25}
POLICY_QUERY = {"SANCTIONS_MATCH": "sanctions watchlist match vessel party hold escalate",
                "OVER_INVOICING": "over invoicing unit price above market range",
                "UNDER_INVOICING": "under invoicing unit price below market range",
                "VAGUE_GOODS": "vague goods description general goods various items",
                "HIGH_RISK_JURISDICTION": "high-risk jurisdictions routing",
                "MULTIPLE_TRANSSHIPMENT": "multiple transshipment points",
                "THIRD_PARTY_PAYMENT": "third-party payments payer not applicant",
                "SHARIA_PROHIBITED_GOODS": "prohibited goods alcoholic beverages murabaha sharia"}
SHARIA_PROHIBITED = {"alcoholic_beverages", "pork_products", "gambling_equipment", "tobacco"}
VAGUE_TERMS = ("general goods", "various items", "assorted", "miscellaneous")


@dataclass
class CaseResult:
    trade_id: str
    flags: list = field(default_factory=list)
    score: int = 0
    action: str = "CLEAR"
    citations: dict = field(default_factory=dict)
    narrative: str = ""
    review_ticket: str = None


class TBMLAgent:
    AGENT_ID = "agent:tbml-investigator-v1"
    USE_CASE = "UC-TBML-001"

    def __init__(self, registry, tools, gateway, policies, review_queue):
        self.registry, self.tools, self.gateway = registry, tools, gateway
        self.policies, self.review = policies, review_queue

    def _call(self, tool, **kw):
        scopes = self.registry.get(self.USE_CASE).granted_scopes
        return self.tools.call(self.AGENT_ID, scopes, tool, **kw)

    def investigate(self, trade_id):
        self.registry.require_runnable(self.USE_CASE)
        t = self._call("get_trade", trade_id=trade_id)
        r = CaseResult(trade_id)
        details = []

        for party in (t["applicant"], t["beneficiary"], t["payer"]):
            for hit in self._call("screen_name", name=party, kind="entity"):
                r.flags.append("SANCTIONS_MATCH"); details.append(f"{party} matches {hit['matched']} ({hit['list']}, {hit['score']})")
        for hit in self._call("screen_name", name=t["vessel"], kind="vessel"):
            r.flags.append("SANCTIONS_MATCH"); details.append(f"Vessel {t['vessel']} matches {hit['matched']} ({hit['list']}, {hit['score']})")

        if any(term in t["description"].lower() for term in VAGUE_TERMS):
            r.flags.append("VAGUE_GOODS"); details.append(f"Goods described only as '{t['description']}'")
        else:
            rng = self._call("price_benchmark", commodity=t["commodity"])
            if rng:
                lo, hi = rng
                p = t["unit_price_usd"]
                if p > hi * 1.25:
                    r.flags.append("OVER_INVOICING"); details.append(f"Unit price USD {p} vs benchmark {lo}-{hi}")
                elif p < lo * 0.75:
                    r.flags.append("UNDER_INVOICING"); details.append(f"Unit price USD {p} vs benchmark {lo}-{hi}")

        risky = [c for c in t["route"] if self._call("jurisdiction_risk", country=c) == "HIGH"]
        if risky:
            r.flags.append("HIGH_RISK_JURISDICTION"); details.append(f"Route includes high-risk jurisdiction(s): {', '.join(risky)}")
        if len(t["route"]) - 2 >= 2:
            r.flags.append("MULTIPLE_TRANSSHIPMENT"); details.append(f"{len(t['route']) - 2} transshipment points: {' > '.join(t['route'])}")
        if t["payer"] != t["applicant"]:
            r.flags.append("THIRD_PARTY_PAYMENT"); details.append(f"Payer {t['payer']} is not the applicant {t['applicant']}")

        sharia_issue = t["product"] == "Murabaha" and t["commodity"] in SHARIA_PROHIBITED
        if sharia_issue:
            r.flags.append("SHARIA_PROHIBITED_GOODS"); details.append(f"Murabaha financing of {t['commodity'].replace('_', ' ')}")

        r.flags = list(dict.fromkeys(r.flags))
        r.score = min(100, sum(WEIGHTS.get(f, 0) for f in r.flags))
        for f in r.flags:  # every flag must be grounded in a cited policy section
            hits = self.policies.search(POLICY_QUERY[f], k=1)
            r.citations[f] = hits[0]["citation"] if hits else None

        if r.score >= 70:
            r.action = "ESCALATE_STR"
        elif sharia_issue:
            r.action = "REFER_SHARIA"
        elif r.score >= 35:
            r.action = "ENHANCED_REVIEW"

        prompt = (f"Trade {trade_id} ({t['product']}), applicant contact: {t['applicant_contact']}\n"
                  "Facts:\n" + "\n".join(f"- {d}" for d in details) +
                  f"\nProposed action: {r.action}. Write a short investigator summary.")
        r.narrative, _ = self.gateway.complete(self.USE_CASE, self.AGENT_ID, prompt)

        self.gateway.ledger.append("agent_proposal", self.AGENT_ID, {
            "trade_id": trade_id, "flags": r.flags, "score": r.score, "proposed_action": r.action,
            "citations": r.citations})
        if r.action in ADVERSE_ACTIONS:
            r.review_ticket = self.review.request(trade_id, r.action, self.AGENT_ID,
                                                  f"Adverse action requires human approval (score {r.score})")
        return r
