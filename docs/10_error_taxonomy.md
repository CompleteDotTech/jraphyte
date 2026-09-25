# Structured errors

Public compiler and validation boundaries raise `ContractError(code, detail, path)`. The CLI writes a JSON error and exits nonzero. Malformed JSON rejects duplicate keys, nonfinite numbers, invalid Unicode, unsupported values and resource excess rather than silently normalizing them. Schema validators are cached and resolve no untrusted remote references.

Representative diagnostic families: MATERIALIZATION_MISMATCH / CLAIM_BINDING / PROVENANCE_MISMATCH; CLOSURE_INCOMPLETE / MISSING_REFERENCE / REFERENCE_TYPE / DEPENDENCY_CYCLE; PREREQUISITE_NOT_COMPLETED / PREREQUISITE_SNAPSHOT / TEMPORAL_ORDER; RUBRIC_MISMATCH / DISTRIBUTION_LABELS / MODEL_VERSION_MISMATCH; SOURCE_PRECONDITION / STALE_SOURCE_EPOCH / STALE_GRAPH_VERSION; OPERATION_CANDIDATE_KIND / RISK_UNDERCLASSIFIED / SCHEMA_IMPACT / PARTIAL_RESOLUTION_PUBLICATION; UNQUALIFIED_POLICY / QUALIFICATION_SCOPE / SIGNATURE_INVALID / AUTHORIZATION_BINDING; LEDGER_COVERAGE / CHECKPOINT_UNTRUSTED / BACKEND_AUDIT; RUN_BUDGET_EXHAUSTED / REPLAY_CONTENT_UNAVAILABLE / UPSTREAM_PIN_MISMATCH.

Exact codes are exercised by the tests. Unexpected programmer or system failures must not be converted into successful validation. TypeSafe operational failures and invalid answers are retained as immutable ERROR observations with their raw response rather than rewritten into semantic agreement. Legacy fixture errors use that compatibility checker's separate normalized exception type.

## Retrieval failures

The executable additions in `retrieval/contracts.py` are ENTITY_NOT_RETRIEVED, RELEVANT_EDGE_NOT_RETRIEVED, RELEVANT_PATH_NOT_RETRIEVED, CONTRADICTION_NOT_RETRIEVED, WRONG_COMMUNITY_RETRIEVED, ONTOLOGY_CONTEXT_MISSING, PROVENANCE_CONTEXT_MISSING, HISTORICAL_CONTEXT_MISSING, IRRELEVANT_GRAPH_CONTEXT, GRAPH_CONTEXT_OVERLOAD, VECTOR_RETRIEVAL_MISS, GRAPH_TRAVERSAL_MISS, RANKING_FAILURE, STALE_GRAPH_CONTEXT, SUPERSEDED_FACT_USED, TEMPORALLY_INVALID_CONTEXT, RETRIEVAL_LOOP and RETRIEVAL_BUDGET_EXHAUSTED. The research proposal function consumes these labels; it does not infer a missing gold fact merely from an empty result. Live operational errors additionally retain their existing structured ContractError codes.
