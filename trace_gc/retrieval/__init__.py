"""Bidirectional GraphRAG integrated with TRACE-GC's evidence-gated compiler.

Public implementations are imported explicitly to avoid import-time I/O and
cycles with the immutable Catalog and existing compiler modules.
"""
from .contracts import RetrievalBudget, query, VERSION

__all__ = ["RetrievalBudget", "query", "VERSION"]
