"""MCP-style tool layer (ADR-003): agents reach bank systems only through narrow,
scoped tools. Each tool wraps an existing service (in production: an IBM APIC / ESB
or Oracle OIC API). Scope checks are enforced here, not trusted to the agent.

This POC uses an in-process registry so it runs with no dependencies. The same
functions can be exposed as a real MCP server with the official `mcp` Python SDK
(see README) without changing the agent logic.
"""
import json
from difflib import SequenceMatcher
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


class ToolRegistry:
    def __init__(self, ledger):
        self.ledger = ledger
        self._tools = {}

    def register(self, name, scope, fn, description):
        self._tools[name] = {"scope": scope, "fn": fn, "description": description}

    def catalogue(self):
        return {n: {"scope": t["scope"], "description": t["description"]} for n, t in self._tools.items()}

    def call(self, agent_id, granted_scopes, tool_name, **kwargs):
        name = tool_name
        tool = self._tools[name]
        if tool["scope"] not in granted_scopes:
            self.ledger.append("tool_denied", agent_id, {"tool": name, "required_scope": tool["scope"]})
            raise PermissionError(f"{agent_id} lacks scope '{tool['scope']}' for tool '{name}'")
        result = tool["fn"](**kwargs)
        self.ledger.append("tool_call", agent_id, {"tool": name, "args": kwargs})
        return result


# ---- Tool implementations over SYNTHETIC data (stand-ins for real bank APIs) ----
def _load(name):
    return json.loads((DATA / name).read_text())


def get_trade(trade_id):
    """Stand-in for the trade finance system API (LC / collections)."""
    return next(t for t in _load("trades_synthetic.json") if t["trade_id"] == trade_id)


def screen_name(name, kind="entity"):
    """Stand-in for FIRCO / sanctions screening. Fuzzy match, threshold 0.85."""
    hits = []
    for e in _load("watchlist_synthetic.json"):
        if e["kind"] != kind:
            continue
        score = SequenceMatcher(None, name.lower(), e["name"].lower()).ratio()
        if score >= 0.85:
            hits.append({"matched": e["name"], "list": e["list"], "score": round(score, 2)})
    return hits


def price_benchmark(commodity):
    """Stand-in for a market price reference service (unit price range, USD)."""
    return _load("price_benchmarks_synthetic.json").get(commodity)


def jurisdiction_risk(country):
    """Stand-in for the bank's country risk table."""
    return _load("jurisdiction_risk_synthetic.json").get(country, "STANDARD")


def release_payment(trade_id):
    """A write action the TBML agent is deliberately NOT allowed to call."""
    return {"released": trade_id}


def build_default_tools(ledger):
    reg = ToolRegistry(ledger)
    reg.register("get_trade", "trade:read", get_trade, "Read a trade finance transaction")
    reg.register("screen_name", "screening:read", screen_name, "Sanctions / watchlist screening")
    reg.register("price_benchmark", "pricing:read", price_benchmark, "Market unit-price range")
    reg.register("jurisdiction_risk", "risk:read", jurisdiction_risk, "Country risk rating")
    reg.register("release_payment", "payments:write", release_payment, "Release a held payment")
    return reg
