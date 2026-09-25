# Design-review recommendation → implementation → evidence

The IDs refer to the complete prior review in `review/Design_Review.md`. “Implemented” describes software, not external deployment or empirical evidence. Exact test outcomes are generated in the release report.

| Review | Implementation | Executed regression/acceptance coverage |
|---|---|---|
| F01 — trusted model-visible state | `catalog.py`, `compiler.py`, typed claim/source/pack schemas; exact field materialization and identity/whitespace transforms | Original P01–P03/P08 reject; runtime state/claim/source substitution, omitted evidence and reproducible-normalization tests. |
| F02 — recursive closure and freshness | BFS typed closure; graph support; trusted source epochs/permissions; historical profile | P04/P09 reject; deep missing prerequisite, source-status bypass, incomplete catalog withdrawal, permission and historical replay tests. |
| F03 — complete dependency graphs | `references.py`; scoped question IDs; all typed refs; causality/status/snapshot/time checks; alternatives kept noncausal | P05–P07/P12–P13 reject; missing/wrong-type refs, cycles, cross-pack completion, timezone and 10,000-node chain tests. |
| F04 — variants and lifecycle | Six operation variants, unique IDs, exact content/revision/schema impact, component/risk agreement, immutable plans, one lifecycle, trusted preflight/auth | P10/P11/P17/P18 reject; all transition classes, metadata, explicit retraction, schema proposal/apply, reviewed R5 and identity component tests. |
| F05 — complete authenticated lineage | Partial/finalized/historical profiles; source/policy/qualification coverage; causal ledger; external checkpoint; atomic transaction anchor | P14/P15 reject; coverage, mode, forged root/receipt, transaction prefix, tampering, fault rollback and published verification tests. |
| F06 — Score rubric meaning | Full legend description comparison, typed response validation, exact error receipts | P16 rejects; reversed legend, malformed distributions/model returns, Score mean and Noul contract tests. |
| F07 — global component result | Exact input-bound joint certificate, cannot-links/exclusive alternatives, status, impact and per-candidate projections | Global identity A–B/B–C with A–C cannot-link, exclusive selections, multi-pair R5 impact, joint publication and reversible withdrawal tests. |
| F08 — observation/policy separation | Immutable observation IDs vs evaluation IDs; multiple policy branches; wire/semantic/cache distinctions; exact adapter bytes | Replay retains observations and previous evaluations; policy/version input binding, cache scope and mocked retry/error/success receipts. |
| F09 — executable qualification and authority | Fourteen-dimension registry; exact binomial bound/coverage; independent-label protocol; expiry/drift/revocation; external Ed25519 operation capabilities | All scope dimension substitutions reject; hash/approval substitution, no-label/zero-acceptance failures, mocked qualified boundary, issuer/receipt/risk/authorization tests. Real labels and pilot not supplied. |
| F10 — serialization and evidence history | Explicit TRACE-C14N-1 with vectors; duplicate/nonfinite/Unicode rules; snapshot versions; epoch/permission/tombstone state | Canonical edge cases and vectors, multiple source versions, withdrawal, restored permissions, local erasure and explicit replay-loss tests. |
| F11 — complete minimal path and engineering | Fixed-question E2E before autoresearch; tested SQLite reference; pinned legacy bridge + conformance command; cached schemas; linear DAG; persistent shared budgets | Original 42 tests retained; complete demo, fault/concurrency/idempotency/AND–OR/generated sequence tests, budget contention and schema package checks. Actual pinned-upstream test is explicitly skipped pending matching bytes. |

## Recommendations that require evidence outside the archive

The implementation supplies the mechanisms and acceptance commands, but does not fabricate representative independent labels, a genuinely preregistered holdout, production calibration, controlled pilot participants/results, a live-provider receipt, externally enrolled deployment principals, or an unavailable exact upstream checkout. Qualification and deployment gates remain closed until those inputs and checks are supplied.

The earlier recommendation to place optional optimization after correctness has been applied to the roadmap. Autoresearch, learned resolution and large-scale packing are not prerequisites and are not reported as completed experiments. The preserved historical design can guide those separately measured additions.

## Compatibility discipline

The original adversarial mutations remain intact. The compatibility probe script only updates its graph-manifest refresh helper for the newly introduced claims collection. Original test/review/script versions are preserved for audit. Runtime v0.3 artifacts are deliberately not hash-compatible with old live observations; do not “migrate” them by recomputing hashes and relabeling them as new inference.
