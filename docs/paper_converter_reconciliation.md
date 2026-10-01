# Manual converter-attempt reconciliation

This workflow is for a preserved **invalidated, unknown-outcome** exposed-page
smoke attempt. It never retries that output, deletes its registry entry, clears
its `INVALIDATED.json`, or declares that the historical converter did not run.
The ordinary `execute` command still blocks whenever the registry contains an
unresolved attempt.

An owning application must first review and pin the exact
`paper-converter-reconciliation-authority-v1` JSON bytes independently of the
receipt. The standalone CLI cannot enroll an authority or execute a successor.
The owning application must supply an externally approved byte SHA-256 through
its own reviewed trust configuration. It never discovers a public key from the receipt. The authority
contains a named issuer, Ed25519 public key, old registry byte hash, successor
plan byte hash, distinct successor output, and expiry. A caller able to author
both this authority and its purported root approval can self-authorize; the
application must control the approval boundary. The repository does not ship
an enrolled production key or an approved reconciliation release.

The signed `paper-converter-manual-reconciliation-v1` envelope binds:

- Exact old registry, intent, invalidation, old plan, and every preserved old
  output file and directory, including partial raw outputs and logs.
- `UNKNOWN_UNATTESTED_NO_RETRY` and `old_retry_authorized:false`.
- A separate hash-pinned closure evidence file. It records the original
  controller PID, observed worker PID and creation/exit times, owned-descendant
  zero observation and the supporting process evidence bytes. GROBID also
  requires a request ID, closed-request/inflight-zero observation and server
  evidence bytes. These are attributed reviewer judgments over actual process
  and server evidence, not facts the tool can reconstruct from the old intent.
- The newly pinned successor plan and a different, absent output path.

The reviewer signs the canonical JSON of envelope `version`, `issuer`,
`issued_at`, and `payload` using Ed25519. The signature, authority pin, typed
closure evidence, byte inventory, and successor identity are verified under
the existing data-root OS lock. The owning application must also hold a live
launch exclusion across the whole new worker and observe the old controller,
worker, descendants, and any provider server immediately before and after it.
A historical signed boolean alone cannot establish present process liveness.
Pinned old materials are rechecked before and after the worker boundary. A changed
material or unknown child outcome invalidates the new attempt for separate
reconciliation; it never silently retries the old attempt.

The standalone `execute-successor` CLI rejects even matching caller-supplied
authority and receipt hashes. Otherwise a caller could create both the key and
its purported approval. A future owning application may call
`execute_successor(..., trusted_application=...)` only after independently
enrolling the authority and supplying a live OS/server exclusion object. The
application must pass the same capability to `verify_execution`, `finalize`,
and `verify_readiness`; without it, successor qualification readback holds.
For a completed successor, historical readback checks the approved expiry
against its immutable `intent.started_at`; an expiry after execution does not
erase valid evidence. A new worker still needs currently unexpired approval
and current live exclusion. The owning application must enforce any current
explicit key or release revocation for both paths.
Immediately before worker dispatch the authority must still be unexpired.
After the owned worker exits, immutable old material is rechecked against
the durable successor intent time under the same held exclusion. A worker
that crosses the approval expiry can finish and be read back, while expiry
cannot authorize another worker.

A future reviewed application command would need descriptors like these:

```powershell
python -m owning_application.reviewed_converter_successor `
  --data-root $dataRoot `
  --plan plans/successor.json --expected-plan-sha256 $successorPlanSha `
  --output smoke/distinct-successor `
  --reconciliation-authority reviews/authority.json `
  --expected-reconciliation-authority-sha256 $approvedAuthoritySha `
  --reconciliation-receipt reviews/signed-reconciliation.json `
  --expected-reconciliation-receipt-sha256 $approvedReceiptSha
```

No such enabled application command is supplied by this change. The new
`RECONCILIATION_PARENT.json` is sealed before its intent and included
in the successor `execution.json` artifact map. It preserves exact authority,
receipt, old registry and outcome references for later independent readback.
The existing source, runtime, code identity, exposure, bounded one-attempt,
offline, zero-retry and custodian-readiness checks still apply to the successor.
The signed review is not a real converter result, source review, prospective
cohort authorization, graph admission, or proof of actual engine success.

**Deployment hold:** No real old-attempt process/server closure evidence,
application-enrolled authority, approved successor plan, or integrated live
exclusion verifier is supplied by this source-only change. Do not use a disposable
test signer or shape fixture as a production authority.
