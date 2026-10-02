# ADIB Enterprise AI Platform: working POC

This POC is the Enterprise AI Blueprint running as code. It is not a chatbot demo.
It shows the shared platform services every AI use case at the bank would reuse,
with the TBML Investigation Agent as the first lighthouse.

**All data is synthetic. The policy documents are illustrative samples, not ADIB policy.**
Runs on any laptop with Python 3.10+, no installs and no API keys.

```bash
python demo.py                 # 9-step end-to-end walkthrough (about 1 second)
python evals/run_evals.py      # Gate 5 evaluation, exits non-zero if thresholds fail (CI-ready)
```

## What the demo proves

| Step | What happens | Why it matters to the bank |
|---|---|---|
| 1 | Unregistered / ungated use case is blocked; gates passed in order | Governance is enforced in code, not in a slide |
| 2 | Emirates ID, IBAN and phone numbers masked before any model call | Customer data never reaches the model (UAE PDPL) |
| 3 | Agent investigates trade T-1003: flags, score, policy citations | Every finding is explainable and traceable to policy |
| 4 | Investigator approves the proposed escalation | A named human owns every adverse decision |
| 5 | Murabaha on prohibited goods is routed to the Sharia function | AI flags; the Sharia committee decides |
| 6 | Agent tries to release a payment and is denied | Least-privilege tools: agents cannot act beyond their scope |
| 7 | Customer requests human review of an AI-assisted outcome | CBUAE Guidance Note (Feb 2026) expectation |
| 8 | One audit record is edited; the chain breaks at that exact entry | Tamper-evident trail for auditors and regulators |
| 9 | Golden-set evaluation with pass/fail thresholds | LLMOps: no release without measured quality |

## Repo map to the reference architecture

| Architecture layer | File | Production equivalent |
|---|---|---|
| AI Gateway (ADR-001) | `core/gateway.py` | Azure API Management AI-gateway policies, UAE region |
| Governance and AI inventory | `core/governance.py` | AI Review Board workflow (extends the EA DRB), model inventory |
| Tools and integration (ADR-003) | `core/tools.py`, `mcp_server.py` | MCP servers over IBM APIC / ESB and Oracle OIC APIs |
| Knowledge, RAG with citations (ADR-002) | `core/rag.py`, `policies/` | Azure AI Search hybrid index over the controlled policy library |
| Agent and orchestration | `agents/tbml_agent.py` | Azure AI Foundry agent / LangGraph; Copilot Studio for Tier 1 |
| Human-in-the-loop (ADR-004) | `core/governance.py` `HumanReviewQueue` | Case management system task with maker-checker |
| Audit ledger | `core/ledger.py` | Append-only ledger tables, exported to the SIEM |
| LLMOps evaluation | `evals/` | Eval pipeline in Azure DevOps / GitHub Actions, gate on every release |

## Switch from the offline model to Azure OpenAI

```bash
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_KEY=<key>
export AZURE_OPENAI_DEPLOYMENT=<deployment-name>
python demo.py
```
The gateway picks the provider automatically. Masking, budgets and audit still apply.

## Expose the tools as a real MCP server

```bash
pip install mcp
python mcp_server.py
```
Any MCP-capable agent platform can then discover `screen_name` and `price_benchmark`.

## Path to production (the bank is Java-first)

The POC is Python for speed. In production the same patterns map to the existing estate:
gateway rules become APIM policies; tools become MCP servers wrapping existing APIC/ESB/OIC
services (Java/Spring Boot where custom code is needed, e.g. Spring AI); the ledger becomes
an append-only database table; the review queue becomes a case-management task.
Only the agent reasoning layer is new.

## Honest limits

- 100% on the golden set means the evaluation harness works on 8 synthetic cases built for
  the demo. Real accuracy must be measured on historical, investigator-labelled cases in the pilot.
- The screening, pricing and risk tools are stand-ins for FIRCO and bank reference data.
- Rules carry the detection logic; the model writes the narrative. This is deliberate for a
  Tier 3 use case: deterministic, explainable controls, with GenAI where it adds value.
