# Local real-paper source preparation

`LocalPaperPilotApplication` binds an externally frozen private issue #23
protocol to the durable `PaperPilot` and `PaperPilotController`. This first
application stage verifies every original PDF and exact native source anchor,
requires explicitly enrolled narrow private signing identities, checks the
current exact-grant ACL, and prepares all native evidence packets. It returns
`WAIT_SOURCE_REVIEW` for v3. Image-only anchors are reported as held. There is no
provider call, signed review, source admission or graph publication in this
stage.

The embedding application creates an isolated private run directory and passes
these capabilities explicitly:

- `PaperPilot` in `LIVE` mode with the frozen cohort hash and questions, a
  pinned real tokenizer callable, app-owned `Catalog`/policy, `RunBudget`, and
  `SQLiteReferenceBackend(sandbox=False)` at the run directory's graph path.
- `TrustStore` containing three **distinct** application-enrolled issuers:
  source reviewer (`SOURCE_STATUS`, `PAPER_SOURCE_REVIEW`, `can_review=True`),
  source admitter (`SOURCE_STATUS`, `SOURCE_ADMIT`, `can_review=False`), and
  preflight validator (`PREFLIGHT`, no graph operations). Each is restricted to
  the exact pilot scope and `LIVE` mode. The application loads their private
  keys outside the repository and checkpoint; this module never generates or
  persists keys. An assistant reviewer must be recorded as `assistant` in the
  later signed source review, without an independent-human claim.
- A current authenticated ACL callback for the same scope with exact grants.
  Each grant must name the current user or one role the user holds; empty
  recipient lists are rejected. The application owns ACL changes. Missing source grants deny access until
  reviewed source snapshots are explicitly admitted and granted.
- The absolute private protocol path, its expected file SHA-256, and the
  authorized local PDF root. Relative PDF paths must resolve within that root.

```python
from trace_gc.paper_pilot_application import LocalPaperPilotApplication

app = LocalPaperPilotApplication(
    pilot=app_pilot, protocol_path=app_private_protocol_path,
    protocol_sha256=app_frozen_protocol_sha256, source_root=app_authorized_pdf_root,
    reviewer=app_source_reviewer_signer, admitter=app_source_admitter_signer,
    validator=app_preflight_validator_signer, trust=app_trust,
    access=app_current_access,
)
result = app.prepare_sources()
assert result["state"] == "WAIT_SOURCE_REVIEW"
# A reviewer now inspects app_pilot.source_review_material(request_id) for each
# prepared request. No source is accepted merely because this call succeeded.
app.close()
```

The corrected frozen private v3 protocol includes f097's native abstract and page-two
study, f113's structured abstract and page-four quantitative text, and f076's
image-only cover plus later native text. This application holds f076's cover
until the reviewed image/crop transcription route can bind text to original
page pixels. It does not mislabel image text as native offsets. The protocol's
edition-label comparison must cite both the cover and inner page.
The earlier v2 protocol is preserved as rejected before activation: several
native anchors ended mid-word or mid-sentence. The application requires v3
and applies mechanical source-span checks: exact quote, word edges, terminal
punctuation and no nonterminal text earlier on the same line. A line break can
occur within a sentence, so these checks do not establish true sentence or
abstract boundaries. An attributed reviewer must inspect the original page
and decide `boundaries` before signing a source review.
PyMuPDF and Pillow are optional dependencies for the package; this real-page
stage requires PyMuPDF at runtime, and its authored image tests skip when the
optional image stack is absent.

## Prospective v4 source preparation

The v3 protocol and v1 controller manifest remain exact. A separate v4 path
requires a final protocol with version `issue23-real-paper-source-first-protocol-v4`
and status `APPROVED_SOURCE_REFERENCE_FROZEN_PENDING_RUN_ACTIVATION`. The caller
must pass `approved_v4_sha256`, `parent_protocol_path`, exact
`image_candidate_paths`, and an application-owned `approval_manifest_path` plus
`approval_manifest_sha256`. The approval manifest binds the final protocol hash,
the v3 parent hash, a source-reference-only decision, and attribution/time.
Its `approved_by` field is **not** a cryptographic signature or an independent
review. No public code contains a private protocol hash. The current private
v4 draft has a prospective status and is rejected by this entry point.

The v4 application compares documents, all original anchor bodies, questions
and numeric gates with the exact parent v3 bytes. It reconstructs both frozen
image candidates from the original PDFs and checks page, render, crop,
transcription, producer and file hashes. The v2 controller journal includes
native and image work items in one full-cohort preflight; a missing or changed
PDF prevents every prepare call. It reconciles image prepare requests after
reopen. `prepare_sources()` returns seven native packets and two image packets
at `WAIT_IMAGE_SOURCE_REVIEW`, with the f113 native notation anchor still on
HOLD. No checks are signed, source admitted, ACL changed, model called or graph
assertion published by this stage. The image candidates require fresh source
review in the new run; earlier private trial receipts do not transfer.

For v4, the approved `anchor_scoring_routes` map selects a separately reviewed
image source for the cover and a `native_corrupt` image crop alternative for
f113 page four. The native f113 anchor remains HOLD; no native offsets are
assigned to either image source. This application prepares sources only; later
scoring must count each mapped anchor once after signed review, separate source
admission and exact current ACL checks.

`PaperPilot` freezes all `trace_gc` code hashes, so the merged v4 application
cannot reopen a v3 or draft-code run. Use a new run ID, checkpoint, controller
journal, isolated backend and private keys after the final v4 protocol and
approval manifest have been reviewed and frozen.

## Subsequent reviewed stages

1. An attributed reviewer inspects each exact PDF, render, native span and
   notation, then signs `source_review_payload`. The app checks and accepts
   each receipt using `PaperPilot.accept_source_review`.
2. A distinct source authority signs exact source-admission payloads. The app
   admits reviewed sources into the isolated reference backend and updates
   current ACL grants only for those source IDs and required nodes.
3. Freeze final code, runtime and local semantic profile, check sustained
   available RAM at or above the protocol's 20 GiB threshold, then compile
   explicit candidate claims. Execute an approved local model through the
   existing Qwen semantic adapter with durable external execution intent;
   import exact bytes and attest observations. Any unknown execution outcome
   holds rather than retries automatically.
4. Review resolution and graph plan. A separately scoped publication authority
   signs the exact plan; reopen the SQLite backend and verify journal,
   provenance and idempotent retry before retrieval.
5. Retrieve under current ACL, use an approved local answer model, and obtain
   attributed claim-support review for every citation. Run supported,
   unsupported, discrepancy, withdrawal, permission-change and recovery cases
   against the preregistered numeric gates. Keep #20 and #22 qualification
   evidence separate from this development-exposed pilot.

No later stage is activated by `prepare_sources()`. The private protocol and
source-first expected evidence may be reviewed before inference; model output
must not be inspected before the final application roles, resources and code
profile are frozen. The `PaperPilot` checkpoint and controller journal retain
the run identity and prepared requests for a fresh-process reopen.
