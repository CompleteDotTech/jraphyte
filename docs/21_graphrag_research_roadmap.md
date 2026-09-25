# Research framing, contribution boundaries, roadmap and paper outline

## Research description

TRACE-GC is an evidence-gated typed probabilistic graph compiler in which hybrid document and graph retrieval constructs bounded evidence contexts, Jev supplies atomic semantic judgments, a resolver reconciles uncertain hypotheses, deterministic compilation enforces graph invariants, and reversible transactions update an evidence graph that subsequently serves as both a GraphRAG knowledge substrate and a retrieval source for future synthesis.

The framing is **incremental graph compilation**, not one-time graph extraction and not GraphRAG-as-truth. The same graph can be useful for locating evidence while still containing incomplete, provisional, contradictory, historically valid or superseded assertions.

## Attribution and novelty boundaries

Known GraphRAG work includes entity-centered local graph/document context and community-centered global summarization. Microsoft's local-search documentation describes combining structured graph data and unstructured document context [R2]. Edge and colleagues describe graph indexing with community summaries for query-focused summarization [R1]; the associated global-search documentation describes community-report-based retrieval [R3]. Those are prior techniques, not TRACE-GC inventions. No performance result from those sources is attributed to this implementation.

Lexical/vector fusion, graph traversal, reciprocal-rank ranking, graph-store adapters and versioned caching are treated here as engineering techniques, not novelty claims. TypeSafe/Jev's bounded semantic judgments, exact pinning and semantic outcome/confidence separation follow the existing supplied TRACE-GC architecture; this extension neither changes those original semantics nor claims to originate them.

The TRACE-GC-specific engineering integration is the auditable path from retrieval query through graph context, minimum evidence closure, question pack, exact observation, resolver decision, plan and versioned commit—and back into future retrieval. Other implemented integrations include source-plus-graph closure, explicit graph trust categories, bounded uncertainty expansion, provenance/contradiction/decision-aware downstream contexts, historical/rejected hypotheses, retrieval lineage and retrieval-aware replay.

Potential research contributions to investigate are whether that integration improves end-to-end synthesis reliability, reduces unsupported changes and false merges, improves abstention decisions, or makes graph updates more reproducible. It is **unvalidated** that any of those benefits hold across real datasets. No comprehensive novelty survey, statistical superiority, production calibration or scientific discovery is claimed by passing the release tests.

## Delivered reference implementation

The bidirectional loop, SQLite/in-memory adapters, 18 retrieval channels, strict IRs, scoped ACLs, source firewall integration, exact materialization, bounded planner/expansion, optional Jev relevance packs, query/context cache, downstream cited contexts, historical/decision modes, replay, metrics, failure proposals, four lifecycle scenarios and synthetic benchmark runner are executable. See the traceability matrix for code/test locations.

## Deployment and research roadmap

| Stage | Concrete next acceptance work | Gate / owner |
|---|---|---|
| Reference integration | Reproduce included tests, probes, scenarios, schemas, benchmark and installed-wheel checks. | Local validation report; engineering owner. |
| Production source/graph adapter | Implement deployment-native consistent reads, row/edge ACL pushdown, stable IDs, source epochs, timeouts, cancellation and journal-equivalent snapshots. Test rollback/commit visibility and unavailable history. | Storage/security conformance; no particular database is mandatory. |
| Semantic retrieval | Inject a trained exact-version embedding model or vector index; supply a trusted tokenizer and live Jev credentials/attestation. Exercise actual relevance outputs and provider failures. | External provider and privacy acceptance. |
| Community/global scale | Evaluate reviewed community algorithms or a Microsoft GraphRAG adapter, regenerate summaries with exact membership/provenance, benchmark high-degree graphs and bounded query plans. | Held-out quality plus latency/memory budget evidence. |
| Qualification/pilot | Collect representative independent labels; preregister group/time-separated comparisons; apply existing policy qualification; enroll authorities; run a reviewed pilot and audit accepted actions. | Deployment policy/security owners, not the model. |
| Optional autoresearch | Lock development-selected retrieval policies, test once on untouched holdouts and retain only improving safe changes; version and requalify before promotion. | Existing research/qualification process. |

No implementation of remote Neo4j/AGE/PuppyGraph/SPARQL adapters, production identity directory, distributed cache invalidation, durable ANN index, automated deployment or HTTP agent orchestration is claimed. The protocol and API designs permit these without changing synthesis authority. Ordinary document/API/row acquisition also stays in the existing source ingestion layer; GraphRAG is not a requirement for every retrieval.

## Updated paper outline

1. **Problem and scope.** Incremental evidence graph synthesis; distinction between locating knowledge, semantic judgment, structural validity and write authority.
2. **Prior work and attribution.** GraphRAG/local/global methods, hybrid retrieval, typed semantic judgments, evidence/provenance systems; define what is integration rather than invention.
3. **System and threat model.** Existing TRACE-GC stages; immutable source/candidate/decision/plan records; graph-store independence; data/instruction and access boundaries.
4. **Bidirectional architecture.** Graph as output and future input, upstream retrieval planner, downstream evidence contexts and graph-version loop.
5. **Minimum source-plus-graph closure.** Canonical context IR, constrained heuristic selection, retrieval budgets, source verification and full internal structural validation.
6. **Adaptive acquisition and resolution.** Task/risk tiers, insufficient-evidence transitions, stopping/saturation, confidence/outcome separation and unchanged qualified publication.
7. **Inspectable retrieval.** Provenance, temporal and contradiction modes; historical/rejected hypotheses; retrieval lineage and replay.
8. **Experimental method.** Frozen graph/source availability, grouped/time-separated labels, A–G and downstream ablations, retrieval/end-to-end/efficiency metrics, calibration and safety gates.
9. **Results.** Separate software conformance from synthetic wiring; populate real-data results only after executing the protocol. Include negative findings and uncertainty.
10. **Limitations and ethics.** Retrieval omissions, stale evidence, source correlation, identity harm, privacy/ACLs, generated summaries, token/latency approximations and external validity.
11. **Reproducibility and conclusion.** Version manifest, graph snapshots, exact observation receipts, authorized replay, implementation artifacts and supported contribution claims.

## Primary-source references

[R1] Darren Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, arXiv:2404.16130, abstract/version record: https://arxiv.org/abs/2404.16130 (v2 dated 2025-02-19; accessed 2026-09-25).

[R2] Microsoft GraphRAG, *Local Search*: https://microsoft.github.io/graphrag/query/local_search/ (accessed 2026-09-25).

[R3] Microsoft GraphRAG, *Global Search*: https://microsoft.github.io/graphrag/query/global_search/ (accessed 2026-09-25).

These references support background attribution only. The uploaded project's original source manifest and TypeSafe/Jev references are preserved; they are not represented as newly revalidated provider conformance.
