# API examples

## Complete isolated workflow

The simplest executable example is `python -m trace_gc demo --output trace-gc-demo`. `trace_gc/demo.py` also contains the complete staged construction. Its constants, fabricated data, reviewer identity and ephemeral keys are explicitly for isolated testing, not a deployment policy.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from trace_gc.demo import build_fixture

with TemporaryDirectory() as directory:
    fixture = build_fixture(Path(directory))
    try:
        approvals = fixture.approvals()             # isolated reviewer and validator
        result = fixture.publish(approvals=approvals)
        retry = fixture.publish(approvals=approvals)
        assert retry["replayed"] is True
        fixture.status_change(fixture.source_ids[0])
        assert len(fixture.backend.view(fixture.catalog)["edges"]) == 1
        fixture.backend.audit()
    finally:
        fixture.close()
```

## Immutable source representations

```python
from trace_gc.catalog import Catalog

catalog = Catalog()
a = catalog.source("document-42", "v1", "Exact first representation.", scope="tenant-a")
b = catalog.source("document-42", "v2", "Exact second representation.", scope="tenant-a")
assert a != b
span = catalog.evidence(a, 0, 5)  # Python Unicode-codepoint offsets, not UTF-8 bytes
claim = catalog.claim("A claim whose content cannot change behind its identity.")
```

Source admission and permissions still require trusted receipts. Creating catalog records does not grant the model read/write authority.

## Analysis policy replay

Create a new policy body by copying a trusted existing policy, assigning a **new** version, and setting `mode` to `ANALYSIS_ONLY`. Keep its explicit scope/population/allowed modes/check set. Then:

```sh
trace-gc replay-policy examples/runtime/bundle.json --policy analysis-v2.json --output replay-v2.json
trace-gc validate replay-v2.json
```

The new artifact retains original observation bytes and old evaluations, appends the new policy branch, and is not automatically checkpointed or authorized. Reusing an existing policy version with different content is rejected as ambiguous.

## Independent-label evaluation

Every label row must include `action_id`, `group_id`, nonempty `source_ids`, Boolean `label_correct`, independent `labeler`, `label_origin` (`HUMAN` or `INDEPENDENT_EXTERNAL`), raw final-policy `score`, Boolean `resolver_selected` and `constraints_passed`, final `decision`, and `split` (`LOCKED_HOLDOUT`). These must describe the actual complete frozen pipeline, not an isolated model output. Source/group correlations and external preregistration need reviewer verification.

A protocol contains `locked: true`, `split: LOCKED_HOLDOUT`, the preselected `threshold`, exact `pipeline_hash`, and `calibration_group_ids` / `development_group_ids`. Use `qualification.pipeline_fingerprint(scope)` to derive the pipeline hash. The 14 required scope fields are exported as `qualification.SCOPE_FIELDS`; `context_for` derives the actual run's values. No example population or test scope qualifies production.

The evaluation CLI requires all risk/coverage/confidence parameters explicitly. It returns an unsigned artifact only when the predeclared objectives pass. An administrator separately approves its exact hash with a QUALIFICATION receipt and registers that receipt in the service-owned `QualificationRegistry`. The subsequent plan still needs an AUTHORIZATION receipt.

## Live adapter integration

Construct `TypeSafeAdapter(enabled=True, api_key=..., token_counter=..., tokenizer_version=..., observation_signer=...)` in the trusted application. Call `.evaluate(catalog, pack_id, source_status=..., budget=...)` only with a LIVE, pinned-model, exactly materialized pack. The tokenizer must be the actual approved implementation, not a caller-supplied “measured” Boolean. The adapter has a mockable transport for tests and keeps error attempts distinct. No live credentials or real tokenizer implementation is supplied by this archive.

For publication instantiate `CompilerService` with your backend, independently enrolled trust, validator signer, exact policy version/hash, population, scope and explicit mode. Call `preflight`, obtain independent `authorize_plan` approval, then `publish`. There is no supported path in which model text supplies these trusted dependencies itself.
