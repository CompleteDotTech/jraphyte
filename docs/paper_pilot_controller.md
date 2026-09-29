# Frozen source preparation controller

`PaperPilotController` is a supported application entry point for the first
source-first segment of issue #23. The embedding application supplies its
existing `PaperPilot`, configured with its own trust store, current ACL, budget,
schema, exact model identity and isolated `SQLiteReferenceBackend`. The
controller cannot create signers or allow-all permissions. It does not call a
model or publish a graph assertion.

Before preparing a source, freeze a private manifest with `version` set to
`real-paper-pilot-controller-v1`, the exact `pilot_config`, the same `questions`,
`acceptance={"phase":"source_preparation_only", "source_review_checks":
sorted(CHECKS)}`, and `pages`. This freezes the source preparation checks only;
the full #23 evaluation cohort and numeric extraction, graph, retrieval, answer,
citation and abstention criteria still need a separate preregistered protocol
before inference or generated-answer inspection. Each page has a stable
`id`, `source_id`, `version`, original `pdf_sha256`, `physical_page`, and exact
native text `start`/`end` offsets. The page must belong to the configured
document and permitted physical pages. Keep the manifest, PDFs, source-first
review and its later signed receipts private.

```python
from trace_gc.paper_pilot_controller import PaperPilotController

controller = PaperPilotController(app_pilot, manifest=app_frozen_manifest,
                                  private_dir=app_private_run_dir)
controller.preflight(app_pdf_bytes_by_page_id)  # verifies every frozen PDF, journals result
prepared = controller.prepare("paper-page-2", app_original_pdf_bytes)
assert prepared["state"] == "WAIT_SOURCE_REVIEW"
review_material = app_pilot.source_review_material(prepared["request_id"])
# Application reviewer inspects original page, image, text and offsets here.
```

The controller writes a hash-chained `application-journal.sqlite3` alongside the
existing pilot checkpoint. `prepare` refuses to run until the full PDF map has
passed and the preflight event is durable. Reopening with the same manifest checks
the initial pilot checkpoint, preflight identity, journal chain and prepared
result hashes. Repeating a request
uses the same stable ID and existing `PaperPilot` idempotency checks. A crash
after `PaperPilot.prepare_native_page` but before the controller journal append
can be recovered by repeating `prepare` with the original PDF bytes. The
application must coordinate any external provider execution journal and model
call with its own supervisor; `PaperPilot` locks its checkpoint for one controller.

This is a preparation interface, not a completed paper-to-answer run. The
application must still obtain actual source review and source-admission
authority; run genuine semantic inference under its frozen resource gate,
import and attest the exact response; review/authorize any graph plan; retrieve
under current ACL; execute an approved answer model; assess claim support and
citations; and exercise reopen, withdrawal and permission changes. Its separate
execution journal must reconcile unknown provider outcomes before a retry.
The prepared f097 profile requires at least 20 GiB sustained available memory;
do not infer activation from this controller's source preparation.
