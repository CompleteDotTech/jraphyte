# Workflow source coverage

[Atlas index](README.md) · [Machine-readable source hashes](source-map.json)

The atlas indexes **112 active Python modules** at source revision `d5ca636a48e963619f4c89e2958d0bb1a3e72f80`. The table assigns every module to its explanatory chapters; it does not claim a separate diagram node for every helper function. The JSON also records each top-level class/function and exact file hash.

Function-level explanations and test references live in the linked chapters. Archived releases remain historical context. The application runtime, optional research harnesses and release tooling remain distinct in the diagrams.

## Runtime and retrieval

| Source module | Workflow chapters |
| --- | --- |
| [trace_gc/__init__.py](../../trace_gc/__init__.py) | [01](01-overview.md) · [12](12-commands-budgets.md) |
| [trace_gc/__main__.py](../../trace_gc/__main__.py) | [12](12-commands-budgets.md) |
| [trace_gc/adapter.py](../../trace_gc/adapter.py) | [03](03-observations-resolution.md) |
| [trace_gc/backend.py](../../trace_gc/backend.py) | [04](04-policy-publication.md) · [05](05-history-replay.md) |
| [trace_gc/budget.py](../../trace_gc/budget.py) | [12](12-commands-budgets.md) |
| [trace_gc/canonical.py](../../trace_gc/canonical.py) | [02](02-evidence-compilation.md) · [05](05-history-replay.md) |
| [trace_gc/catalog.py](../../trace_gc/catalog.py) | [02](02-evidence-compilation.md) |
| [trace_gc/cli.py](../../trace_gc/cli.py) | [12](12-commands-budgets.md) |
| [trace_gc/compiler.py](../../trace_gc/compiler.py) | [02](02-evidence-compilation.md) · [07](07-upstream-compilation.md) |
| [trace_gc/conformance.py](../../trace_gc/conformance.py) | [11](11-validation-delivery.md) |
| [trace_gc/constraints.py](../../trace_gc/constraints.py) | [03](03-observations-resolution.md) · [04](04-policy-publication.md) |
| [trace_gc/demo.py](../../trace_gc/demo.py) | [01](01-overview.md) · [11](11-validation-delivery.md) |
| [trace_gc/errors.py](../../trace_gc/errors.py) | [02](02-evidence-compilation.md) · [12](12-commands-budgets.md) |
| [trace_gc/ledger.py](../../trace_gc/ledger.py) | [05](05-history-replay.md) |
| [trace_gc/legacy.py](../../trace_gc/legacy.py) | [04](04-policy-publication.md) · [11](11-validation-delivery.md) |
| [trace_gc/pdf_admission.py](../../trace_gc/pdf_admission.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [trace_gc/pdf_evidence.py](../../trace_gc/pdf_evidence.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [trace_gc/pdf_source_parallel_v4.py](../../trace_gc/pdf_source_parallel_v4.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [trace_gc/pdf_source_v3.py](../../trace_gc/pdf_source_v3.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [trace_gc/pdf_structure.py](../../trace_gc/pdf_structure.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [trace_gc/pdf_structure_parallel_v4.py](../../trace_gc/pdf_structure_parallel_v4.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [trace_gc/plans.py](../../trace_gc/plans.py) | [04](04-policy-publication.md) · [05](05-history-replay.md) |
| [trace_gc/policy.py](../../trace_gc/policy.py) | [04](04-policy-publication.md) |
| [trace_gc/programs.py](../../trace_gc/programs.py) | [02](02-evidence-compilation.md) · [03](03-observations-resolution.md) |
| [trace_gc/qualification.py](../../trace_gc/qualification.py) | [04](04-policy-publication.md) |
| [trace_gc/references.py](../../trace_gc/references.py) | [02](02-evidence-compilation.md) · [05](05-history-replay.md) |
| [trace_gc/replay.py](../../trace_gc/replay.py) | [05](05-history-replay.md) |
| [trace_gc/resolver.py](../../trace_gc/resolver.py) | [03](03-observations-resolution.md) |
| [trace_gc/retrieval/__init__.py](../../trace_gc/retrieval/__init__.py) | [06](06-hybrid-retrieval.md) · [07](07-upstream-compilation.md) · [08](08-downstream-answers.md) |
| [trace_gc/retrieval/benchmark.py](../../trace_gc/retrieval/benchmark.py) | [06](06-hybrid-retrieval.md) · [11](11-validation-delivery.md) |
| [trace_gc/retrieval/budget.py](../../trace_gc/retrieval/budget.py) | [06](06-hybrid-retrieval.md) · [12](12-commands-budgets.md) |
| [trace_gc/retrieval/contracts.py](../../trace_gc/retrieval/contracts.py) | [06](06-hybrid-retrieval.md) |
| [trace_gc/retrieval/evaluation.py](../../trace_gc/retrieval/evaluation.py) | [06](06-hybrid-retrieval.md) · [11](11-validation-delivery.md) |
| [trace_gc/retrieval/fixtures.py](../../trace_gc/retrieval/fixtures.py) | [06](06-hybrid-retrieval.md) · [11](11-validation-delivery.md) |
| [trace_gc/retrieval/integration.py](../../trace_gc/retrieval/integration.py) | [02](02-evidence-compilation.md) · [07](07-upstream-compilation.md) · [08](08-downstream-answers.md) |
| [trace_gc/retrieval/items.py](../../trace_gc/retrieval/items.py) | [06](06-hybrid-retrieval.md) · [08](08-downstream-answers.md) |
| [trace_gc/retrieval/planner.py](../../trace_gc/retrieval/planner.py) | [07](07-upstream-compilation.md) |
| [trace_gc/retrieval/reranker.py](../../trace_gc/retrieval/reranker.py) | [06](06-hybrid-retrieval.md) · [07](07-upstream-compilation.md) |
| [trace_gc/retrieval/scenarios.py](../../trace_gc/retrieval/scenarios.py) | [01](01-overview.md) · [07](07-upstream-compilation.md) · [08](08-downstream-answers.md) · [11](11-validation-delivery.md) |
| [trace_gc/retrieval/security.py](../../trace_gc/retrieval/security.py) | [06](06-hybrid-retrieval.md) · [08](08-downstream-answers.md) |
| [trace_gc/retrieval/service.py](../../trace_gc/retrieval/service.py) | [06](06-hybrid-retrieval.md) · [08](08-downstream-answers.md) |
| [trace_gc/retrieval/store.py](../../trace_gc/retrieval/store.py) | [06](06-hybrid-retrieval.md) · [08](08-downstream-answers.md) |
| [trace_gc/retrieval/strategies.py](../../trace_gc/retrieval/strategies.py) | [06](06-hybrid-retrieval.md) |
| [trace_gc/retrieval/vector.py](../../trace_gc/retrieval/vector.py) | [06](06-hybrid-retrieval.md) |
| [trace_gc/schema.py](../../trace_gc/schema.py) | [02](02-evidence-compilation.md) |
| [trace_gc/trust.py](../../trace_gc/trust.py) | [04](04-policy-publication.md) |
| [trace_gc/validation.py](../../trace_gc/validation.py) | [05](05-history-replay.md) · [11](11-validation-delivery.md) |

## Versioned research experiments

| Source module | Workflow chapters |
| --- | --- |
| [src/abstract_validation/__init__.py](../../src/abstract_validation/__init__.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/audit.py](../../src/abstract_validation/audit.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/baselines.py](../../src/abstract_validation/baselines.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/common.py](../../src/abstract_validation/common.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/embedding_batch.py](../../src/abstract_validation/embedding_batch.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/evaluate.py](../../src/abstract_validation/evaluate.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/extraction_trial.py](../../src/abstract_validation/extraction_trial.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/prepare.py](../../src/abstract_validation/prepare.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/references.py](../../src/abstract_validation/references.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/report.py](../../src/abstract_validation/report.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/retrieval_trial.py](../../src/abstract_validation/retrieval_trial.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation/search.py](../../src/abstract_validation/search.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/__init__.py](../../src/abstract_validation_expanded/__init__.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/common.py](../../src/abstract_validation_expanded/common.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/convert.py](../../src/abstract_validation_expanded/convert.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/extraction.py](../../src/abstract_validation_expanded/extraction.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/finalize.py](../../src/abstract_validation_expanded/finalize.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/prepare.py](../../src/abstract_validation_expanded/prepare.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/references.py](../../src/abstract_validation_expanded/references.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/report.py](../../src/abstract_validation_expanded/report.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/retrieval.py](../../src/abstract_validation_expanded/retrieval.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/verify.py](../../src/abstract_validation_expanded/verify.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_expanded/vision.py](../../src/abstract_validation_expanded/vision.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/__init__.py](../../src/abstract_validation_v2/__init__.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/adapters.py](../../src/abstract_validation_v2/adapters.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/audit.py](../../src/abstract_validation_v2/audit.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/common.py](../../src/abstract_validation_v2/common.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/convert.py](../../src/abstract_validation_v2/convert.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/download_models.py](../../src/abstract_validation_v2/download_models.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/extraction.py](../../src/abstract_validation_v2/extraction.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/fields.py](../../src/abstract_validation_v2/fields.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/prepare.py](../../src/abstract_validation_v2/prepare.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/references.py](../../src/abstract_validation_v2/references.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/report.py](../../src/abstract_validation_v2/report.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/retrieval.py](../../src/abstract_validation_v2/retrieval.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/verify.py](../../src/abstract_validation_v2/verify.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v2/vision.py](../../src/abstract_validation_v2/vision.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/__init__.py](../../src/abstract_validation_v3/__init__.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/adapters.py](../../src/abstract_validation_v3/adapters.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/common.py](../../src/abstract_validation_v3/common.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/evaluate.py](../../src/abstract_validation_v3/evaluate.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/freeze.py](../../src/abstract_validation_v3/freeze.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/local_reranker.py](../../src/abstract_validation_v3/local_reranker.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/prepare.py](../../src/abstract_validation_v3/prepare.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/retrieval.py](../../src/abstract_validation_v3/retrieval.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/abstract_validation_v3/retrieval_experiment.py](../../src/abstract_validation_v3/retrieval_experiment.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/__init__.py](../../src/parallel_source_v4/__init__.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/adapters.py](../../src/parallel_source_v4/adapters.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/common.py](../../src/parallel_source_v4/common.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/extraction.py](../../src/parallel_source_v4/extraction.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/fields.py](../../src/parallel_source_v4/fields.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/freeze.py](../../src/parallel_source_v4/freeze.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/metrics.py](../../src/parallel_source_v4/metrics.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/prepare.py](../../src/parallel_source_v4/prepare.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |
| [src/parallel_source_v4/retrieval.py](../../src/parallel_source_v4/retrieval.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) |

## Validation and release tooling

| Source module | Workflow chapters |
| --- | --- |
| [tools/build_schemas.py](../../tools/build_schemas.py) | [11](11-validation-delivery.md) |
| [tools/build_vectors.py](../../tools/build_vectors.py) | [11](11-validation-delivery.md) |
| [tools/check_legacy.py](../../tools/check_legacy.py) | [11](11-validation-delivery.md) |
| [tools/legacy_hardening.py](../../tools/legacy_hardening.py) | [11](11-validation-delivery.md) |
| [tools/package_project.py](../../tools/package_project.py) | [11](11-validation-delivery.md) |
| [tools/public_fixtures_parallel_v4.py](../../tools/public_fixtures_parallel_v4.py) | [09](09-pdf-evidence-review.md) · [10](10-research-experiments.md) · [11](11-validation-delivery.md) |
| [tools/retrieval_schemas.py](../../tools/retrieval_schemas.py) | [11](11-validation-delivery.md) |
| [tools/run_validation.py](../../tools/run_validation.py) | [11](11-validation-delivery.md) |
| [tools/validate_package.py](../../tools/validate_package.py) | [11](11-validation-delivery.md) |

## Executable query example

| Source module | Workflow chapters |
| --- | --- |
| [examples/graphrag/query_example.py](../../examples/graphrag/query_example.py) | [08](08-downstream-answers.md) |

## Keeping the inventory current

Run `python docs/workflow/verify.py` to verify file hashes, module coverage, local links, matching Mermaid blocks and image receipts. After reviewing a code change and updating the affected chapters/revision, use `--refresh-map` to explicitly accept a new source inventory. Regenerate changed figures with `render.mjs` before verification.
