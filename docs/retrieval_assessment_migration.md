# Versioned Docling assessment migration

The migration utility adopts **sealed conversion attempts** from a stopped
assessment run into a new, immutable protocol. It never edits the origin run.
Imported documents are assessed again under the new selector code and source
geometry, with `new_model_call: false` in each imported row. Subsequent IDs use
the ordinary single-owner producer. A sealed conversion is reusable; an intent
without a sealed conversion is an unknown outcome and requires reconciliation.

The utility is `python -m src.parallel_source_v4.assessment_migration`. Run it
with the pinned **evaluator** interpreter. `--origin-interpreter` also names the
original pinned evaluator, whose source checkout and runtime are replayed to
verify every completed origin row. The converter interpreter is a separate
identity held by the private profile and worker session receipts.

```powershell
& $evaluatorPython -B -s -m src.parallel_source_v4.assessment_migration `
  --data-root $dataRoot `
  --origin-output $originOutputRelativeToDataRoot `
  --new-output $freshOutputRelativeToDataRoot `
  --origin-checkout $frozenOriginCheckout `
  --origin-interpreter $originalEvaluatorPython `
  --origin-head $expectedOriginHead `
  --origin-protocol-sha256 $expectedOriginProtocolSha256 `
  --expected-import-count $reviewedSealedAttemptCount
```

Before starting, preserve the origin directory and its supervisor history;
stop any old controller; confirm the original exposure cutoff and authorized
resource window; and choose a fresh output directory. Review the origin
protocol, manifest, profile, completed receipts, and next sealed conversion.
For the 2026-09-29 incident, 108 completed rows and the next sealed conversion
give 109 imports; this is an incident fact, not a general default. The tool
requires a completed-row prefix followed by exactly one sealed pending
conversion and no later or unknown work. It writes a separate immutable
`migration-v1` plan binding the origin and new code/runtime identities before
creating the new run.

On restart, use **identical arguments and identities**. The utility replays the
frozen origin audit, validates every existing migrated row and its source,
reuses any assessment sealed before a crash, then continues at the next ID.
If the plan, source, runtime, conversion, or row differs, stop and reconcile;
do not delete or rewrite receipts. The new run has a distinct protocol and
must be reviewed as such. A source-gate acceptance for the prior code is stale
after this verifier change and requires a fresh qualification before any
downstream freeze or promotion.

This utility has not been run on the full 10,000-document corpus. Local tests
cover immutable import, a crash between assessment and row sealing, idempotent
resume, altered source/origin/runtime/plan rejection, and source-owned abstract
closure. No model conversion or graph publication occurs in those tests.

## Sealed-prefix migration v2

`assessment_migration_v2` handles a different stopped-run shape: a complete
row prefix followed by an **empty pre-intent directory** for the next ID. It
does not reuse a pending conversion or restart the old worker. The empty
directory must be the exact next protocol ID, have no hidden entries, and
follow the frozen producer's verified `mkdir -> durable intent -> convert`
call order. Any intent, conversion, later row, or unknown attempt holds for
separate reconciliation. The old directory remains unchanged.

`prepare` replays every completed receipt using the frozen original checkout
and evaluator. It writes a distinct immutable plan outside either run. This
step performs no model conversion. `run` requires that same plan, a fresh
source-verified acceptance receipt whose V4 method hashes equal the current
producer closure, and the exact pinned approval policy, configuration and
source map. Imported cached Docling documents are assessed again under the
current code and source geometry, retaining their original success/error and
eligibility states. All imported rows explicitly record zero new model calls.
Subsequent IDs use the current bounded producer, capped at 64 documents per
converter session. The source gate and resource guard must be verified for
the new code before allowing that model work.

```powershell
& $evaluatorPython -B -s -m src.parallel_source_v4.assessment_migration_v2 prepare `
  --data-root $dataRoot --origin-output $originRelative --new-output $freshRelative `
  --origin-checkout $frozenCheckout --origin-interpreter $originalEvaluatorPython `
  --origin-head $frozenHead --origin-protocol-sha256 $frozenProtocolSha `
  --expected-prefix-count $verifiedCompletedRows --max-documents-per-session 64

& $evaluatorPython -B -s -m src.parallel_source_v4.assessment_migration_v2 run `
  --data-root $dataRoot --origin-output $originRelative --new-output $freshRelative `
  --origin-checkout $frozenCheckout --origin-interpreter $originalEvaluatorPython `
  --origin-head $frozenHead --origin-protocol-sha256 $frozenProtocolSha `
  --expected-prefix-count $verifiedCompletedRows --max-documents-per-session 64 `
  --gate-receipt $currentGateReceipt --gate-receipt-sha256 $currentGateSha `
  --gate-policy $currentPolicy --gate-policy-sha256 $currentPolicySha `
  --gate-configuration $currentConfiguration --gate-source-map $currentSourceMap
```

The 1,207-row `d02857` prefix and empty `d02858` directory are incident
evidence, not defaults. Preserve the old supervisor failure and the empty
directory. A distinct new output and protocol are required. An interrupted
new run resumes only with identical plan, runtime, source, profile, and code
identities; unknown converter outcomes remain held.
