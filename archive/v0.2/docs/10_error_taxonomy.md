# 10. Error taxonomy

Keep the supplied semantic codes and add operational codes rather than folding failures into NOT_ENOUGH_INFO. An incident can carry multiple codes, one primary stage, severity, affected objects, evidence/decision references and a remediation version.

| Code | Primary class | Meaning | Diagnostic |
|---|---|---|---|
| ENTITY_FALSE_MERGE | Semantic/identity | Different entities accepted as equivalent | Cluster precision, merge blast radius |
| ENTITY_FALSE_SPLIT | Semantic/identity | Same entity remains incorrectly separated | Pair and cluster recall |
| WRONG_RELATION | Semantic | Incorrect predicate or direction accepted | Typed-edge precision |
| MISSING_RELATION | Discovery/semantic | Gold relation omitted or rejected | Candidate versus final recall |
| WRONG_ENTITY_TYPE | Semantic | Incorrect entity type assigned | Type precision/recall |
| WRONG_RELATION_TYPE | Semantic | Incorrect mapping to schema predicate | Relation-type accuracy |
| TEMPORAL_ERROR | Semantic/constraint | Incorrect interval or time interpretation | Scoped relation correctness |
| PROVENANCE_MISMATCH | Integrity | Source, representation, version or span differs | Integrity rejection rate |
| SOURCE_CONTRADICTION_IGNORED | Evidence/resolution | Applicable counterevidence omitted or suppressed | Contradiction handling and false commits |
| SCHEMA_VIOLATION | Constraint | Declared schema invalidated | Violation count by rule |
| LOW_CONFIDENCE_AUTO_COMMIT | Policy | Action accepted outside its qualified operating rule | Unauthorized/unsafe acceptance |
| ONTOLOGY_PATH_ERROR | Search | Wrong hierarchy/DAG placement retained | Hierarchical loss and recall |
| RETRIEVAL_FAILURE | Discovery | Required evidence absent from retrieved set | Evidence recall |
| IRRELEVANT_CONTEXT_CONTAMINATION | Evidence | Distractor evidence changes outcome incorrectly | Matched-context error delta |
| DUPLICATE_ASSERTION | Representation | Duplicate assertion identity or unintended duplicate fact | Duplicate and idempotency failures |
| STALE_EVIDENCE | Evidence | Source version/status no longer applicable | Freshness and withdrawal correctness |
| CANDIDATE_OMISSION | Discovery | Gold target not represented before adjudication | Candidate recall ceiling |
| PACK_DEPENDENCY_VIOLATION | Scheduling | Question requires another answer in the same independent stage | Rejected invalid pack count |
| PACK_BUDGET_EXCEEDED | Scheduling | Either request context budget exceeded | Overflow/split rate |
| CLOSURE_INCOMPLETE | Scheduling | Declared prerequisite missing or silently truncated | Closure contract violations |
| QUESTION_TARGET_AMBIGUOUS | Semantic program | Target exists only in map ID or unspecified state | Request-contract rejection |
| MODEL_VERSION_MISMATCH | Provenance | Returned version differs from qualification | Unqualified observation count |
| MALFORMED_DISTRIBUTION | Operational | Wrong labels, nonfinite values or invalid sum | Invalid response rate |
| MODEL_REQUEST_FAILED | Operational | Missing response, transport/rate/service failure | Failure rate and retry cost |
| UNQUALIFIED_POLICY | Policy | No matching independent qualification artifact | Automatic write blocked |
| STALE_GRAPH_VERSION | Concurrency | Graph changed since plan/preflight | Replan/abort rate |
| UNAUTHORIZED_MUTATION | Security | Request lacks effective authorized write capability | Denied write attempts |
| SOURCE_COPY_DOUBLE_COUNT | Evidence | Copied origins treated as independent evidence | Corroboration error |
| DEPENDENCY_UNDECLARED | Provenance | Required assertion omitted from dependency graph | Missed retraction/counterfactual changes |
| SCORE_MEAN_AS_CATEGORY | Semantic program | Expected ordinal value treated as selected nominal class | Program-contract violations |
| TEST_SET_LEAKAGE | Research | Locked evaluation data influenced optimization | Invalidated confirmatory run |
| COUNTERFACTUAL_CACHE_MISUSE | Replay | Changed semantic input reused an incompatible response | Replay invalidation count |

Failures from model input/output, application code and source quality need separate denominators. Record whether a code is independently adjudicated, deterministically detected, reviewer-assigned or model-suggested. The optimizer must not treat its own unverified error labels as gold.
