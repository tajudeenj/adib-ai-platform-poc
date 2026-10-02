"""Hash-chained, tamper-evident audit ledger.

Every governance decision, model call, tool call and human approval is appended
here. Each entry stores the SHA-256 hash of the previous entry, so changing any
past record breaks the chain and verify() reports exactly where.
Production equivalent: append-only table (e.g. Azure SQL ledger tables / immutable
Blob storage) with the same hashing, exported to the SIEM.
"""
import hashlib
import json
from datetime import datetime, timezone

GENESIS = "0" * 64


class AuditLedger:
    def __init__(self, path=None):
        self.entries = []
        self.path = path
        if path:
            open(path, "w").close()

    @staticmethod
    def _hash(entry):
        body = {k: v for k, v in entry.items() if k != "hash"}
        return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()

    def append(self, event_type, actor, payload):
        entry = {
            "seq": len(self.entries) + 1,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "type": event_type,
            "actor": actor,
            "payload": payload,
            "prev_hash": self.entries[-1]["hash"] if self.entries else GENESIS,
        }
        entry["hash"] = self._hash(entry)
        self.entries.append(entry)
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def verify(self):
        """Return (True, None) if intact, else (False, seq_of_first_broken_entry)."""
        prev = GENESIS
        for e in self.entries:
            if e["prev_hash"] != prev or self._hash(e) != e["hash"]:
                return False, e["seq"]
            prev = e["hash"]
        return True, None

    def events(self, event_type=None):
        return [e for e in self.entries if event_type is None or e["type"] == event_type]
