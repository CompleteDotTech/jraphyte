#!/usr/bin/env python3
"""Source-cited GraphRAG query over a fabricated, explicitly authorized fixture."""
from pathlib import Path
import json
import sys

# Make the checked-out example runnable without an editable installation.
ROOT = Path(__file__).resolve().parents[2]
if (ROOT / "trace_gc").is_dir():
    sys.path.insert(0, str(ROOT))

from trace_gc.retrieval.contracts import RetrievalBudget, query
from trace_gc.retrieval.fixtures import SCOPE, corpus
from trace_gc.retrieval.service import GraphRAGQueryService


def main() -> None:
    fixture = corpus()
    request = query(
        requesting_component="downstream-research-example",
        security_scope=SCOPE,
        focus_entities=[fixture["claim_id"]],
        text="Does intervention X improve outcome Y in population P?",
        strategies=["CLAIM", "NEIGHBORHOOD", "CONFLICT", "PROVENANCE", "EVIDENCE"],
        mode="BALANCED_EVIDENCE",
        budget=RetrievalBudget(maximum_tokens=16000),
    )
    answer = GraphRAGQueryService(fixture["retriever"]).query(request)
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()
