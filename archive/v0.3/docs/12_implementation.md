# Runtime implementation specification

## Serialization: TRACE-C14N-1

The hash input is ASCII `TRACE-C14N-1`, one zero byte, then a recursive typed encoding. SHA-256 is used. This is a documented alternative to JCS, **not RFC 8785 compliance**.

| Value | Encoding after the profile prefix |
|---|---|
| null | ASCII `n` |
| true / false | ASCII `t` / `f` |
| integer | ASCII `i`, decimal byte-length, `:`, signed decimal ASCII |
| float | ASCII `d`, then 8-byte big-endian finite IEEE-754 binary64 |
| string | ASCII `s`, UTF-8 byte-length, `:`, strict UTF-8 bytes |
| array | ASCII `a`, decimal element-count, `:`, encoded elements in order |
| object | ASCII `o`, decimal member-count, `:`, encoded key/value pairs sorted by UTF-8 key bytes |

Integers are restricted to ±(2^53−1). Integer, boolean and float types remain distinct. Float negative zero is retained; integer `-0` parses as integer zero. No Unicode normalization is implicit. Lone surrogates, nonstring object keys, duplicate JSON keys, NaN/Infinity, depth over 128 and input/canonical sizes over 16 MiB are rejected. JSON number tokens with decimal/exponent syntax parse as binary64; integer tokens parse as bounded integers. Cross-runtime implementations must preserve this distinction rather than parse every number identically. Number syntax such as `1e0` and `1.0` has the same float value, not the same type as integer `1`.

JSON is transport, not canonical hash syntax. `examples/runtime/canonical_vectors.json` specifies actual transport values, canonical byte hex and hashes. Raw source text and HTTP request/response bytes also have ordinary byte SHA-256 hashes, clearly separate from the record digest. Do not interchange these identifiers.

## State and closure

`compiler.materialize` starts from candidate roots and required prior observations plus an exact snapshot. It follows typed dependencies to a fixed point, including graph support evidence. Each displayed field has a record/hash/locator/transformation trace. Installed transforms are identity and versioned whitespace collapse; the latter changes rendered text only, not source bytes or evidence spans. Claims, candidate assertions and prior observations cannot be independently substituted in rendered state. Closure receipts enumerate roots, reached records, edge types, evidence, source snapshots, snapshot identity and omissions.

Candidate prerequisites and execution dependencies use queue-based topological traversal. Alternatives are contextual/noncausal links, not automatically prerequisite edges. Question IDs are scoped by run/pack/question and earlier answers must be complete, temporally preceding and snapshot/mode/scope compatible. The compiler and validator never accept a supplied “complete” flag as proof.

## Question and adapter contract

The installed program binds exact instruction/rubric content and version; new programs must be installed and versioned. Fixed semantic tasks are document support/refutation and identity, with auxiliary evidence-quality questions. Support Choice uses SUPPORTS/CONTRADICTS/INSUFFICIENT; identity uses MATCH/DIFFERENT/INSUFFICIENT. Score retains its probability-weighted mean and complete legend; it is not rounded to a category. Noul retains its single proposition probability and no invented confidence. The full probability distribution is never silently normalized.

The TypeSafe adapter emits exact JSON bytes, retains request/response base64 plus byte hashes, records errors, verifies returned model versions and signs observation attestations through a separately supplied signer. Headers recorded are restricted; authorization credentials are not persisted in receipts. Redirects are not silently followed with credentials. 429/529 retries are explicitly bounded and consume shared budgets; each failed response remains attributable.

Live inference is disabled by default. It requires an API key supplied by the application, LIVE mode, a pinned model, current source checks, an injected matching tokenizer, a run budget and observation signer. The default byte estimator is explicitly unqualified and cannot enable automatic production acceptance. The actual full wire request and state-plus-longest-question budget are rechecked using the configured counter. Responses over the configured maximum fail rather than consume unbounded memory; omitted excess bytes cannot be represented as exact replayable content. No real API request is made by tests or the demo.

## Resolution, graph semantics and limits

The resolver exhaustively searches a bounded candidate set, uses fixed integer utility and deterministic lexicographic tie-breaking, and checks each feasible combination against the shared graph constraints. It binds all input hashes, exact snapshot, alternatives, cannot-links and impact. More than 24 candidates, expansion exhaustion, or infeasibility produces an explicit unresolved status and no selected set. Even below that cap, the run budget can terminate search. This reference solver is not marketed as a scalable learned resolver.

Constraints include endpoint types, canonical inverse/symmetric relations, self-relation policy, scoped incompatibility, identity type compatibility/cannot-links, and AND prerequisite validity. Identity equivalence is transitive and views are reversible. The schema's general `transitive` metadata does **not** implement arbitrary recursive relation reasoning; only identity component closure is materialized. Deployments requiring arbitrary transitive predicates must add a separately versioned, tested reasoning capability rather than assume that flag proves it.

Certificate verification independently rechecks input binding, graph feasibility, impact, objective arithmetic and completed enumeration count. It does not independently rerun the full optimality search. Optimality labels are not trust/authorization credentials. Publication still requires current deterministic feasibility, applicable policy and trusted signatures.

## Storage and mutation

The reference backend uses SQLite WAL, FULL synchronous writes and BEGIN IMMEDIATE. Graph/schema version and source status checks execute inside the transaction. All six operation variants are tested. Records, source statuses, current graph, before/after hashes, authorization references, lineage prefix and journal are committed together. A fault at any tested commit stage rolls the transaction back; a valid retry uses persisted idempotency identity. Concurrent stale writers cannot both consume one expected version.

Evidence and prerequisites inside one assertion form an AND proof; separate assertions form alternative OR proofs. Withdrawal finds affected evidence using authoritative stored records, not a caller-truncated catalog. It propagates through prerequisites. Identity views are rebuilt from surviving original assertions. Permissions, epochs and tombstones are explicit. Cache erasure honestly breaks exact replay where bytes no longer exist.

The pinned legacy adapter wraps the upstream transaction and journal and never creates a second current accepted-graph table. See `14_deployment.md` for its gate and narrower operation capabilities. The reference backend, upstream bridge and statistical registry must not be conflated with a distributed production deployment.

## Budgets and schema resources

`RunBudget` stores monotonic counters in SQLite per run. Retrieval requests, model calls, retries, solver expansions, review actions and request bytes share limits. Multi-resource reservations are atomic and concurrent connections cannot overspend; reopening cannot reset used resources or relabel limits. Applications must route their own retrieval/review integrations through these APIs; the library does not intercept unrelated network clients.

All runtime schemas are standalone Draft 2020-12 contracts, cached after compilation and packaged for offline wheel execution. No caller-controlled remote reference is fetched. Public malformed-input boundaries return structured diagnostics rather than raw unchecked dictionary indexing.
