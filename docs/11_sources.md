# Source and external-contract provenance

The user-supplied archive is the implementation baseline. Its original source manifest and requirements are retained in `archive/v0.2` and `sources/`. The prior design review and reproduction harness are retained under `review/`. No external repository was modified and no provider request was performed.

External primary documentation checked for interface/standards design:

- TypeSafe API, models and confidence: https://docs.typesafe.ai/api ; https://docs.typesafe.ai/models ; https://docs.typesafe.ai/confidence
- JSON Schema Draft 2020-12 and conditionals: https://json-schema.org/understanding-json-schema/reference/conditionals
- RFC 8785: https://www.rfc-editor.org/rfc/rfc8785 — considered but **not** the serialization implemented; this project explicitly specifies TRACE-C14N-1 instead.
- Hypothesis stateful-testing documentation: https://hypothesis.readthedocs.io/en/latest/stateful.html — design reference only; this release uses unittest-generated state sequences and does not claim Hypothesis was executed.

The upstream source pin comes from the supplied manifest: `CompleteDotTech/paper-package`, `graph_synthesis/core.py`, Git blob `68217feec539d37e4a524432c93df035f9a0fe39`. Matching executable bytes were not available during this release. The bridge remains subject to its exact-pin conformance gate; reconstructed or current-branch bytes are not represented as a verified checkout.

Documentation/reference inspection does not establish live API compatibility or statistical qualification. Dependency versions in `requirements.txt` are the local versions exercised by the attached report, not a claim to be the latest releases.
