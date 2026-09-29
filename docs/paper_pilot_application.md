# Local real-paper source preparation

`LocalPaperPilotApplication` binds an externally frozen private issue #23
protocol to the durable `PaperPilot` and `PaperPilotController`. This first
application stage verifies every original PDF and exact native source anchor,
requires explicitly enrolled narrow private signing identities, checks the
current exact-grant ACL, and prepares all native evidence packets. It returns
`WAIT_SOURCE_REVIEW`. Image-only anchors are reported as held. There is no
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

The frozen private v2 protocol includes f097's native abstract and page-two
study, f113's structured abstract and page-four quantitative text, and f076's
image-only cover plus later native text. This application holds f076's cover
until the reviewed image/crop transcription route can bind text to original
page pixels. It does not mislabel image text as native offsets. The protocol's
edition-label comparison must cite both the cover and inner page.
PyMuPDF and Pillow are optional dependencies for the package; this real-page
stage requires PyMuPDF at runtime, and its authored image tests skip when the
optional image stack is absent.

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
