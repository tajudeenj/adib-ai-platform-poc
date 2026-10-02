"""Optional: expose the screening and pricing tools as a real MCP server.
pip install mcp   then   python mcp_server.py
Any MCP-capable agent (Copilot Studio, Azure AI Foundry, Claude, LangGraph) can then
discover and call these tools. Scopes and audit are still enforced by ToolRegistry.
"""
try:  # mcp SDK 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP

from core.ledger import AuditLedger
from core.tools import build_default_tools

ledger = AuditLedger("mcp_audit.jsonl")
registry = build_default_tools(ledger)
SCOPES = {"screening:read", "pricing:read", "risk:read"}  # granted to this server's client identity
mcp = FastMCP("adib-screening-tools")


@mcp.tool()
def screen_name(name: str, kind: str = "entity") -> list:
    """Screen a party or vessel name against the sanctions watchlist (synthetic data)."""
    return registry.call("mcp-client", SCOPES, "screen_name", name=name, kind=kind)


@mcp.tool()
def price_benchmark(commodity: str) -> list:
    """Return the market unit-price range in USD for a commodity (synthetic data)."""
    return registry.call("mcp-client", SCOPES, "price_benchmark", commodity=commodity)


if __name__ == "__main__":
    mcp.run()
