# Versioned first-page fidelity metrics

Issue [#14](https://github.com/CompleteDotTech/jraphyte/issues/14) adds evaluation beside the frozen scores. It changes no selector, alignment threshold, source admission policy or historical receipt.

## Metric identities and interpretation

| Identity | Property measured |
|---|---|
| `ordered-alphanumeric-text98-boundary48-v1` | Existing `canonical()` / `compare()`: ordered alphanumeric agreement, the original 98% threshold, and the original 48-character prefix/suffix approximation. |
| `notation-reviewed-source-boundary-v1` | Conservative ordered transcription comparison plus attributed, source-bound boundary/reading-order review. |

Existing `text_match_98`, `boundary_and_98_match`, precision and recall retain their exact behavior. New per-case results are under `fidelity`; summaries include both identities. Missing reviews become `unresolved`, including historical labels that never recorded the new evidence. A matching withheld candidate remains withheld. An all-abstain result has zero complete-abstract recall and no measured proposal precision.

The frozen 200-paper v2 baseline remains **91 historical text98 / 90 historical boundary-plus-text98**. f195 is traceable as text98=true and boundary-plus-text98=false. This metric change does not repair its selector output; that belongs to section-boundary work.

## Notation policy

`compare_notation()` retains case, operators, negation, signs, punctuation, units and equation/token order. It permits only:

- Unicode NFC composition, Unicode mathematical minus `−` to `-`, and the presentation ligatures U+FB00–U+FB06 to their letter sequences.
- Whitespace between tokens, including newlines; insertion/removal inside a word or compound operator is not equivalent. Factorial followed by equality (`n! = m`) differs from inequality (`n != m`).
- Unicode superscript/subscript digit runs and supported script signs to explicit `^{...}` / `_{...}` structure. ASCII scripts with an unambiguous unbraced digit run or one letter are normalized to the same braced form. Adjacent alphanumeric or decimal continuations remain literal; `x^12a` never becomes `x^{1}2a`.

Thus `x²` and `x^{2}` agree; `x²` and `x₂` differ. `x = 1` versus `x != 1`, `x + y` versus `x - y`, and `10^5` versus `105` fail although their historical scores pass. Unit changes (`mg` to `g`, `mM` to `mm`) and reordered equations fail. Algebraically equivalent expressions are not automatically equivalent transcriptions.

The machine comparison can report a mismatch without an adequate source review. That mismatch is a diagnostic, not a measured scientific error: it may reflect bad reference transcription, extraction loss or an unapproved normalization. Attribution and evidence are required before a notation result can pass.

## Review contract

A label may add `fidelity_review` without changing its historical `text` or `status`. Existing frozen labels must remain byte-preserved: use a separately hashed reviewed label file and identify it in a new experiment or rescore receipt.

The object contains `reviewer_kind` (`human` or `assistant`), `reviewer`, timezone-aware `reviewed_at`, `source_sha256`, `page_sha256`, and SHA-256 of the exact UTF-8 label text as `reference_text_sha256`. Each dimension has `status` in `pass/fail/unresolved/not_applicable` and an external evidence identifier `evidence_id`. The caller supplies a timezone-aware `evaluated_at` to `score_case()` or `evaluate_fidelity()`; missing evaluation context or a review dated after that time remains unresolved. The rescore command captures and records one evaluation time, rejects future evaluation times, and accepts `--evaluated-at` to replay the same review decision. Review attribution is recorded; human independence and the authenticity of an assertion are not inferred by the scorer.

`notation.status=pass` means the reference transcription was checked against the source under the documented normalization policy. A failed or unresolved reference review makes candidate notation fidelity unresolved, with the original review status visible. `not_applicable` requires attribution and cannot clear a `math_review_required` hold. A passed review can resolve such a hold; the review must actually cover the notation.

A boundary review with `status=pass` needs `section_owner="abstract"`, a reviewed `closing_boundary`, and one representation:

- `native_spans`: matching `native_sha256` plus ordered `reference_spans`, using source `line_id/start/end/page_no`. Optional `excluded_spans` objects contain `role` (`footnote/metadata/body/other`) and `spans` to attribute contamination.
- `image_regions`: matching `image_sha256`, `page_size=[width,height]`, and ordered `reference_regions` with `page_no=1`, `coord_origin="TOPLEFT"` and finite in-page `bbox=[x0,y0,x1,y1]`. The first version requires exact reviewed boxes, not guessed overlap thresholds; changed crops require new review.

The prediction supplies the same source/page identity, representation hash, its `spans` or `image_regions`, and `section_owner`. Upstream source preparation/review must validate offsets and coordinates against the hashed artifact. The scorer compares identities and selected extents; it neither opens source PDFs nor fabricates missing evidence. Source-binding status is distinct from transcription fidelity and review status.

Native comparison exposes missing/extra positions, prefix/suffix contamination and reviewed excluded roles independently of approximate text agreement. Ordered positions measure reading order separately: the same source extent in a different sequence fails order. Adjacent span segmentation is harmless. Image-only reviews need no fabricated native offsets. Missing ownership, mismatched representation hashes, malformed evidence and incomplete reference reviews stay unresolved. A review assigning the same position to the abstract and an excluded body/metadata/footnote role is contradictory and remains unresolved. A reviewed mismatch fails; unresolved cases cannot count as verified correct. Verified proposals also require `status="complete"`, boolean `proposal=true` and `complete_candidate=true`; contradictory error/partial states cannot qualify.

## Summaries and immutable rescoring

Summaries retain all pages, gold/predicted/conversion states, partial/absent false proposals, withheld cases and legacy errors. New summaries expose eligible reviewed denominators, four-state counts, reviewed failures, unresolved workload, notation mismatch diagnostics and verified complete-abstract recall. `gold_scope_false_proposals` counts proposals against known partial/absent references; `source_dimension_false_proposals` counts reviewed notation/boundary/order failures; `reviewed_false_proposals` is their union. `verified_fraction_of_all_proposals` is deliberately a conservative fraction of all proposals; unresolved proposals are not silently called false or dropped. No value establishes production calibration or graph admission.

Run authored positive/adversarial tests:

```sh
python -m unittest discover -s tests -p 'test_parallel_source_fidelity_v4.py' -q
python -m unittest discover -s tests -p 'test_parallel_source*v4.py' -q
```

Re-evaluate actual saved assessments into a **new external directory**:

```sh
python -m src.parallel_source_v4.fidelity_report \
  --data-root "${TRACE_GC_TEST_DATA_ROOT}" \
  --run validation_v3_private/parallel-v4-regression-rerun-20260927-220439 \
  --output validation_v3_private/fidelity-rescore-next
```

The default labels and frozen baseline are `validation_expanded200/labels.json` and `validation_expanded200/assessments/structure_v2`. `--labels` and `--baseline` can identify separate authorized inputs. The command requires each method to retain all uniquely labelled cases, verifies V4 assessment seals, legacy per-case values and the original baseline summary, and hashes the exact bytes it parses before rechecking every input prior to publication. Duplicate JSON keys and nonfinite values are rejected. It writes through the existing immutable receipt mechanism and rejects historical input directories as destinations.

The 2026-09-28 saved-assessment rescore covered all four current methods × 200 cases plus 200 frozen baseline assessments. The [compact receipt](../review/first_page_fidelity_v1/evaluation_receipt.json) binds all 1,002 input artifacts and the external result by hash. Every legacy score replayed unchanged. Current primary/GROBID/MinerU/olmOCR text98 success counts remain 38/33/38/39. All 200 cases per method lack the new typed review evidence and remain unresolved for verified fidelity. This is honest missing evidence, not a new extraction failure or an error-free result. No PDFs, labels or historical assessments were changed; no paid calls or graph writes occurred.

Selector preservation, the integrated 200-paper quality gate, independent notation/boundary review and unseen-cohort qualification remain open. Passing these authored tests or rescoring cached predictions does not satisfy those gates. The evaluation patterns in [olmOCR-Bench](https://github.com/allenai/olmocr/blob/main/olmocr/bench/tests.py) and [OmniDocBench](https://arxiv.org/abs/2412.07626) motivate separate measures; they provide no local accuracy result.
