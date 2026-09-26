# Reproduce the parallel first-page experiment

The experiment reads cached first-page conversions and writes immutable receipts under an authorized external data root. It does not call Jev or mutate a graph. Keep private PDFs, rendered pages, source maps, labels, model caches and full assessments outside this repository. Install the project's pinned validation requirements and PyMuPDF/Pillow locally.

The versioned modules are `trace_gc/pdf_source_parallel_v4.py`, `trace_gc/pdf_structure_parallel_v4.py` and `src/parallel_source_v4/`. They do not replace merged v3 or frozen v1/v2. The original archive overlay was built against an older base and must not be applied to current main; use this reconciled checkout.

## Offline checks

```sh
python -m unittest discover -s tests -p 'test_parallel_source*v4.py' -q
python tools/run_validation.py
python -m compileall -q trace_gc/pdf_source_parallel_v4.py trace_gc/pdf_structure_parallel_v4.py src/parallel_source_v4
python tools/validate_package.py
```

PDF fixture tests skip when optional PyMuPDF or Pillow is unavailable, as in the core-only hosted workflow. On Windows, one symlink test skips if the account lacks symlink privilege. Offline validation does not satisfy external provider or deployment gates.

## Known 200-paper replay

Supply the original external `validation_v2/` and `validation_expanded200/` caches and an external JSON mapping each `f001`–`f200` ID to a relative original PDF path under the data root. The harness checks the frozen protocol, source/page/image hashes and saved v2 assessments. Use a new output directory each time because receipts are immutable.

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --output validation_v3_private/parallel-v4-regression-next
```

Exit code 1 is expected while the preservation gate fails. Inspect `results.json`, including `saved_replay_gate`, `preserve_91_gate`, four method metrics, conversion states and per-case reasons. A blocked preflight exits 2 and must not count as a completed run. Automatic fallback stays disabled.

## Source-first new papers

`prepare` takes a JSON array of `{sample_id, work_id, source_relative}` entries. It emits page-one PDFs, images, exact native spans and a manifest without predictions. Review images and spans first. Labels keyed by `sample_id` require `status`, exact `text`, and attributed `source_review` with a timezone-aware time, `source_before_predictions: true`, matching image/native hashes, exact native `reference_spans`, and a reviewed `closing_boundary` for complete abstracts. Use `uncertain` when specialist review is needed. An assistant review must be attributed to the assistant.

```sh
python -m src.parallel_source_v4.prepare \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --sources validation_v3_private/new-cohort/sources.json \
  --output validation_v3_private/new-cohort/source-views
python -m src.parallel_source_v4.freeze \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --manifest validation_v3_private/new-cohort/source-views/manifest.json \
  --labels validation_v3_private/new-cohort/labels.json \
  --exposure-registry validation_v3_private/new-cohort/exposure-registry.json \
  --output validation_v3_private/new-cohort/freeze-01.json
```

The freeze checks first-page source, image and native-span bindings, work-identity exposure, review attribution and the absence of pre-review conversion outputs. After freezing, create authentic conversion outputs at the manifest paths before running `python -m src.parallel_source_v4.extraction cohort --data-root ... --freeze ... --output ...`. Missing converters produce isolated errors, not successful measurements. The eight-paper integration diagnostic deliberately uses only frozen native text.

Running retrieval unit tests does not measure retrieval quality. A measured 10,000-paper run needs source-hashed fields for the candidate pool, a frozen query/target set, an authorized local model snapshot for neural reranking, and judged competing results. Keep those gates separate from selector results.
