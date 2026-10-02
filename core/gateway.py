"""AI Gateway: the single control point for every model call (ADR-001).

Enforces: inventory check, PII masking, token budget per use case, model routing
by risk tier, and full audit logging (prompt is stored as a hash, never raw).
Production equivalent: Azure API Management AI-gateway policies in front of
Azure OpenAI / private models, hosted in the UAE region.
"""
import hashlib
import json
import os
import re
import urllib.request

PII_PATTERNS = [
    ("EMIRATES_ID", re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b")),
    ("IBAN", re.compile(r"\bAE\d{2}(?:\s?\d{4}){4}\s?\d{3}\b")),
    ("CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    ("PHONE", re.compile(r"(?:\+971[ -]?|00971[ -]?|\b0)(?:5\d|[2-79])[ -]?\d{3}[ -]?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
]

MODEL_ROUTES = {1: "small-fast-model", 2: "large-reasoning-model", 3: "large-reasoning-model"}


def mask_pii(text):
    found = {}
    for label, pattern in PII_PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        if n:
            found[label] = n
    return text, found


class MockLLM:
    """Deterministic offline model so the POC runs anywhere, with no keys and no data leaving the laptop."""

    def complete(self, model, prompt):
        facts = [l.strip("- ").strip() for l in prompt.splitlines() if l.strip().startswith("- ")]
        if not facts:
            return "No material red flags identified in the supplied facts."
        return ("Investigator summary: " + "; ".join(facts[:6]) +
                ". Recommendation is advisory only; final decision rests with the investigator.")


class AzureOpenAIProvider:
    """Optional: set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT."""

    def __init__(self):
        self.endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        self.key = os.environ["AZURE_OPENAI_KEY"]
        self.deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    def complete(self, model, prompt):
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version=2024-06-01"
        body = json.dumps({"messages": [
            {"role": "system", "content": "You are a TBML investigation assistant. Summarise only the facts given. Never decide; recommend."},
            {"role": "user", "content": prompt}], "temperature": 0}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "api-key": self.key})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["choices"][0]["message"]["content"]


def default_provider():
    return AzureOpenAIProvider() if os.environ.get("AZURE_OPENAI_ENDPOINT") else MockLLM()


class BudgetExceeded(Exception):
    pass


class AIGateway:
    def __init__(self, registry, ledger, provider=None):
        self.registry, self.ledger = registry, ledger
        self.provider = provider or default_provider()
        self.spent = {}

    def complete(self, use_case_id, caller, prompt):
        uc = self.registry.require_runnable(use_case_id)          # 1. inventory + gates
        masked, pii = mask_pii(prompt)                            # 2. PII never leaves the bank
        tokens = max(1, len(masked) // 4)                         # 3. token budget (FinOps)
        used = self.spent.get(use_case_id, 0)
        if used + tokens > uc.token_budget:
            self.ledger.append("llm_blocked_budget", caller, {"use_case": use_case_id, "requested": tokens})
            raise BudgetExceeded(f"{use_case_id} token budget exhausted")
        self.spent[use_case_id] = used + tokens
        model = MODEL_ROUTES[uc.tier]                             # 4. route by risk tier
        response = self.provider.complete(model, masked)
        self.ledger.append("llm_call", caller, {                  # 5. audit, prompt stored as hash only
            "use_case": use_case_id, "model": model, "tokens_est": tokens, "pii_masked": pii,
            "prompt_sha256": hashlib.sha256(masked.encode()).hexdigest()})
        return response, pii
