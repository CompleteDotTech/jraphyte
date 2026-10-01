# Manual recovery when the old worker PID was not recorded

This version keeps the old invalidated attempt and its UNKNOWN provider outcome.
It allows one distinct successor only through `execute_successor` with an
application-owned authority and a current live exclusion. The standalone CLI
cannot enroll itself or call this effect path.

The `paper-converter-attempt-closure-v2` branch applies only to the exposed
Docling attempt made by the exact reviewed historical controller/worker source
hashes in `paper_converter_reconciliation.py`. Its signed closure must use
`worker_pid: null`, identify the unchanged old intent, registry, inventory,
stderr/stdout and invalidation bytes, and label the old launcher inference
`LAUNCHER_TERMINAL_PROVIDER_OUTCOME_UNKNOWN`. The preserved stderr contains a
worker `WORKER_FAILED` ValueError and the invalidation is FileNotFoundError.
The pinned old controller calls `Popen.wait` before loading `worker-result`;
the preserved stderr proves a worker process reached its error handler, while
the absent result and unknown PID do not prove a particular provider outcome.
The signed receipt must retain `UNKNOWN_UNATTESTED_NO_RETRY` and
`old_retry_authorized: false`.

`RootEnrolledConverterApplication` consumes an independently reviewed
enrollment file outside the converter data root. The owning application must
pin its exact SHA in a separate approved release; supplying a self-authored
path and SHA is not enrollment. It checks the exact old registry, authority,
successor plan/output, and original data root. Under the shared converter
engine lock, it obtains a fresh `Win32_Process` census, rejects the old
controller identity, possible descendants, any live use of the old interpreter
image (derived from the authenticated old plan, then matched to enrollment),
and inaccessible Python process images. It reobserves immediately
before and after the distinct successor worker. A failed census, unknown
process identity, changed enrollment, or missing lock is HOLD. Its exclusion
applies to cooperative launchers using the same engine lock and this owning
application. It cannot attest an arbitrary unrecorded historical process tree
or an uncooperative launcher.

Operational prerequisites for a real attempt:

1. Preserve and independently hash the old registry, intent, invalidation,
   stdout/stderr, plan, raw files and original code identity. Do not edit the
   old output or clear its registry.
2. Record current process census and exact source-correlated launcher inference
   as new evidence outside the old output. Have the enrolled reviewer sign a
   new closure and reconciliation receipt for one distinct successor output.
3. Have the owning application approve and pin the enrollment and authority
   independently of that receipt, with the original data root, old registry,
   and new plan/output. The approval must be current and unexpired at launch.
4. Revalidate all pinned old bytes and the fresh process census while holding
   the engine lock. Execute only the new output once. A failure leaves that
   successor's durable intent and must be reconciled before any further work.

This code has only authored no-converter tests. No actual enrollment, current
process approval, Docling worker or successor output has been authorized or
created by this handoff.
