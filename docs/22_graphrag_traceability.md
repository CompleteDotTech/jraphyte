# GraphRAG requirement and deliverable traceability

## Scope and status vocabulary

This index maps the 50 numbered requirements in `sources/graphrag_requirements.txt` to the implemented reference runtime and its explicit extension boundaries. “Implemented” means executable offline reference behavior, not production qualification. Remote database connectors, trained embedding services, true model accuracy experiments, a durable vector index, a separate retrieval-plan cache, and automated human/external acquisition are not silently claimed to exist. The fixed original synthesis tasks remain support/refutation and identity; a retrievable relation type is not automatically a newly qualified mutation task.

Paths without a leading directory in the implementation column are under `trace_gc/`; schema-only filenames are under `schemas/runtime/`. The baseline audit and generated validation report record what was inspected and executed.

## Requirements 1–50

| # | Requirement | Implementation / specification | Coverage and important limit |
|---:|---|---|---|
| 1 | Responsibility boundaries | `docs/01_architecture.md; compiler.py; backend.py` | Graph retrieval never changes authoritative state; existing validation and transaction owners retained. |
| 2 | Hybrid Evidence & Graph Retrieval | `retrieval/service.py; strategies.py; vector.py` | 18 executable channels, canonical fusion and deterministic utility ranking. |
| 3 | Upstream GraphRAG | `retrieval/planner.py; compiler.py` | UpstreamGraphRAG compiles selected graph context before the original semantic questions. |
| 4 | Firewall and graph trust | `retrieval/security.py; items.py` | Existing source verification plus seven provenance/status trust classes; no trust from adjacency. |
| 5 | Source + graph evidence closure | `compiler.py; retrieval/integration.py` | Explicit bounded model context; full graph remains available for deterministic validation. |
| 6 | Graph Context IR | `schemas/runtime/graph-context.schema.json` | Versioned canonical items and projections, model-safe rendering, provenance and selection lineage. |
| 7 | Structured graph query | `schemas/runtime/retrieval-query.schema.json` | Validated structured scope, modes, filters, snapshot, methods and budgets. |
| 8 | Pluggable graph strategies | `retrieval/strategies.py` | GraphRetriever protocol and local/path/community/global/ontology/temporal/conflict implementations. |
| 9 | Database agnosticism | `retrieval/store.py; docs/17_hybrid_and_downstream_graphrag.md` | In-memory and existing SQLite snapshot/journal adapters implemented; other database adapters are extension contracts, not shipped connectors. |
| 10 | Hybrid vector + graph | `retrieval/vector.py; service.py` | Executable deterministic offline embedding and supplied-vector adapter; trained provider integration is a deployment gate. |
| 11 | Bounded semantic reranking | `retrieval/reranker.py; programs.py` | Exact Jev pack/receipt path with a separately pinned relevance program; never overrides canonical text or truth. |
| 12 | Retrieval budgets | `retrieval/budget.py; policies/retrieval-budget.json` | All requested resource dimensions plus candidate/round/semantic caps; cost is logical work, not currency. |
| 13 | Uncertainty-triggered expansion | `retrieval/planner.py` | Existing INSUFFICIENT evidence routes to RETRIEVE_MORE_EVIDENCE; no automatic write or confidence shopping. |
| 14 | Stopping and saturation | `retrieval/planner.py` | Budget, no-new-content, rejection, infeasibility, review and qualification outcomes stop the bounded controller. |
| 15 | Downstream GraphRAG | `retrieval/service.py:GraphRAGQueryService` | Read-only evidence-backed context API for QA/search/agents; no fabricated natural-language answer or HTTP server. |
| 16 | Downstream provenance | `retrieval/items.py; service.py` | Assertion to transaction, plan, resolution, observation, original evidence and source citations when available. |
| 17 | Claim-centric retrieval | `retrieval/strategies.py; fixtures.py` | CLAIM target, supporting/opposing source claims, replication, method/dataset and condition context. |
| 18 | Contradiction-aware modes | `retrieval/items.py; service.py` | Six query modes; balanced default, temporal conflict checks and atomic conflict budget accounting. |
| 19 | Temporal GraphRAG | `retrieval/store.py; items.py` | Graph-version/as-of/before-source journal reads and half-open assertion-valid-time filters. |
| 20 | Decision-aware GraphRAG | `retrieval/strategies.py; items.py` | Prior decisions, observations, resolutions and evaluations are available with access and availability checks. |
| 21 | Rejected / historical hypotheses | `retrieval/items.py; strategies.py` | Explicit historical HYPOTHESIS and decision items; never mistaken for accepted graph assertions. |
| 22 | Retrieval lineage ledger | `retrieval/service.py; integration.py; ledger.py` | Candidate/selected/discarded accounting, reasons, scores, query/method versions, usage and cache telemetry. |
| 23 | Decision IR linkage | `compiler.py; adapter.py; resolver.py; integration.py` | All-or-none query/context/source-retrieval/closure/fingerprint linkage, derived from exact underlying packs. |
| 24 | Retrieval-aware replay | `replay.py` | Append-only alternative retrieval branches with original observations preserved and no authorization. |
| 25 | GraphRAG evaluation | `retrieval/evaluation.py` | Retrieval, synthesis and efficiency functions; null metrics when denominators or genuine measurements are absent. |
| 26 | Ablations | `retrieval/evaluation.py; benchmark.py` | Eight upstream and five downstream configurations executed across seven synthetic cases. |
| 27 | Failure taxonomy | `retrieval/contracts.py; evaluation.py` | All 18 named retrieval failures plus structured proposals and regression tests. |
| 28 | Autoresearch strategy optimization | `retrieval/evaluation.py; docs/19_graphrag_replay_evaluation.md` | Development selection plus disjoint held-out promotion gate; no autonomous production policy promotion. |
| 29 | Retrieval Planner | `retrieval/planner.py; retrieval-plan.schema.json` | Candidate/question/risk/entities/relations/uncertainty/history/budget drive structured plans. |
| 30 | Progressive tiers | `retrieval/planner.py; docs/16_retrieval_planner_budget_cache.md` | Tiers 0–4 executable; tier 5 hands off for external acquisition/human review. Four-round default does not automatically reach tier 4. |
| 31 | Caching and invalidation | `retrieval/service.py:RetrievalCache` | Deep-copy LRU for authorized hybrid candidates including paths, community and vector results. Snapshot/status/ACL/version keys; standalone plan cache/durable index are documented extensions, not implemented services. |
| 32 | Canonical evidence vs summaries | `retrieval/items.py; integration.py` | Generated summaries explicitly non-authoritative; exact original record/evidence pointers remain canonical. |
| 33 | Community summaries | `retrieval/strategies.py; items.py` | Versioned regenerable bounded component summaries with member assertions/source evidence; not a full hierarchical community-detection pipeline. |
| 34 | Security / injection boundary | `retrieval/security.py; integration.py; docs/18_graphrag_security.md` | Source-derived context is data, checked before model construction and rendered with explicit origin flags. |
| 35 | Access controls | `retrieval/security.py; store.py; service.py` | Tenant/workspace/user/role/classification/resource grants; no hidden bridge traversal or unauthorized vector input. |
| 36 | Canonical architecture | `docs/01_architecture.md; diagrams/architecture.mmd` | Single existing compilation architecture with separate upstream and downstream retrieval roles. |
| 37 | Continuous synthesis loop | `retrieval/store.py; scenarios.py` | Existing commits are visible to subsequent retrieval; immutable version lineage and version-keyed invalidation. |
| 38 | Research framing | `docs/21_graphrag_research_roadmap.md` | Known prior techniques, retained Jev practices, project-specific integration and unvalidated hypotheses separated. |
| 39 | Schemas and original IRs | `tools/retrieval_schemas.py; schemas/runtime/` | Ten added record schemas, 28 total; original content-addressed record envelope remains 0.3.0-compatible. |
| 40 | Implementation modules | `trace_gc/retrieval/; docs/20_graphrag_deltas.md` | New retrieval-specific package integrated into existing compiler/adapter/resolver/ledger/validation, not parallel synthesis. |
| 41 | Comprehensive tests | `tests/test_graphrag_*.py; VALIDATION_REPORT.json` | 108 additional tests across retrieval, pipeline, evaluation and security; original test files unchanged. |
| 42 | Four end-to-end scenarios | `retrieval/scenarios.py; examples/graphrag/scenarios/` | Entity identity, opposing claims, research claims, uncertainty expansion; existing independent reviewed sandbox commit used. |
| 43 | Benchmark experiments | `retrieval/benchmark.py; benchmarks/graphrag/` | 91 actual synthetic comparisons; seven requested task families. Controlled oracle is explicitly not a real model accuracy result. |
| 44 | Retrieval quality autoresearch | `retrieval/evaluation.py; docs/19_graphrag_replay_evaluation.md` | Failure-driven proposals, frozen development choice, held-out strict improvement and non-overlap guards. |
| 45 | Reproducibility | `retrieval/service.py; planner.py; replay.py` | Snapshot, ACL, algorithm, embedding, ranking/budgets, cache telemetry and original Jev/question/resolver/constraint/policy lineage. |
| 46 | Graph is output and input | `README.md; docs/01_architecture.md` | Prominent architectural principle, implemented transaction → snapshot → retrieval visibility. |
| 47 | GraphRAG is not graph synthesis | `docs/01_architecture.md; retrieval/service.py` | GraphRAG locates context; TRACE-GC proposes, compiler validates, transaction authority commits. |
| 48 | Deliverables | `This document, deliverable index below` | Architecture, diagrams, specifications, schemas, reports, executable code, examples and tests are packaged together. |
| 49 | Architectural delta matrix | `docs/20_graphrag_deltas.md; review/graphrag_baseline_audit.json` | Material changes only, with existing component, extension, integration, rationale, risk and validation columns. |
| 50 | Final target architecture | `docs/01_architecture.md; diagrams/graphrag.mmd; scenarios.py` | Complete reference retrieve → synthesize/validate → reviewed commit → retrieve-again cycle; deployment gates remain explicit. |

## The 25 requested deliverables

| # | Deliverable | Packaged location |
|---:|---|---|
| 1 | Canonical architecture | `docs/01_architecture.md` |
| 2 | Main architecture diagram | `diagrams/architecture.mmd` |
| 3 | GraphRAG subsystem diagram | `diagrams/graphrag.mmd` |
| 4 | Retrieval Planner specification | `docs/16_retrieval_planner_budget_cache.md` |
| 5 | Hybrid Retrieval specification | `docs/17_hybrid_and_downstream_graphrag.md` |
| 6 | Graph Retrieval Query schema | `schemas/runtime/retrieval-query.schema.json` |
| 7 | Graph Context IR schema | `schemas/runtime/graph-context.schema.json` |
| 8 | Retrieval lineage schema | `schemas/runtime/retrieval-lineage.schema.json` |
| 9 | Expansion specification and diagram | `docs/16_retrieval_planner_budget_cache.md; diagrams/retrieval_expansion.mmd` |
| 10 | Retrieval-budget policy | `policies/retrieval-budget.json` |
| 11 | Cache/invalidation design | `docs/16_retrieval_planner_budget_cache.md` |
| 12 | Downstream API/design | `docs/17_hybrid_and_downstream_graphrag.md; examples/graphrag/query_example.py` |
| 13 | Provenance-aware design | `docs/17_hybrid_and_downstream_graphrag.md` |
| 14 | Contradiction-aware design | `docs/17_hybrid_and_downstream_graphrag.md; docs/18_graphrag_security.md` |
| 15 | Temporal design | `docs/17_hybrid_and_downstream_graphrag.md` |
| 16 | Decision-aware design | `docs/17_hybrid_and_downstream_graphrag.md` |
| 17 | Replay updates | `docs/05_provenance_replay.md; docs/19_graphrag_replay_evaluation.md; trace_gc/replay.py` |
| 18 | Evaluation updates | `trace_gc/retrieval/evaluation.py; docs/19_graphrag_replay_evaluation.md` |
| 19 | Benchmark and ablation plan | `benchmarks/graphrag/dataset.json; benchmarks/graphrag/benchmark_results.json; docs/19_graphrag_replay_evaluation.md` |
| 20 | Retrieval error taxonomy | `trace_gc/retrieval/contracts.py:FAILURES; docs/09_failure_autoresearch.md` |
| 21 | Implementation / deployment roadmap | `docs/21_graphrag_research_roadmap.md` |
| 22 | Updated research contributions | `docs/21_graphrag_research_roadmap.md` |
| 23 | Updated paper outline | `docs/21_graphrag_research_roadmap.md` |
| 24 | End-to-end examples | `trace_gc/retrieval/scenarios.py; examples/graphrag/scenarios/` |
| 25 | Comprehensive tests | `tests/test_graphrag_retrieval.py; tests/test_graphrag_pipeline.py; tests/test_graphrag_evaluation.py; tests/test_graphrag_security.py` |

## Re-run the release checks

```sh
python -m pip install -r requirements.txt
python tools/run_validation.py
python -m trace_gc graphrag-demo --output examples/graphrag/scenarios
python -m trace_gc graphrag-benchmark --output benchmarks/graphrag
python -m trace_gc validate examples/graphrag/scenarios/D_uncertainty_expansion/bundle.json
```

The generated suite report separates failures, skips and deployment gates. Benchmark rows are retained rather than selecting only favorable configurations. Packaging hashes attest delivered bytes, not semantic correctness. The Mermaid files are editable diagram sources, not pre-rendered images.
