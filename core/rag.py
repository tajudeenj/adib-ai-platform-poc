"""Retrieval with citations (ADR-002: RAG, not fine-tuning, for policy knowledge).

Minimal BM25 over policy sections so the POC has zero dependencies.
Production equivalent: Azure AI Search hybrid (vector + keyword) index over the
bank's controlled policy library, with document versions recorded in every citation.
"""
import math
import re
from collections import Counter
from pathlib import Path

POLICIES = Path(__file__).resolve().parent.parent / "policies"


def _tok(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class PolicyIndex:
    def __init__(self, folder=POLICIES):
        self.chunks = []
        for f in sorted(folder.glob("*.md")):
            doc_title = f.stem
            for block in re.split(r"\n(?=## )", f.read_text()):
                if block.startswith("## "):
                    head, _, body = block.partition("\n")
                    self.chunks.append({"doc": doc_title, "section": head[3:].strip(), "text": body.strip()})
        self.tf = [Counter(_tok(c["section"] + " " + c["text"])) for c in self.chunks]
        self.avgdl = sum(sum(t.values()) for t in self.tf) / len(self.tf)
        df = Counter(w for t in self.tf for w in t)
        n = len(self.tf)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def search(self, query, k=2, k1=1.5, b=0.75):
        q = _tok(query)
        scored = []
        for i, tf in enumerate(self.tf):
            dl = sum(tf.values())
            s = sum(self.idf.get(w, 0) * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * dl / self.avgdl)) for w in q)
            if s > 0:
                scored.append((s, i))
        return [dict(self.chunks[i], score=round(s, 2), citation=f"{self.chunks[i]['doc']} > {self.chunks[i]['section']}")
                for s, i in sorted(scored, reverse=True)[:k]]
