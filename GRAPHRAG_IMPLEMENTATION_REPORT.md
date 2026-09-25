# TRACE-GC 0.4.0 — GraphRAG implementation report

## Delivered project

The supplied TRACE-GC 0.3.0 project was extended in place with a bidirectional GraphRAG reference subsystem. Existing source verification, atomic semantic tasks, confidence/outcome separation, resolver, deterministic constraints, authorization, calibration/qualification, graph transactions and replay were retained. The graph is both an output of compilation and an input to future compilation.

The new upstream `UpstreamGraphRAG` coordinates retrieval before the existing question/semantic/resolver workflow. The downstream `GraphRAGQueryService` exposes evidence-backed, source-cited context over the same compiled graph. They share retrieval infrastructure but have distinct roles. Neither component has a publication capability; graph retrieval is candidate context, not an arbiter of graph truth.

This is an executable, installable reference integration with explicit external gates. It is not a production qualification, a replacement graph database, or evidence of improved real-model accuracy.

## Input preservation audit

| Item | Verified result |
|---|---|
| Input archive | `TRACE-GC_Implemented_Project(1).zip` |
| Input SHA-256 | `5fdb420a3d927cc6ca247f8013bdbebfb608dc18788a4ff4ef1528690fed62db` |
| Baseline test run | 197 tests: 196 passed, one external conformance test skipped |
| Original test files | All five files byte-identical to the input archive |
| Original runtime modules | All 25 retained; extension changes are recorded individually |
| Original semantic program definitions | Existing top-level assignments preserved; reranking uses a separate relevance program |
| Original documentation and release reports | Preserved under `archive/v0.3/` |
| Original record envelope | `0.3.0` compatibility retained; retrieval payloads use `trace-retrieval-v1` |

The full hash audit is in `review/graphrag_baseline_audit.json`. Extended original modules are `trace_gc/__init__.py`, `trace_gc/adapter.py`, `trace_gc/catalog.py`, `trace_gc/cli.py`, `trace_gc/compiler.py`, `trace_gc/demo.py`, `trace_gc/ledger.py`, `trace_gc/plans.py`, `trace_gc/programs.py`, `trace_gc/replay.py`, `trace_gc/resolver.py`, `trace_gc/validation.py`. The transaction backend, independent trust enrollment, qualification implementation and deterministic constraints were not replaced.

## Material architectural changes

| Existing component | GraphRAG extension | Integration point | Why | Principal risk | Validation |
|---|---|---|---|---|---|
| Source verification and evidence closure | Bounded canonical source + graph context | `compiler.py`, retrieval security/integration | Adds useful prior graph context without treating adjacency as proof | Forged, stale or excessive context | Canonical reconstruction, ACL, source withdrawal and closure tests |
| Question packing and exact Jev receipts | Optional bounded graph-relevance program and retrieval lineage | Existing pack/adapter/observation records | Audits what reached the model and why | Reranker silently changing truth or scope | Exact response/pack binding; forged and recursive rerank rejection |
| Resolver and abstention | Task/risk planner and finite uncertainty-triggered expansion | Existing `INSUFFICIENT` semantic outcome and policy result | Acquires more evidence only when needed | Retrieval loops or answer shopping | Round/cost/latency limits; saturation and review-stop tests |
| Authoritative snapshot/journal | Read-only graph adapters and historical/temporal views | Existing SQLite authority; in-memory fixtures | Makes committed graph state queryable without a second writer | Inconsistent snapshot or inaccessible historical content | Version, source-epoch, rollback and before-source tests |
| Decision/provenance ledger | Query, context, selection/discard and source-citation lineage | Existing immutable Catalog, ledger and validation | Explains retrieval-to-decision-to-commit provenance | Broken or fabricated references | Strict schemas, reference reconstruction and complete-bundle validation |
| Compiled evidence graph | Downstream claim-, contradiction-, temporal- and decision-aware GraphRAG | `GraphRAGQueryService` | Supplies inspectable evidence contexts to QA/search/agents | One-sided conflicts or lossy summaries mistaken for proof | Conflict-pair accounting, exact source spans, historical/trust tests |
| Replay and research gates | Alternative retrieval branches, metrics, ablations and held-out policy gate | Existing replay/qualification boundaries | Tests retrieval changes without rewriting original observations | Benchmark leakage or unsupported performance claims | Disjoint held-out selection tests; synthetic results explicitly labeled |
| Existing packaging and validation | 108 added tests, four scenarios, 91 comparisons and 28 schemas | CLI, validation runner and wheel resources | Makes the integration reproducible and portable | Source-only success or missing installed resources | Installed-wheel execution outside the source tree |

The expanded six-column matrix is in `docs/20_graphrag_deltas.md`. All 50 requested sections and all 25 deliverables have a location and coverage/limitation entry in `docs/22_graphrag_traceability.md`.

## Executable retrieval capabilities

The hybrid service includes 18 channels: entity, lexical, vector, neighborhood, path, community, global, ontology, schema, relation, provenance, evidence, conflict, decision, temporal, source, similar-case and claim retrieval. Canonical candidates are deduplicated and ranked by explicit utilities rather than uncalibrated probabilities. Optional Jev relevance judgments reorder bounded candidates without rewriting their contents or publication status.

Seven graph trust classes preserve the distinction between verified provenance, provisional facts, derived artifacts, conflicts, superseded facts, historical facts and unverified context. Six query modes support balanced evidence, consensus, contradictions only, provenance only, historical and latest-valid-state retrieval. A community summary is a versioned retrieval artifact linked to original assertions and evidence, not canonical evidence.

Deny-by-default resource ACLs cover tenant, workspace, user, roles, security classification, sources, nodes, edges, decisions and schema fragments. Filtering precedes embedding or semantic-model context construction. Historical requests continue to honor current source access and tombstones. The application must supply a trusted access policy; an internal audit Catalog is not a public unauthenticated API.

Structured budgets bound hops, paths, unique nodes/edges, communities, provenance depth, decisions, source spans, context size, work, latency, candidates, rounds and semantic reranking. Known contradiction pairs are selected atomically or omitted with a warning, rather than falling back to a misleading one-sided assertion. Snapshot/status/ACL/algorithm-sensitive caches prevent stale authorized context from being reused after relevant changes.

## Executed validation

Generated on `2026-09-25T08:58:36.501082+00:00` in the environment recorded in `VALIDATION_REPORT.json`.

| Check | Actual result |
|---|---|
| Full unit/integration/security suite | **305 run; 304 passed; 1 skipped; 0 failures; 0 errors** |
| Original baseline / added GraphRAG tests | 197 / 108 |
| Original adversarial design-review probes | 18 of 18 rejected; none accepted |
| Canonicalization vectors | 18 valid and 6 invalid vectors checked |
| Runtime schemas and embedded copies | 28 matching schema pairs |
| Original isolated transactional lifecycle | Passed |
| GraphRAG end-to-end scenarios | Four passed |
| Synthetic benchmark | 91 runs across seven task families; eight upstream + five downstream configurations |
| Installed-wheel checks | CLI version, original demo, four GraphRAG scenarios, 91 comparisons and both bundle validators passed outside source tree |
| Live provider calls / production graph writes | 0 / 0 |

The sole skip is the retained pinned-upstream conformance test: matching external `core.py` bytes were not supplied. Synthetic scenarios do execute authorized commits against isolated temporary test databases with ephemeral test keys. No private key or persistent test database is exported.

The four scenarios exercise entity identity, opposing source claims, condition-specific research claims, and uncertainty-triggered retrieval expansion. Each exports immutable records, an evidence-cited answer context and a result report. The expansion scenario performs a second decision round when additional graph context arrives, then follows the existing independently reviewed sandbox publication path. It does not bypass unqualified-policy abstention.

## Results that are not established

The benchmark labels are hand-authored synthetic relevance labels. Its semantic oracle intentionally uses fixture context coverage; those decisions are not an independent estimate of a real model's accuracy. Benchmark results therefore establish retrieval measurements and pipeline wiring only. Real-model synthesis improvement, deployed calibration, scientific novelty and a controlled production pilot remain unestablished.

The tested graph adapters are the existing SQLite reference authority and in-memory snapshots. Neo4j, PostgreSQL/AGE/pgvector, PuppyGraph and RDF/SPARQL integrations are replaceable adapter designs, not shipped remote connectors. The offline embedding baseline is deterministic token hashing, with exact-version supplied vectors and embedding interfaces; no trained provider was invoked. Community retrieval uses bounded connected components, not a full hierarchical global GraphRAG indexing pipeline.

The cache stores authorized hybrid candidate results, including graph, provenance, community and vector results. A separate retrieval-plan cache and durable ANN index are documented extensions, not implemented services. The downstream interface returns structured contexts; it is not an HTTP server or an automatic prose-answer generator. The existing fixed synthesis tasks remain source support/refutation and identity, even though graph retrieval supports broader relation types.

Latency checks are cooperative; remote adapters need their own cancellation and I/O timeouts. Context-size accounting uses a conservative UTF-8 byte estimate, not billed provider tokens. Retrieval cost is logical work, not measured currency. These limits and deployment acceptance gates are documented rather than presented as production guarantees.

## Run the project

```sh
python -m pip install .
trace-gc --version
python tools/run_validation.py
trace-gc graphrag-demo --output examples/graphrag/scenarios
trace-gc graphrag-benchmark --output benchmarks/graphrag
python examples/graphrag/query_example.py
trace-gc validate examples/graphrag/scenarios/D_uncertainty_expansion/bundle.json
```

Installing the standalone wheel provides the Python runtime, CLI and embedded schemas. Use the project ZIP for documentation, test sources, policy files, editable Mermaid diagrams, benchmark results and scenario exports.

## Files to read first

`README.md` is the entry point. `docs/01_architecture.md` is the canonical architecture. `docs/16_retrieval_planner_budget_cache.md` specifies planning, limits, expansion and caching. `docs/17_hybrid_and_downstream_graphrag.md` covers retrieval strategies and the downstream API. `docs/18_graphrag_security.md` covers security boundaries. `docs/19_graphrag_replay_evaluation.md` covers replay, metrics and experimental method. `docs/20_graphrag_deltas.md` contains the requested change matrix. `docs/21_graphrag_research_roadmap.md` separates prior work, implemented integration, hypotheses and deployment gates. `docs/22_graphrag_traceability.md` maps the request and deliverables.

The editable diagram sources are `diagrams/architecture.mmd`, `diagrams/graphrag.mmd` and `diagrams/retrieval_expansion.mmd`; pre-rendered diagram images are not claimed. Generated execution evidence is in `VALIDATION_REPORT.json`, `VALIDATION_LOG.txt`, `PACKAGING_REPORT.json`, `examples/graphrag/scenarios/` and `benchmarks/graphrag/`. `MANIFEST.json` records delivered file sizes and hashes, excluding its own bytes to avoid recursive hashing.
