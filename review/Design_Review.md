# TRACE-GC 0.2-design: design issues and recommended fixes

**Reviewed:** 25 September 2026  
**Input:** `TRACE-GC_Revision_Package.zip`  
**Assessment:** Keep the architecture; strengthen the executable contracts before adding more inference or optimization machinery.

## 1. Executive assessment

The strongest design choice is the separation of candidate generation, semantic observations, global resolution, deterministic checks, and authorized graph publication. Preserve analysis-only defaults, immutable source representations, reversible identity views, alternative-proof semantics, and the distinction between raw probability, policy score, and permission to act.

The main weakness is the gap between these written guarantees and what the current record schemas and cross-record validator establish. The package itself correctly describes its checks as a subset, not a production certification. This review identifies what that next subset should contain and which representation contracts need refinement before implementation.

I independently reran the supplied validator and unit tests. The sample bundle passed and **all 42 tests passed**. All **37 entries in the package manifest matched their recorded hashes and sizes**. I then constructed **18 additional synthetic probes**, each of which was accepted by the current validator. These are 18 test cases, not 18 independent vulnerabilities. Some expose direct cross-record inconsistencies; others show that complete-run or lifecycle guarantees need a stronger validation profile than a draft-fixture checker.

The probes deliberately recompute request and ledger hashes after changing synthetic input. This distinguishes a semantic/structural contract failure from ordinary tamper detection. It does not reproduce live inference, authorize publication, or show that a deployed graph can be compromised. The analysis-only publication block remained intact. No model calls, database commits, or modifications to the original source files were performed.

**Scope exclusions:** This archive does not contain the referenced legacy `GraphStore` implementation. I did not execute that engine, a live Jev adapter, backend concurrency tests, calibration experiments, or production security controls. Findings about those areas are contract/integration requirements, not observed failures of that external implementation.

## 2. Priorities

- **P0:** Resolve before these contracts are used to authorize automatic consequential writes.
- **P1:** Resolve for a reliable end-to-end research prototype and controlled pilot.
- **P2:** Engineering improvements after the correctness-critical path is executable.

## 3. Reproduced contract issues

### F01 — Model-visible state is not derived from verified evidence — P0

**Locations:** `schemas/question-pack.schema.json`, property `state`; `tools/validate_package.py:125–133,158–194,207–215`. **Probes:** P01–P03, with P08 as a related reference-consistency check.

The source span is verified and the state is hashed, but the validator does not establish that the verified span is the text actually placed in the model state. The state's schema is only `{"type":"object"}`. An empty state passes after rebinding its hashes. So does a state in which the verified joining statement is replaced by its opposite. The claim text can also change while the candidate still names the same `claim-demo` object.

These are different contracts: a hash establishes the identity of the supplied object, not that the object is the correct materialization of the source and candidate. In the fixture, the candidate binds a claim identifier rather than an immutable claim-content record.

**Fix:** Make state construction a trusted deterministic compiler pass. Materialize question-required fields from typed, immutable candidate, claim, evidence, and snapshot objects. For each rendered field, preserve its state path, source/reference identity, representation version, exact span or structured-field locator, and transformation version. Verify the materialization against trusted records before inference. Bind a claim identifier to an immutable claim-content hash. A permitted normalization is an explicit versioned transformation, not a freely replaceable quotation.

Define task-specific evidence requirements rather than requiring every question to cite every passage. Check that the decision's declared evidence agrees with those requirements and its bound pack.

**Acceptance:** Removing a required claim or passage, swapping passage text, or substituting the content behind a claim ID is rejected even when all caller-controlled hashes are internally consistent. An explicitly permitted, reproducibly derived normalization remains valid.

### F02 — Closure is shallow and current-source validation can be skipped — P0

**Location:** `tools/validate_package.py:167–175,214–215,268–277`. **Probes:** P04 and P09.

The design defines recursive dependency closure. The implementation collects pack candidates/evidence and one level of candidate evidence/prerequisite references. With A requiring B and B requiring C, a closure listing A and B but not C is accepted.

The active-source check iterates only over `pack.evidence_refs`. A probe withdraws the source and empties that list and the decisions' evidence lists, while leaving evidence in the candidate, closure, rendered state, resolution, and draft operation. Validation still passes. This is a gap in the offline freshness check, not a demonstrated commit bypass.

**Fix:** Compute required closure from versioned question contracts and typed dependency edges to a fixed point. Do not treat a supplied `closure_complete` Boolean as the proof. Generate a closure receipt recording roots, traversed dependency edges, required materializations, snapshot identity, and omissions. Check freshness/admissibility over the computed required set, not an independently editable convenience list.

Separate historical provenance validation from present-time commit eligibility: a withdrawal must not erase an old observation's provenance, but it must block new reliance on inactive support. Encode source-status snapshot or revocation-epoch references, as already contemplated in the prose.

**Acceptance:** Missing transitive prerequisites and inactive required support are rejected for new evaluation/publication. Historical observations remain reconstructable with their as-of source status.

### F03 — Only part of the dependency graph is checked — P0

**Location:** `tools/validate_package.py:142–156,176–184,214,247–256`. **Probes:** P05–P07 and P12–P13.

Candidate prerequisite cycles are checked. Cross-pack prior-decision cycles are not. A question can name a nonexistent question dependency; a decision can list itself as a parent; two packs can require each other's decisions. `supersedes` and resolution alternative references can also point to nonexistent records.

**Fix:** Introduce a shared typed-reference validator for all reference-bearing fields. Use fully scoped question identities such as `(run_id, pack_id, question_id)`. Explicitly distinguish data prerequisites, scheduling prerequisites, supersession, alternatives, and audit links; not every ordinary reference is a scheduling dependency. Validate acyclicity, completion, and temporal ordering on the appropriate dependency subgraphs. Require an upstream result to exist and be usable before its dependent pack becomes runnable, and bind its rendered content into state.

**Acceptance:** Forward/circular execution prerequisites cannot be marked runnable. Missing and wrong-type references fail with stable diagnostic codes. Legitimate noncausal links do not create false scheduling cycles.

### F04 — Mutation operations need distinct payloads and lifecycle rules — P0

**Locations:** `schemas/mutation-plan.schema.json`; `tools/validate_package.py:258–277`; `docs/05_provenance_replay.md:15–27`. **Probes:** P10–P11 and P17–P18.

All operations have essentially the same generic shape. An `ADD_IDENTITY_ASSERTION` operation targeting an ordinary document-support candidate passes if its risk class is raised to R4. Duplicate operation IDs pass. A resolution can claim R0 while its planned assertion operation is R2. A plan can be labeled `DRY_RUN_VALIDATED` while an implemented constraint reports `FAIL`.

There is also specification drift: the prose uses states including `RESOLVED`, `PREFLIGHT_VALIDATED`, `AUTHORIZED`, and `COMMIT_RECHECK`; the schema exposes `DRAFT`, `DRY_RUN_VALIDATED`, `READY`, `REJECTED`, and `COMMITTED` plus a separate authorization field. Different abstractions could be valid, but their mapping is not defined.

**Fix:** Use discriminated operation variants. Add-assertion operations should bind exact assertion content. Identity operations must bind identity candidates and a checked component change. Retractions need an unambiguous accepted-assertion target and expected revision. Schema migrations need a reviewed target schema and explicit impact/mapping artifact, not merely a generic triple. Enforce unique operation IDs and candidate-kind/predicate compatibility.

Specify one authoritative transition system. Keep immutable plan content separate from append-only lifecycle events and trusted authorization/validation receipts. A validated state requires successful required checks; a ready state additionally requires valid authorization and qualification; commit requires current-state rechecks. Compute effective risk from the operation and affected dependency set, then ensure all projections agree.

**Acceptance:** The four reproduced contradictions fail. Every allowed and forbidden transition has a test. Draft proposals may be incomplete, but cannot acquire a validated/ready status by setting a field. JSON Schema conditionals or `oneOf` can establish local variants; cross-record and authority checks remain runtime duties [R2].

### F05 — Ledger validity is not ledger completeness — P0 for finalized publication; P1 for prototype replay

**Location:** `tools/validate_package.py:279–291`. **Probes:** P14–P15.

Removing every ledger event while retaining all substantive records passes. A ledger event can also claim a different run and `LIVE` execution mode in an otherwise synthetic bundle. The checker verifies the hashes of events that exist; it does not verify required event coverage or run/mode consistency.

`all_records` excludes source snapshots, the graph manifest, and the policy, so the current payload-reference mechanism cannot directly cover those objects either. This does not disprove the planned upstream journal; it identifies missing executable lineage contracts.

**Fix:** Define separate partial-draft and finalized-run validation profiles. Finalized runs must bind source snapshot manifests, exact semantic observations, policy/qualification artifacts, relevant state, and the graph transaction receipt. Require record-to-event coverage according to stage, plus run/mode and causal-order checks. Design the root manifest without recursive self-hashing. Link to the backend's atomic graph journal rather than adding a second graph publication authority.

A chain rooted only in caller-supplied data is not an authorization mechanism. Use a trusted persisted anchor and, where required by the threat model, authenticated receipts or externally anchored checkpoints. The existing prose already recognizes this distinction; carry it into the runtime contract.

**Acceptance:** A finalized bundle with deleted events, missing source/policy bindings, or mixed run/mode provenance is rejected. Partial analysis bundles remain explicitly identifiable as incomplete rather than silently treated as replay-complete.

### F06 — The Score legend is checked by key, not by meaning — P1

**Location:** `tools/validate_package.py:241–243`. **Probe:** P16.

The Score legend's key set is checked, but its level descriptions are not compared with the requested rubric. Reversing a description while keeping its numeric index passes. TypeSafe documents the legend as the mapping from level numbers back to their descriptions [R1].

**Fix:** Validate the complete returned legend against the adapter's exact expected rubric representation, including a documented transformation when structured descriptions are serialized. Preserve a mismatched raw response as an operational error receipt rather than editing it into agreement.

**Acceptance:** Renamed/reversed level descriptions produce a rubric-mismatch error without discarding the original response. Keep the existing correct behavior: Score means are not rounded into categories, and Noul does not acquire an invented raw confidence field [R1, R5].

## 4. Architectural refinements

### F07 — Global resolution needs a component-level certificate — P1

**Locations:** `schemas/resolution.schema.json`; `tools/validate_package.py:247–253`; `docs/01_architecture.md`, section 1.8.

The design promises global identity consistency, but Resolution is candidate-centered and its direct decision references must all belong to that candidate. A global solver can still compute internally; the problem is that its multi-candidate reasoning does not have a first-class, auditable result contract.

Add a resolution-batch/component artifact that binds all candidate and observation inputs, cannot-links and other hard constraints, graph/schema snapshot, selected alternatives, solver/configuration version, objective interpretation, tie-breaking rule, and termination status. Per-candidate resolutions should be projections of this result. An unresolved or budget-exhausted solve is not a conflict-free solution.

Validate the entire proposed component change, not just individual pairs. Use affected-component size and dependent assertions in effective risk. For example, bridging two groups of 100 records implies 10,000 cross-group equivalences; that deserves a different impact assessment from a two-record match even when the initiating pair score is identical.

### F08 — Separate semantic observations from policy evaluations — P1

**Locations:** `schemas/decision.schema.json`; `docs/03_ir_contracts.md:37–43`; `docs/05_provenance_replay.md:39–60`.

Decision currently combines an immutable model response with policy version, policy score, policy result, resolver version, calibration reference, and abstention metadata. That makes frozen-observation policy replay harder to express without cloning or mutating an observation-shaped object.

Retain the Decision family, but give immutable observation receipts and derived policy evaluations distinct identities. One observation can then support multiple explicit policy-replay branches without appearing to be multiple model calls. Similarly, bind semantic candidate content separately from mutable lifecycle status so a bookkeeping transition does not accidentally imply that the model saw a different claim.

Define separate hashes for internal semantic IR, actual adapter-emitted request bytes, and cache identity. The current `request_hash` is computed from an internal question representation; it is not a demonstrated hash of a transmitted provider request. Capture exact wire request/response artifacts and adapter version when integration is implemented. Keep tenant scope and execution-mode partitioning in cache rules.

### F09 — Qualification and authorization need executable applicability contracts — P0 before automatic writes

**Locations:** `docs/04_risk_calibration.md:33–60`; `schemas/risk-policy.schema.json`; `schemas/mutation-plan.schema.json`.

The calibration prose is substantially stronger than the schema. The package has no qualification-artifact schema, and policy rules expose one scalar threshold per risk class without typed task/predicate/population applicability. An authorization enum is also only a claim until checked against a trusted issuer and operation scope.

Implement a qualification registry and an explicit applicability check binding task/predicate, source population, candidate generator, exact model, question program, materialization/packing rules, resolver, metric denominator, selected threshold, upper risk bound, minimum coverage, expiry, and drift status. Encode approvals as operation-scoped receipts binding the immutable plan hash, principal, permissions, required review, and validity interval. Do not let a model-generated record author these permissions.

Preserve the existing careful evaluation definitions and do not introduce arbitrary production thresholds. Test the policy after candidate selection and global resolution, not only the underlying classifier. Include random audits of automatically accepted actions rather than relying only on the cases already routed to review. This is a recommendation to reduce a foreseeable sampling blind spot, not a claim that the package has already run biased experiments.

Treat large identity components and highly consequential predicates separately where their approved risk objectives differ. Fail closed when a qualification artifact no longer matches the actual run. TypeSafe's current documentation also recommends pinning exact model versions when thresholds have been tuned against them [R4].

### F10 — Reproducibility needs a serialization profile and lifecycle-aware evidence IDs — P1

**Locations:** `tools/validate_package.py:40–56,118`; `docs/03_ir_contracts.md:21–27`; `docs/05_provenance_replay.md:52–60`.

The Python JSON serializer is deterministic within its chosen behavior, but a cross-runtime canonicalization profile and test vectors are not specified by that function alone. Explicitly decide whether to adopt JCS or a documented versioned alternative. Define number handling, duplicate-key rejection, Unicode/key ordering, array order, nonfinite-value rejection, and byte encoding. RFC 8785 provides an established JSON canonicalization scheme with explicit constraints [R3].

Make source-snapshot identity distinct from a logical source identifier. The fixture indexes sources only by `source_id`, which is sufficient for a single version per source in a bundle but not for a history containing multiple versions of the same document. Use snapshot/representation IDs or composite immutable keys for replay and maintenance.

Preserve original and derived text separately as the design already recommends. Test permission changes, withdrawal epochs, tombstones, and exact-replay loss after permitted deletion. Avoid making an archived observation invalid merely because its evidence is not eligible for a new commit today.

### F11 — Move a minimal end-to-end test earlier; defer optional optimization — P1/P2

**Locations:** `docs/08_roadmap.md`, phase table; `tools/validate_package.py:59–62,151–156`; `tests/test_contracts.py`.

The controlled pilot currently depends on the autoresearch phase. That expands the critical path before the fixed-question compiler has demonstrated a complete lifecycle. Make autoresearch optional for the first pilot. Similarly, do not require sophisticated beam search, union-of-closures packing, or schema evolution to prove a narrow fixed-schema evidence-link path.

Build one executable path with a fixed question program: source representation → candidate/claim binding → deterministic materialization → recorded or shadow observation → explicit resolution → validated plan → isolated backend transaction → replay and withdrawal. Test concurrency and source-status coordination in the actual backend boundary already described in the architecture; a fixture checker cannot substitute for those tests.

Promote invariant-based, stateful tests alongside example tests. Generate dependency chains and alternative proofs, then test withdrawal, concurrent update, interrupted commit, retries, idempotency-key reuse with changed payload, and replay. Stateful testing tools support generating action sequences and checking invariants [R6]. Keep all unsafe variants in isolated test environments.

Two code-level scaling improvements are straightforward: cache compiled JSON Schema validators instead of rereading and checking each schema per record; replace repeated full scans of candidate prerequisites with a queue-based topological traversal. The existing repeated-scan loop is quadratic on a long dependency chain; the queue-based algorithm can process vertices and edges once. This is an algorithmic observation, not a measured production performance result.

Also add a root bundle/source schema and structured error normalization before indexing arbitrary input. Share monotonic run budgets across retrieval, inference retries, solver expansion, and review rather than relying only on per-request budget fields.

## 5. Recommended implementation order

**Change set 1 — Make data binding and execution prerequisites verifiable.** Implement typed claim content, deterministic state materialization, recursive closure, complete typed-reference checks, and causal dependency validation. Preserve the existing 42 passing tests and add targeted regressions for the reproduced gaps.

**Change set 2 — Make the plan boundary coherent.** Introduce discriminated operations, one authoritative lifecycle, immutable plan hashes, trusted receipts, effective-risk consistency, and finalized-run ledger coverage. Test reviewed/deterministic transaction paths in an isolated backend without enabling synthetic semantic auto-acceptance.

**Change set 3 — Demonstrate a small, complete lifecycle.** Use a fixed-schema task and fixed question program. Show an accepted/rejected/abstained path, alternate-proof survival after withdrawal, idempotency, stale-version rejection, and reproducible replay. Validate the actual legacy adapter against its pinned checkout.

**Change set 4 — Qualify and optimize only the stable path.** Collect independent labels, perform matched-risk/coverage comparisons, implement applicability and drift checks, and conduct a bounded reviewed pilot. Add packing, a learned resolver, and autoresearch as separate measured interventions. Keep schema evolution and a scalable backend behind their own conformance gates.

## 6. Evidence and reproduction

`baseline_results.json` and `baseline_test_log.txt` record the independent baseline run. `probe_results.json` records all additional cases. `reproduce_findings.py` constructs the synthetic cases without modifying package files.

Run after extracting the original archive:

```sh
python reproduce_findings.py /path/to/trace_gc_revision --output probe_results.json
```

The reproduction script is a diagnostic harness, not a complete production conformance suite. Some finalized-run and lifecycle findings require adopting the corresponding stronger validation profile before they should become unconditional CI assertions. Hash refreshing is restricted to synthetic test construction and must never be substituted for real inference after changing semantic input.

### Probe inventory

| Probe | Synthetic change | Observed result |
|---|---|---|
| P01 | Pack state can be completely empty despite complete closure | ACCEPTED_BY_VALIDATOR |
| P02 | Rendered evidence can differ from the verified quoted span | ACCEPTED_BY_VALIDATOR |
| P03 | Rendered claim can change without changing the candidate assertion | ACCEPTED_BY_VALIDATOR |
| P04 | Declared closure omits a transitive candidate prerequisite | ACCEPTED_BY_VALIDATOR |
| P05 | Question names a dependency that does not exist | ACCEPTED_BY_VALIDATOR |
| P06 | A decision can list itself as a parent | ACCEPTED_BY_VALIDATOR |
| P07 | Cross-pack prior-decision dependencies can form a cycle | ACCEPTED_BY_VALIDATOR |
| P08 | A semantic support decision can omit every evidence reference | ACCEPTED_BY_VALIDATOR |
| P09 | Withdrawn support escapes the active-source check when omitted from pack evidence_refs | ACCEPTED_BY_VALIDATOR |
| P10 | Identity operation can target an ordinary document-support candidate | ACCEPTED_BY_VALIDATOR |
| P11 | Two operations can share an operation_id in one plan | ACCEPTED_BY_VALIDATOR |
| P12 | Decision supersedes points to a nonexistent decision | ACCEPTED_BY_VALIDATOR |
| P13 | Resolution alternative candidate reference does not exist | ACCEPTED_BY_VALIDATOR |
| P14 | All ledger events can be removed while retaining every substantive record | ACCEPTED_BY_VALIDATOR |
| P15 | Synthetic ledger event can claim another run and LIVE mode | ACCEPTED_BY_VALIDATOR |
| P16 | Score response legend descriptions can disagree with the question rubric | ACCEPTED_BY_VALIDATOR |
| P17 | Resolution risk can be lower than its planned ordinary assertion operation | ACCEPTED_BY_VALIDATOR |
| P18 | A plan can be DRY_RUN_VALIDATED while a required implemented constraint reports FAIL | ACCEPTED_BY_VALIDATOR |

## 7. External reference checks

External references support API/standards details and suggested tooling, not the observed local test results. Accessed 25 September 2026.

[R1] TypeSafe, *API reference*: Score levels, returned legend, probability-weighted Score, and typed answer contracts. `https://docs.typesafe.ai/api`

[R2] JSON Schema, *Conditional schema validation*: conditional subschemas and composition for local record contracts. `https://json-schema.org/understanding-json-schema/reference/conditionals`

[R3] RFC 8785, *JSON Canonicalization Scheme (JCS)*: an explicit interoperable JSON canonicalization profile. `https://www.rfc-editor.org/info/rfc8785/`

[R4] TypeSafe, *Models*: exact model version pinning, alias behavior, and the separate request/state-plus-longest-question budgets. `https://docs.typesafe.ai/models`

[R5] TypeSafe, *Confidence*: distribution-derived Choice/Score confidence; no separate Noul confidence field. `https://docs.typesafe.ai/confidence`

[R6] Hypothesis, *Stateful tests*: generated operation sequences and state-machine invariant testing. `https://hypothesis.readthedocs.io/en/latest/stateful.html`

## Bottom line

TRACE-GC does not need more architectural components before its next useful milestone. It needs a smaller executable safety boundary in which state materialization, dependency closure, global-resolution inputs, policy applicability, operation types, lifecycle transitions, and publication provenance agree mechanically. The present analysis-only block is worth preserving while those guarantees become executable.
