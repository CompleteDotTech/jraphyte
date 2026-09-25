# TRACE-GC architecture revision — 0.4.0

> **The graph is both an output of compilation and an input to future compilation.**

This release extends the supplied 0.3 implementation with a shared, bidirectional hybrid source/graph retrieval subsystem. It does not replace the existing Evidence Firewall, bounded semantic adapter, resolver, qualification, signed authorization or transactional graph authority.

The canonical specification is `docs/01_architecture.md`. The editable diagrams are `diagrams/architecture.mmd` and `diagrams/graphrag.mmd`. Planner, budgets and cache are specified in `docs/16_retrieval_planner_budget_cache.md`; retrieval/provenance/contradiction/temporal/decision APIs in `docs/17_hybrid_and_downstream_graphrag.md`; security in `docs/18_graphrag_security.md`; replay/evaluation in `docs/19_graphrag_replay_evaluation.md`; material deltas in `docs/20_graphrag_deltas.md`; research/roadmap/paper outline in `docs/21_graphrag_research_roadmap.md`; and all requested deliverables in `docs/22_graphrag_traceability.md`.

The executable runtime remains `trace_gc/`; the extension is `trace_gc/retrieval/`. Schemas remain in `schemas/runtime/` and the wheel's resources. Original 0.3 architecture/report documents are preserved under `archive/v0.3`; the previous 0.2 archive is unchanged. The original tests and fixed semantic question definitions remain regression inputs.

GraphRAG retrieves context. TRACE-GC synthesizes proposed state. The compiler validates structure. Only the existing transaction layer changes authoritative graph state. The release's real validation results and unexecuted external gates are recorded in `VALIDATION_REPORT.json`.
