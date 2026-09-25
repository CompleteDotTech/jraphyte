# 3. Intermediate representations and compatibility contracts

## 3.1 Preserve the original representations

Do not create a second incompatible graph store. Preserve Evidence, Candidate, Decision and Mutation as the foundational record families. The Graph IR is the versioned manifest tying those families, schema identity, graph snapshot, resolution and ledger together. Question Pack and Resolution are additional records, not replacements for Candidate or Decision.

The executable schemas are standalone JSON Schema 2020-12 documents. Each prohibits unknown top-level fields and supplies a version identifier. JSON Schema establishes local shape; `tools/validate_package.py` adds selected cross-record checks. Referential integrity, temporal ordering, probability sums, source substring equality and authorization cannot all be delegated to a schema declaration.

| Representation | Essential contract | Legacy mapping |
|---|---|---|
| Evidence IR | Candidate-relative assessment of an immutable source/version/span; integrity, source family, temporal and semantic tags | Preserve `evidence()`; attach sidecar assessments instead of changing frozen source bytes |
| Candidate IR | Exact proposed assertion or identity/type/schema alternative, evidence and prerequisite references, lifecycle status | Preserve `candidate()` shape when lowering supported assertions |
| Question Pack | Dependency-stage state, exact questions, ordered alternatives, scope/snapshot/model and context accounting | New scheduler/adapter layer, not a `GraphStore` responsibility |
| Decision IR | Raw typed answer plus model/request/question/state identity, calibration and policy metadata | Preserve `bind()`'s exact assertion binding; add immutable receipt sidecars |
| Resolution IR | Selected action or abstention/acquisition with alternative, dependency, risk and policy references | Generalize the role above `select_identity()` without redefining its original behavior |
| Mutation Plan | Explicit proposed operations, expected state, evidence/decision refs and authorization/qualification state | Lower to existing `commit`, `retract` or `migrate` only after trusted preflight |
| Graph IR | Manifest of all run records and immutable snapshot/schema identities | Exports/reference index, not a competing graph engine |
| Ledger Event | Stage-specific payload hash, parent event hashes and previous event hash | Link upstream events to the existing atomic graph journal |
| Risk Policy | Versioned per-operation risk and qualified decision rules, or explicit analysis-only behavior | Preserve legacy `Policy` for frozen replay; introduce a qualified policy adapter for new runs |

## 3.2 Evidence addresses

The baseline source span uses Python string indexing. The revision therefore specifies zero-based Unicode-code-point offsets with an exclusive end: `quoted_span == snapshot_text[start:end]`. The hash addresses the exact UTF-8 encoding of that stored text. A separate raw-document hash identifies original bytes when a parser produced a text representation. Do not apply text offsets to PDF bytes, a differently normalized string or another source version.

For parsed documents, retain `representation_id`, parser version and the source-to-text locator mapping. Normalized text used by a model is a new representation, not a silent replacement for the original quote. Structured records may be rendered into deterministic textual projections, with the original field paths and conversion version preserved.

Semantic evidence assessments are candidate-relative and versioned. One source can support candidate A and contradict candidate B. Evidence tags do not independently grant write permission. A hash chain does not authenticate the publisher or prevent a privileged administrator from rewriting all local history.

## 3.3 Questions are semantic programs

A question contract consists of task family, instruction structure, primitive, ordered criteria, referenced state fields, candidate target, expected semantic interpretation, dependency requirements and program version. Changing any element is a semantic program change. Preserve exact rendered requests, not just a human-readable template name.

The package's question schema uses ordered arrays for criteria even where the provider serializes a map. This preserves option presentation for hashing and replay. The adapter lowers Choice options to the provider's criteria map, Score options to the ordered level array and Noul descriptions to true/false criteria. Repeated questions need distinct traceable IDs, but IDs themselves cannot carry information omitted from instructions [T2].

Question dependencies are scheduling dependencies. Statistical dependence is retained as a separate research concern. A later question requiring an earlier answer must use a new pack with that answer in its bound state. A large shared pack is not allowed to smuggle in answers that do not yet exist.

## 3.4 Decision fields and error representation

The revised decision contains `decision_id`, `candidate_id`, `question_id`, `question_schema_version`, `question_hash`, `state_hash`, `request_hash`, `evidence_refs`, provider and requested/returned model IDs, execution mode, raw answer, distribution, raw confidence, semantic outcome, confidence band, calibration reference, policy score, policy/resolver versions, timestamp, latency, cost, request ID, parents, supersession and abstention reason.

Choice and Score raw confidence are preserved exactly as observed. For Noul, raw confidence is null; the application may later attach a calibrated uncertainty band with its own provenance. The binary distribution `{YES:p, NO:1-p}` is an explicitly derived representation of a Noul, not a second model response. Score keeps its expected value and complete ordered distribution; no category is inferred by rounding.

An ERROR decision carries operational status and an error receipt without invented semantic probabilities. Legacy records with missing provider or exact-version evidence remain replayable as historical observations but are not silently promoted into a newly qualified policy population.

## 3.5 Graph assertions and proof structure

Within an assertion, all listed evidence and prerequisite assertions are required: AND semantics. Multiple separately accepted assertions can be alternative proofs of one displayed edge: OR semantics. A source withdrawal invalidates the assertions requiring that source, then their dependents. A view remains if another valid proof supports it.

Document-to-claim support, record equivalence and direct domain relations are different predicate contracts. Maintain direction, canonical inverse, symmetry, allowed endpoint types and qualifiers. Nonexclusive relations must not be forced into one Choice distribution. Inferred transitive edges require explicit inference-rule and premise records, even if the relation has a transitivity annotation.

## 3.6 Compatibility adapter: proposed integration, not implemented here

Implement new-run records alongside the existing core. The trusted adapter should resolve an accepted Candidate IR to the exact legacy `candidate()` bytes, validate its Decision IR and policy qualification, then use `bind()` and construct an explicit plan. Commit lowering can call `GraphStore.commit`; withdrawal lowering can call `retract`; reviewed schema updates can call `migrate`.

A v0.2 Decision IR must not be blindly inserted into the old fact dictionary: the current engine deliberately rejects unknown assertion fields [B4]. Store expanded decision/evidence metadata in sidecars referenced by IDs and hashes, or create a carefully versioned migration after tests. Do not remove strict legacy validation merely to make new fields fit.

Keep the original frozen `Policy` and replay adapter unchanged. A new qualification adapter must not claim that the legacy numerical threshold itself establishes calibrated risk. The new path is disabled for automatic consequential writes until qualification and backend integration tests pass.

## 3.7 Capability declaration

Report each constraint as `IMPLEMENTED`, `DELEGATED`, `UNSUPPORTED` or `NOT_APPLICABLE`, with implementation/version and a result. The inspected core implements exact qualifier-map equality rather than general interval reasoning. Temporal overlap, cardinality, full ontology consistency, RDF shape validation and property-graph backend migration need separate integration. Unknown required capabilities produce an unresolved plan, not PASS.

Local package checks cover data contracts and selected fail-closed invariants. They do not execute the existing database engine, implement a production resolver, authenticate reviewers, or prove complete constraint coverage.


## 3.8 Request-level accounting

A Question Pack carries request-level usage and latency. Decision costs may be null or explicitly allocated shares; never sum full request cost once for every question. Retain billed usage separately from tokenizer estimates. The Resolution IR has an optional search trace containing beam parameters, alternative paths, score types and pruning reasons. A null search trace means hierarchical exploration was not used; it does not mean zero uncertainty.
