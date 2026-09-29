# Reproduce the parallel first-page experiment

The experiment reads cached first-page conversions and writes immutable receipts under an authorized external data root. It does not call Jev or mutate a graph. Keep private PDFs, rendered pages, source maps, labels, model caches and full assessments outside this repository.

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
Set `TRACE_GC_TEST_DATA_ROOT` to the same absolute directory passed to `--data-root` before launching Python; the frozen v2 replay imports its data root at module load time. The CLI sets an unset variable before importing the baseline, but rejects a conflicting environment or an already imported baseline bound to another root. This supports a data directory that is not beside the checkout. Restart that Python process with the correct environment; do not reload modules or edit frozen source data.

### Install and verify the experiment runtime

The new validated Windows replay profile uses **CPython 3.12.10, PyMuPDF 1.28.0 (MuPDF 1.29.0), and Pillow 12.2.0**. `src/parallel_source_v4/requirements-replay.txt` pins these and every transitive dependency of the core validation environment. It is a small cached-conversion environment; it does not install or run Docling, OCR models, or model weights. Historical converter environments and their existing requirements remain unchanged.

This is **not a reconstruction of the historical PyMuPDF 1.28.2 environment**. Replaying its saved native bytes is explicitly different from extracting new native text with the new profile. The checked-in runtime lock includes the exact Python build, platform, Unicode tables, MuPDF and dependency versions. The receipt additionally hashes distribution metadata and native libraries. A platform or dependency mismatch blocks the experiment before selection.

With the actual Python 3.12.10 interpreter available, a clean PowerShell installation is:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r src/parallel_source_v4/requirements-replay.txt
.venv\Scripts\python.exe -m src.parallel_source_v4.runtime verify-lock
```

Verify the interpreter patch version; the launcher may choose another installed 3.12 patch. Use the explicit 3.12.10 executable in that case. The commands below assume this environment is active. On a different platform/runtime, deliberately create a new external profile with `python -m src.parallel_source_v4.runtime capture-lock --data-root /authorized/TRACE-GC_RealPaper_Test --output runs/new-runtime.lock.json`, inspect it, and pass its absolute path through `--runtime-lock`. Capture records a proposed new experiment identity, not historical reproduction or quality qualification; execute the fixture and empirical checks before declaring it validated.

### Fresh extraction

`fresh` reads the verified first-page PDF using the selected locked runtime. It records each new native representation and extractor identity. Preflight validates the baseline import root, source identities, converter JSON caches, original baseline lines and all saved v2 assessments before the V4 selection pass. A cached conversion receipt whose status is error/truncated remains a measured case; a missing cache is a blocked run.

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --native-mode fresh \
  --output validation_v3_private/parallel-v4-regression-next
```

Use `preflight` instead of `regression` with the same options to validate inputs without running V4 selection. The receipt contains the full repository-local import closure, including dynamically loaded frozen baseline helpers and every V4 module; changing the data-root helper or an imported metric changes the experiment identity. No historical protocol or reference is rewritten.

### Replay saved native evidence

First import an authorized archived V4 run. The caller must supply the previously recorded result hash. The capture verifies the source bindings and native bytes and preserves the archive's reported extractor identity and its limitations. Every parsed input is hashed from the same byte buffer, and every archive input used for provenance is rechecked before publishing the manifest. It never overwrites the archive or pretends to re-extract historical bytes.

```sh
python -m src.parallel_source_v4.runtime capture-native \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --run validation_v3_private/parallel-v4-regression-03 \
  --results-sha256 f9ee4f438c8cae7ce192970f7ff172ecbe7c24b3a383d48fe62cf75da7f4102b \
  --output validation_v3_private/saved-native-manifest.json
python -m src.parallel_source_v4.extraction regression \
  --data-root /authorized/TRACE-GC_RealPaper_Test \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --native-mode replay \
  --native-manifest validation_v3_private/saved-native-manifest.json \
  --native-manifest-sha256 REPLACE_WITH_CAPTURED_MANIFEST_SHA256 \
  --output validation_v3_private/parallel-v4-saved-native-next
```

Copy the SHA-256 printed by `capture-native`; a missing or changed external pin blocks the run. Replay loads exactly those native bytes without calling native extraction. Selected converters remain the authentic cached inputs. New outputs contain `native_manifest.json`, an explicit `native_mode`, the complete execution identity, and the content-bound `experiment_sha256`. Output-directory names and timings can differ while identical inputs produce identical assessment bytes.

To measure fresh extraction drift, use `--native-mode fresh` **with** that same pinned native manifest. `native_comparison.changed_ids` records every changed case; differing native inputs define a different experiment. Without a comparison manifest the receipt says `NO_REFERENCE_SUPPLIED`, rather than claiming unchanged native evidence. A saved-native/source identity mismatch blocks both modes.

For the optional source-geometry experiment, add `--source-geometry-policy source_fraction_v1` and retain the verified original-PDF source map. This mode extracts native lines from the original PDF's first physical page, then builds the vector/paint context from those exact bytes. It checks that the cached first-page copy has the same page size and records the original-source native digest and extraction origin in each native receipt. `--native-mode replay` is rejected for this mode because an archived page-copy extraction may differ from the original PDF even when its visible text and boxes agree. The default `disabled` mode keeps extracting from the cached first-page PDF. Use a new output directory for each mode and compare its native manifest to the pinned reference; a changed ID is a distinct input, not an extraction gain.

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

The freeze checks first-page source, image and native-span bindings, work-identity exposure, review attribution and the absence of pre-review conversion outputs. After freezing, create authentic conversion outputs at the manifest paths before running `python -m src.parallel_source_v4.extraction cohort --data-root ... --freeze ... --output ...`. Missing or malformed cache files block the run; authentic converter error/truncated receipts remain measured states. The eight-paper integration diagnostic deliberately uses only frozen native text.
The cohort runner checks the chosen `--runtime-lock` before assessment and consumes the exact native representation from the source-reviewed freeze; it does not silently re-extract native text after review. Its receipt reports `frozen_source_reviewed` separately from regression replay and fresh extraction. Both runners check source, page, image, native and converter identities plus complete code/runtime identities before and after assessment. Any observed mutation produces a redacted `BLOCKED` result, never a completed assessment under a stale receipt.

For the opt-in `source_fraction_v1` original-PDF geometry policy, a complete first-page abstract can use a source-located opening on physical page two as closing evidence. The page-one abstract must have an explicit source-located heading, terminal punctuation and no substantive continuation on page one; page two must visibly open with Introduction or Contents. The result records the page-two opening and exact page-one native spans as a review-only boundary. It never appends page-two text to the first-page candidate. A missing or ambiguous opening stays held. The [title-page regression receipt](../review/title_page_next_opening_v1/receipt.json) records this change on the examined 200-paper set; notation on f026/f131 and the overall 91-case preservation gate remain unresolved.

Running retrieval unit tests does not measure retrieval quality. A measured 10,000-paper run needs source-hashed fields for the candidate pool, a frozen query/target set, an authorized local model snapshot for neural reranking, and judged competing results. Keep those gates separate from selector results.
