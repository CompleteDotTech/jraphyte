# 1. Canonical architecture specification

## 1.1 Objective and preserved foundation

TRACE-GC is an evidence-gated, uncertainty-aware graph compiler. It transforms proposed semantic structures into explicitly justified, reversible graph mutations. Candidate generators discover possibilities; bounded models judge semantics; a resolver coordinates competing possibilities; deterministic validators enforce declared constraints; an authorized transaction engine alone changes accepted graph state.

This is a revision of the existing design, not a replacement. Preserve the heterogeneous candidate generators, Graph IR, global dependency resolution, transactional graph publication, provenance, event-driven auditing and staged schema evolution described in the earlier report [B1]. Preserve the concrete durable store, exact assertion binding, predicate outcome contracts, non-destructive identity views and dependent-assertion retraction already present in the inspected implementation [B2–B4].

The system must distinguish four different questions: does the quoted source exist; is the source authentic; does that source support this assertion; and is the assertion actually true in the world? A content hash addresses only integrity relative to a stored representation. A semantic support judgment does not answer the other three questions automatically.

## 1.2 Authority boundaries

| Component | Owns | Must not own |
|---|---|---|
| Parsers and source store | Immutable representations, offsets, hashes and retrieval receipts | Semantic truth certification |
| Candidate generators | Proposed entities, predicates, properties, matches and schema alternatives | Accepted graph writes |
| Evidence admission and tagging | Deterministic integrity checks plus fallible relevance/support/risk annotations | Tool permissions or final acceptance authority |
| Closure planner | Declared dependencies, bounded context and snapshot binding | A claim of universally minimal semantic context |
| Packing planner | Scheduling independent questions sharing compatible state | Statistical independence assumptions |
| Jev or alternative judge | Typed semantic observations over supplied state | Orchestration, arithmetic, constraints, credentials or side effects |
| Synthesizer/resolver | Alternative selection, global consistency, abstention and acquisition requests | Bypassing deterministic validation |
| Constraint compiler | Declared structural, temporal and policy checks | Inferring real-world truth from valid structure |
| Mutation planner | Explicit, immutable proposed operations and preconditions | Direct database access on a model's behalf |
| Transaction engine | Authorization, fresh snapshot checks and atomic publication | Trusting model-supplied validation receipts |
| Research controller | Offline experiments and candidate program versions | Editing production questions or thresholds without promotion |

A generative model may help propose an explanation, a new ontology name or a migration candidate. These outputs return to candidate status. A human review similarly adds an attributable decision; it does not bypass graph invariants, access controls or source integrity.

## 1.3 Two related but distinct graphs

Maintain an **evidence and decision graph** containing source snapshots, candidate assertions, typed decisions, supporting and contradicting passages, dependency links, rejected alternatives, transactions and research lineage. Maintain an **accepted graph view** derived from qualified active assertions. Storage can share one backend, but the two views must have different query contracts.

A proposed claim is not accepted merely because it has a node. A rejected or contested claim can remain in the evidence graph. A graph-native predicted link remains a hypothesis unless an explicitly permitted inference rule or qualified evidence path licenses it. Every derived assertion needs its own derivation record and prerequisite references.

For the existing SciFact-derived use case, retain `Document → supports|refutes → Claim` semantics. Do not reinterpret those links as newly extracted biomedical relations. For identity, retain original records and compute a reversible equivalence view; do not delete source records or permanently rewire every edge [B3–B4].

## 1.4 Evidence Firewall: admission, then candidate-relative tagging

The requested Evidence Firewall has two stages. **Admission** verifies readable immutable snapshots, correct source versions, valid spans, tenant permissions and retrieval policy. **Tagging** makes candidate-relative judgments about relevance, support, contradiction, temporal applicability, duplication and instructional content. A bounded semantic model may perform tagging after minimal deterministic admission; this resolves the apparent circularity of placing semantic evidence assessment before the main semantic decision layer.

Use orthogonal axes rather than one mutually exclusive label. One passage may simultaneously support part of a claim, contradict another part, be a duplicated source and contain an adversarial instruction. Preserve the requested category names as tags. Record the classifier and question version producing each semantic tag.

`CONTRADICTING_EVIDENCE` is useful evidence, not a reason to discard a passage. Deduplicate shared origins without erasing alternate retrieval paths. An old source can remain applicable to a historical claim. `STALE_OR_OUT_OF_SCOPE` must be justified relative to the asserted time and scope, not document age alone.

The classifier is not an impenetrable security boundary. Source text remains untrusted even after a benign label. Control instructions, tool permissions and database credentials never originate in retrieved passages. Retrieval execution is subject to application-level destination restrictions, size/time budgets and access checks. Model recommendations cannot relax those restrictions. These are proposed engineering controls, not capabilities provided by the Jev API.

The output is an Evidence IR containing an immutable span reference, deterministic integrity status, candidate-relative semantic tags, source-family metadata and explicit unresolved issues. Invalid or unavailable evidence cannot enter an automatic accepted-fact path. Quarantined material may remain available to an authorized analyst.

## 1.5 Minimum Evidence Closure

Define a question's initial requirement set `R(q)` from its versioned question contract: candidate fields, source spans, ontology fragment, entity alternatives, time qualifiers, declared prior assertions and policy context. Let `deps(x)` return declared dependencies. Compute the least fixed point:

```text
C0(q) = R(q)
C(k+1)(q) = Ck(q) union deps(Ck(q))
stop when C(k+1)(q) = Ck(q)
```

This is a dependency closure, not a proof that the model has every semantically relevant fact in the world. The term Minimum Evidence Closure denotes a design objective and a reproducible declared-dependency contract. Determining the smallest semantically sufficient subset remains an empirical research question.

A valid closure binds a graph snapshot, schema version, source versions, candidate revision and completed upstream decisions. Preserve negation, reference resolution, temporal qualifications, contradictory passages and required entity identifiers. Graph facts used as context carry their assertion status and provenance, so a hypothesis does not become self-confirming evidence.

Remove material only through a logged relevance or dependency decision. A closure budget failure causes partitioning with explicit cross-pack dependencies, retrieval refinement or abstention. It must not silently truncate a required passage. Store the dependency manifest, omission reasons, completeness status and serialized state hash.

## 1.6 Question Packing Planner

Construct a directed graph of question dependencies. Questions whose answers feed other questions cannot occupy the same independent evaluation stage. Within a stage, group questions by compatible closure, security scope, model version, question program and snapshot. Exact shared-state groups are the initial safe implementation; more aggressive union-of-closures packing is a later experiment with an explicit contamination budget.

All references needed by a question belong in its instructions and state. Do not rely on a question-map key to communicate the entity pair or claim target [T2]. Preserve the rendered instruction, ordered option menu, serialized state and request hash. Two requests differing in any of these are different semantic inputs.

Apply the current provider's separate total-request and state-plus-longest-question budgets. The example contract uses conservative operational caps of 64,000 and 32,000 tokens derived from the documentation's 64k/32k limits, not a claim about the provider's internal tokenizer [T1]. Production token estimation must have an identified estimator and margin; synthetic fixture counts are not valid production accounting. Do not assume a 255-question request limit merely because Choice has a 255-option limit [T2].

Packing reduces repeated context only when evidence sharing is real. Measure serialization overhead, question-specific rubric size, latency, failure/retry cost and decision disagreement against unpacked calls. Questions can be runtime-independent while statistically correlated. Keep both distinctions explicit.

## 1.7 Typed semantic judgments and Decision IR

Jev remains a replaceable semantic backend. The adapter preserves the exact request, returned model identity, raw answer, probability distribution, optional raw confidence and operational status before deriving any policy result.

Use Choice for mutually exclusive nominal alternatives such as SUPPORTS, CONTRADICTS and NOT_ENOUGH_INFO within a well-defined claim-span task. Use separate questions for compatible predicates or independently true propositions. Use Score only for genuinely ordered rubrics; its mean is not an observed category. Use Noul for a proposition, with application-derived uncertainty bands kept separate from vendor fields [T2–T4].

An HTTP failure, malformed answer or missing question result is an operational event, not a semantic negative, uncertainty probability or evidence of absence. Fail closed for mutations, retain the error receipt and retry only within an explicit budget. Do not silently renormalize invalid distributions or fill missing probabilities with neutral numbers.

Pin both the model request and expected returned model identity in evaluated programs. A version mismatch invalidates qualification rather than silently inheriting thresholds. Record whether the response was live, recorded or synthetic. A synthetic fixture may imitate the response shape but cannot count as a model observation.

## 1.8 Synthesizer/resolver

The resolver receives Decision IRs, admissible evidence and hard constraints. Its outputs are ACCEPT, REJECT, ABSTAIN, RETRIEVE_MORE_EVIDENCE, HUMAN_REVIEW or CONFLICT_UNRESOLVED. ACCEPT means a candidate is eligible for planning, not committed.

Resolve global identity consistency before using local pair judgments as equivalence relations. A high-scoring A–B match and B–C match cannot override a trusted A–C cannot-link. Preserve competing hypotheses and their evidence rather than averaging them into one supposedly coherent graph probability. A deterministic or learned ranking score can prioritize candidates, but only a separately validated statistical model may label an aggregate a probability.

For hierarchical placement, retain the top `K` feasible alternatives subject to depth, cost and expansion limits. Keep per-step distributions and full candidate paths. A path score is a search score unless separately calibrated. The versioned search configuration must name `beam_width`, `depth_limit`, `minimum_branch_score`, `maximum_expansion_cost`, `maximum_expansions` and `early_stop_policy`. Log every retained and pruned path with its parent, evidence/decision references and pruning reason; require explicit application budgets rather than hidden defaults. Ontologies may be DAGs or multi-label systems: do not force every case into one tree leaf. Include explicit no-match, unresolved and out-of-vocabulary outcomes.

A structured acquisition request names missing evidence, preferred source classes, candidate and question IDs, remaining budget and stop conditions. Repeated identical unresolved requests terminate. Absence from a retrieval shortlist does not establish a new entity. A human reviewer is the final escalation for unresolved or policy-restricted cases, not the destination of every ambiguous local judgment.

## 1.9 Deterministic constraints and transactional publication

Apply constraint checks twice: during plan construction and against current state inside the authorized transaction boundary. Preserve existing domain/range, inverse, symmetry, cannot-link, active prerequisite and exact-scope incompatibility behavior [B4]. Explicitly identify which additional constraints are implemented, delegated to a backend or unsupported.

Do not conflate RDF entailment, RDF validation and property-graph constraints. SHACL validates a graph against declared shapes; PROV-O supplies a provenance vocabulary [W1–W2]. Neither citation establishes that the existing prototype is a complete SHACL processor, OWL reasoner or PROV-O serializer. Arithmetic, interval overlap, keys and referential integrity remain deterministic application/backend duties.

A plan carries exact operations, expected graph/schema versions, source status requirements, assertion and decision references, risk classification, qualification artifacts and authorization state. The transaction engine recomputes preconditions from trusted stores. A model-produced string saying PASS is not a validation receipt.

The engine publishes accepted state and journal entry atomically, or publishes neither. Idempotency fingerprints bind the operation, policy and expected version. A changed payload with a reused key is rejected. Compensating transactions repair later-discovered errors without erasing intervening history. Destructive schema changes require shadow execution, impact analysis and explicit approval.

## 1.10 Conditional invariants and limits

The architecture aims to maintain: every accepted assertion has active traceable evidence or an explicit authorized derivation; every consequential operation passes current deterministic validation; unsupported calibration cannot authorize automatic semantic writes; every inference request and policy decision remains attributable; and revoked support invalidates dependent assertions while preserving alternative independent proofs.

These are conditional software invariants. Their force depends on correct validators, complete dependency declarations, reliable transactions and effective authorization. They do not prove semantic correctness or robustness against an administrator rewriting the entire trusted store. Model uncertainty, retrieval omissions and missing real-world evidence remain substantive failure modes.

## 1.11 Controlled self-improvement

The live compiler consumes an immutable promoted question-set version. Offline research consumes labeled development errors, proposes new questions, tests their incremental value, assesses redundancy and submits a candidate program. Independent calibration and release validation occur before promotion. Final test data do not feed question discovery, thresholds or stopping decisions.

The project may become self-improving through evaluated program revisions; it must not self-authorize new policies. Model upgrades, new question menus, altered closure/packing rules or changes in source population can all invalidate prior calibration. Event-driven auditing prioritizes affected assertions rather than rereading the entire graph continuously.
