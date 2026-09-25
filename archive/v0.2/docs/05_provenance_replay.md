# 5. Provenance, mutation protocol and replay

## 5.1 Complete lineage

The lineage path is source snapshot → parsed representation → retrieval receipt → candidate → admission/tagging → evidence closure → question pack → raw decision receipt → resolution → constraint results → mutation plan → graph transaction → accepted view. Rejected and abstained paths remain recorded rather than disappearing from the research denominator.

Use immutable identities and content hashes. Record both graph provenance and decision provenance. Map snapshots/assertions to PROV entities, processing steps to activities and models/services/reviewers to agents where an explicit PROV export is implemented [W2]. The package specifies that mapping but does not claim an executable PROV serializer.

A global append-only event order can support simple replay while parent-event references retain the dependency DAG. Store wall-clock and monotonic timing where available, process/run identity, versions, input/output hashes and previous-event hash. A hash chain detects changes relative to trusted anchors; it is not an authentication mechanism against an attacker who can rewrite every local record. Optional external signatures or anchored audit checkpoints are separate application controls.

## 5.2 Privacy and scope

Exact replay needs source and request bytes, but keeping all text indefinitely may be inappropriate. Record access classification and retention policy. Store secrets outside prompts and logs. If evidence must be removed, retain permitted metadata and a tombstone explaining why exact reconstruction is no longer possible; do not claim byte-exact replay after deleting necessary bytes. A redacted derivative is a distinct representation with its own hash.

## 5.3 Proposed plan lifecycle

```text
DRAFT → RESOLVED → PREFLIGHT_VALIDATED → AUTHORIZED
      → COMMIT_RECHECK → COMMITTED
      → ABSTAIN / REJECTED / STALE / REVIEW_REQUIRED / FAILED
```

The package's synthetic fixture stops at DRAFT and ABSTAIN. Future runtime integration must use the trusted planner and transaction engine to advance states. Schemas alone cannot confer authorization.

A plan includes the expected graph version and schema hash, operation list, explicit evidence/decision/assertion references, prerequisite checks, effective risk, policy/calibration identity, authorization state, and a compensation strategy. No arbitrary Cypher, SQL or executable migration text from a model is accepted as an operation.

Preflight resolves references and computes the affected dependency subgraph. Immediately before publication, recheck source activity, prerequisite activity, current schema, policy version, access rights, idempotency and graph version inside the atomic boundary. A preflight PASS does not remain valid after a concurrent graph change. Source activation/withdrawal must participate in the same transactional registry or an explicitly coordinated revocation-epoch protocol; an unlocked read from a separate service does not establish an atomic source-validity guarantee. Where coordination is unavailable, the contract is only validity as of a recorded source snapshot, with subsequent withdrawal handled as a new repair event. Replan on stale versions; do not silently update the expected version without reevaluating changed dependencies.

The existing store already supports atomic graph-state and journal publication with `BEGIN IMMEDIATE`, version checks and idempotency [B4]. Extend around that mechanism instead of creating a parallel transaction authority. Future scalable backends must demonstrate equivalent invariants independently; full JSON snapshots in the current research store do not establish production performance.

## 5.4 Reversible graph updates

Keep original record identities and assertions. A merge is a derived equivalence view based on active identity assertions and cannot-link constraints. Withdrawing a mistaken identity bridge recomputes the affected view rather than reconstructing deleted records.

Within one assertion, evidence and prerequisite lists are conjunctive. Multiple assertions backing an accepted view are alternatives. For withdrawn roots `R`, repeatedly add assertions depending on any root until a fixed point, then deactivate those assertions atomically. An independently supported view survives. Missing dependency declarations cannot be magically recovered; measure declaration completeness and test it explicitly.

Retraction and restoration are different operations. A later restoration requires a new assertion/decision or validated reactivation policy, not erasure of the retraction event. Compensating operations bind current state and may differ from an old plan's naive inverse after intervening writes. Schema migrations require a reviewed target schema, impact report and shadow validation of active assertions.

## 5.5 Four replay modes

| Mode | What is held fixed | What changes | Valid claim |
|---|---|---|---|
| Artifact reconstruction | Stored evidence, requests, responses, program/runtime and initial state | Nothing semantic | Reconstruct the recorded compiler result to the documented byte or semantic equality criterion |
| Frozen-observation policy replay | Exact prior semantic observations and their inputs | Thresholds or resolver rules not requiring missing judgments | Counterfactual policy output conditional on those observations |
| Semantic rerun | Source snapshot and declared input population | Model, question wording, menu, closure or evidence | New model observations; not reuse of old answers |
| Closed-loop graph rerun | Initial state, source sequence and external experiment controls | Policy/model effects on accepted graph, later retrieval and later candidates | End-to-end alternate trajectory with newly evaluated downstream dependencies |

Changing a source, candidate, question or state invalidates cached observations touching that change. A policy replay can reuse unchanged observations only when the new policy requires no missing inputs. Removing a question that also influenced later retrieval demands a closed-loop rerun, not merely deletion of one feature column.

A new model version needs actual new inference unless the result already exists under an exact matching cache key. No provider determinism is presumed. Fresh repeated calls form a separate variability study. Record stored-request reconstruction separately from semantic equality of graph views and byte equality of serialized artifacts.

## 5.6 Replay manifest and comparators

Bind run ID, parent run, intervention, initial graph snapshot/hash, source manifest, question program, provider/model versions, closure and packing versions, resolver/policy/calibration identities, compiler commit, runtime/dependency lock, canonicalization version, seed where meaningful, response receipts, cost/latency and execution mode.

A comparison reports added, withdrawn, changed and unresolved assertions; identity-component changes; affected source/decision lineages; coverage and semantic error changes when independent labels exist; and rerun cost. Preserve both branches. Deterministically select comparison order and distinguish an observed counterfactual from a speculative unexecuted forecast.

## 5.7 Cache rules

A conservative semantic cache key hashes provider and exact model; exact state bytes; exact questions and ordered criteria; program and parser versions; evidence/source versions; relevant graph/schema snapshot; and execution settings. Tenant/access scope also partitions caches. Recorded synthetic fixtures cannot satisfy live inference cache lookups. Cache hits retain the original observation receipt and create a new reuse event, not a fabricated new API request ID.
