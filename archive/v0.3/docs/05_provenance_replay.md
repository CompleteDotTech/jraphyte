# Lifecycle, transaction lineage and replay

## Authoritative lifecycle

The current projection is:

`DRAFT → RESOLVED → PREFLIGHT_VALIDATED → AUTHORIZED → COMMIT_RECHECK → COMMITTED`

DRAFT/RESOLVED may terminate as ABSTAINED or REJECTED; intermediate nonterminal stages may reject. Terminal states cannot advance. PREFLIGHT_VALIDATED requires every implemented required check to pass and a receipt reference. Authorization and commit require receipt references. The `Lifecycle` class is a local append-only hash projection; setting it is **not authority**. The service and actual atomic backend receipts determine whether publication occurred.

## Atomic boundary

Immutable plan content is separate from lifecycle events. The service checks exact plan/policy identity, current graph/schema version, source epochs/read permission, typed operations, component feasibility, complete batch publication, qualification and signatures under the same transaction that persists the accepted graph and journal. A preflight receipt cannot replace commit-time rechecks.

Graph, source status, immutable record sidecars, lineage anchor and journal update atomically. Retries with an existing key and identical plan return the original receipt without replaying writes. Reusing the key for changed content fails. A successful historical retry does not reactivate an assertion invalidated by a later withdrawal.

## Validation profiles

PARTIAL_ANALYSIS permits incomplete lineage and grants no authority. FINALIZED_ANALYSIS requires every included record to appear once in a valid causal ledger. FINALIZED_PUBLISHED additionally requires non-synthetic mode, a complete atomic transaction receipt, exact plan/authorization/preflight binding, a precommit provenance anchor and a root signed by an independently trusted issuer. HISTORICAL_REPLAY preserves exact source attribution without requiring those sources to be currently eligible for a new evaluation or mutation.

Ledger sequence/parent order establishes causal ordering. Event timestamps also record artifact times, which need not be monotonically ordered across independently constructed artifacts. The current-state source-status snapshot is explicit. Complete coverage includes source snapshots, policies and qualifications. The root excludes its own checkpoint identity to avoid recursive hashing. Hash chains without trusted roots or persisted anchors do not establish authorization.

The actual transaction stores its precommit ledger prefix. Exporters must preserve that prefix when producing a FINALIZED_PUBLISHED bundle; rebuilding a different prefix is not a substitute for the atomic receipt. `make_bundle(..., ledger_prefix=...)` supports this operation.

## Policy replay and erasure

Frozen-observation policy replay appends new evaluations and policy records; it does not change raw observations or invent inference calls. The CLI emits an unsigned analysis branch, not a new publication authorization. Old policy branches remain attributable in the same catalog.

Withdrawal and permission denial increment source epochs and deactivate all dependent assertions. Evidence/dependencies inside one proof are AND requirements. Separate assertions supporting the same edge are OR alternatives. Identity views are computed reversibly from active assertions. Restoring a permission never silently reactivates past assertions.

The reference backend supports authorized tombstones and removal of source-derived cached records. An intentionally erased byte history cannot support exact replay; it reports REPLAY_CONTENT_UNAVAILABLE instead of manufacturing replacements. This is scoped local cache deletion, not a promise to erase every external copy, derived personal datum, backup, or upstream journal. The pinned bridge has additional upstream retention constraints documented in `14_deployment.md`.
