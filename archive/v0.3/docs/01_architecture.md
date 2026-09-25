# Executable architecture

The fixed-schema path is: immutable source snapshot and claim → candidate → deterministic state/closure compiler → exact-wire observation → joint resolution certificate → policy evaluation → typed immutable plan → independent preflight and authorization → atomic graph transaction → provenance/replay/withdrawal.

A candidate generator or model does not hold signing keys, register issuer permissions, set the service's publication mode, or write the graph. Evidence text is rendered as data rather than instructions. A hash binds bytes; it is never treated as semantic correctness or authority.

The catalog stores immutable content with separate logical-source/snapshot identities. The compiler traverses candidates, prerequisites, alternatives, claims, evidence, upstream observations and graph support. It renders the exact required state plus per-field provenance. The request adapter serializes a pinned installed question program and preserves exact wire bytes. Failed observations remain error records.

The resolver evaluates combinations against deterministic graph constraints, cannot-links and explicit mutually exclusive alternatives. Per-candidate resolutions project one component certificate rather than concealing global inputs. Automatic acceptance needs an exact applicable approved qualification; independent approval is still required to publish. Unqualified observations abstain, but an enrolled reviewer may approve an isolated/reviewed flow under separately configured policy.

`SQLiteReferenceBackend` is an inspectable single-host implementation for tests and isolated use. `PinnedLegacyBackend` is a separately gated bridge that keeps the upstream store authoritative. Both use a transaction boundary where current graph/schema versions, source status/epochs, qualification, signatures, and plan semantics are rechecked before publication.

Optional autoresearch, learned resolution and large-scale packing are not prerequisites for this complete fixed-question path. Research design material and proposed experiments remain in the archived v0.2 package.
