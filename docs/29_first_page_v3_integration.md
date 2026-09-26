# First-page v3 integration: real-paper results

The v3 patch from `jraphyte-first-page-v3.zip` was applied to public `main` at `02e9c1fc530bec1b9a766caa4282ada2e5b957bf`. It remains an **experimental, review-only proposal path**. The frozen v1/v2 selectors, labels, admission gate, and corpus worker were not changed. All original PDFs, renders, model caches, and full per-paper receipts remain outside Git. The compact [integration receipt](../review/first_page_v3/integration_result.json) binds the external results by hash.

## Verified known 200-paper regression

The original 200 PDFs, retained page PDFs, renders, reference blocks, and frozen protocol were hash checked. All 1,200 saved assessments for the six previous methods reproduced from the frozen code and cached conversions. The cohort has 111 assistant-reviewed complete abstracts, 7 partial, and 82 absent. It is a previously examined regression set, not fresh validation.

| Method | Proposals | Correct at 98% | False proposals | Complete abstracts withheld | Correct proposals with matching boundaries |
|---|---:|---:|---:|---:|---:|
| Frozen structure v2 | 96 | 91 | 5 | 16 | 90 |
| Source v3 | 28 | 26 | 2 | 83 | 22 |
| GROBID verified v3 | 22 | 22 | 0 | 89 | 18 |
| MinerU v3 | 15 | 15 | 0 | 96 | 14 |
| olmOCR v3 | 20 | 20 | 0 | 91 | 17 |

The **preserve-91 gate fails**: source v3 withholds or mismatches 68 of the 91 previously correct structure-v2 proposals. Its 28 proposals have 26/28 = 92.86% precision and 26/111 = 23.42% complete-abstract recall on this diagnostic set. The previous structure-v2 figures were 91/96 = 94.79% and 91/111 = 81.98%. New v3 has lower recall and does not demonstrate a precision improvement. The experimental wrappers add no correct proposals when the source-v3 primary abstains. Automatic fallback and Jev admission remain disabled.

The dominant loss mechanisms in those 68 cases are 25 unfinished-final-sentence holds, 21 untrusted-boundary holds, and 14 headings with no prose found in the same geometric lane. Previously correct papers can have matching text yet still be withheld. The lane and closing-boundary requirements are too strict for common PDF line boxes and paragraph layouts. The remaining cases include unlabelled detection misses, a page-role veto, and source-v3 complete proposals with insufficient matching text. These are observed error classes, not resolved fixes.

The patch does fix concrete false-proposal mechanisms on this set: f030's Overview body and f192's dedication are excluded with matching source text; f199's author-list page is held absent. f119's colored synopsis and f150's column layout are now held uncertain, so they no longer produce false proposals but their real abstracts are not recovered. A zero-width combining-accent glyph previously caused two v3 adapter failures; the native-run validator now accepts only that valid accent case. A dot-leader line in f070 was also incorrectly proposed as an abstract; the punctuation-only check now holds it. Marked author footnotes found on a development sample now close the abstract before the note. The two remaining false proposals, f089 and f092, omit source words within otherwise relevant abstracts and fail the ordered 98% recall rule. They must not be admitted.

The final 200-paper replay completed in about 110 seconds with 200 original sources verified, 1,200 saved assessments reproduced, zero replay errors, zero paid model calls, and zero graph writes. Its command exited nonzero because the preservation gate failed, as intended.

## Fresh assistant-reviewed sample

After the final selector change, six previously unreviewed works were selected from the local distractor catalog, excluding the known 200, prior retrieval/holdout targets, and all earlier development samples. The assistant viewed each original first-page image and exact native intervals, then froze the references and code hashes **before** opening predictions. Five reviewed pages have complete first-page abstracts; one was held uncertain because its formula notation needs specialist math review. No independent human review occurred.

The `source_v3_native_only` path proposed **1/6** and matched that one reference and its boundaries at the same ordered 98% threshold. It withheld four of five complete abstracts, including one whose text already matched. Precision is 1/1 and complete-abstract recall is 1/5 on this very small sample; it cannot estimate a reliable false-positive rate. The method uses native source lines without Docling/GROBID corroboration, so these figures are not a direct estimate of the full regression pipeline. Earlier 20-, 12-, and 8-paper samples were evaluated under earlier code hashes and are retained outside Git as development evidence, not combined with this final sample.

## Validation and limits

The full current checkout validation ran offline with no provider calls or production graph writes: 419 tests, 416 passed, 3 skipped, 0 failures, 0 errors, with external qualification gates remaining. Package fixture validation and Python compilation also passed. The source archive builder was audited to exclude `.env` data, private PDFs, model weights, and temporary outputs. The patch author's files under `review/first_page_v3/` describe its original blocked handoff; `integration_result.json` and this report describe the reviewed checkout integration.

Full 10,000-document retrieval and local cross-encoder metrics were **not rerun** for this integration. The existing catalog supplies original paths for 10,000 PDFs but lacks source SHA-256 values for 9,900 of them; a new source-bound map and field pass would be required. No authorized local cross-encoder snapshot with a byte manifest was supplied. Candidate-only unit tests are not measured 10,000-document retrieval accuracy. The prior frozen 10,000-document results remain historical; do not attribute them to v3.

Independent human labels, specialist notation checks, an approved risk/coverage policy, a live provider test, and production qualification remain outstanding. This report does not authorize automatic abstract use, Jev requests, or graph mutations.
