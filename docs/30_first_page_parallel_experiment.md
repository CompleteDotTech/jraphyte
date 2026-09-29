# Parallel first-page source experiment

This integration reconciles `jraphyte-parallel-source-experiment.zip` (SHA-256 `9633b41bf8796f50b45335063ba1b89954bd46c517a0005377b136023579d9a5`) with public `main` after PR #2. The package was built against the older `02e9c1f` base and overlaps merged v3 files. Its selector and harness therefore live in separate `parallel_v4` modules. Frozen v1/v2, merged v3, the active corpus worker, Jev admission and the graph writer are unchanged. The new selector returns **review-only proposals**; automatic fallback remains disabled.

## Previously examined 200-paper regression

The run checked 200 original source PDFs, first-page PDFs and images, cached conversions, and frozen assistant-reviewed references: 111 complete abstracts, 7 partial, 82 without a first-page abstract. The table's historical text98 measure requires at least 98% ordered alphanumeric agreement; it does not establish source boundaries or scientific notation fidelity. This is a development regression set, not an independent held-out estimate. The previous v2 assessments replayed identically.

| Method | Proposed | Historical text98 correct | Historical text98 false | Complete withheld |
|---|---:|---:|---:|---:|
| Frozen structure v2 | 96 | 91 | 5 | 16 |
| Merged source v3 | 28 | 26 | 2 | 83 |
| Parallel primary v4 | 38 | 38 | 0 | 73 |
| Parallel GROBID v4 | 33 | 33 | 0 | 78 |
| Parallel MinerU v4 | 39 | 38 | 1 | 72 |
| Parallel olmOCR v4 | 40 | 40 | 0 | 71 |

The frozen v2 baseline has **91 historical text98 successes and 90 historical boundary-plus-text98 successes**. Case f195 adds a final footnote marker: it passes text98 but fails the historical boundary check. The table retains the original historical values; the 2026-09-27 rerun's olmOCR count is 39, which is a distinct environment/run result. Even the historical boundary check strips operators and punctuation, so neither historical measure certifies scientific transcription. [Versioned fidelity metrics](32_first_page_fidelity_metrics.md) add attributed source-span/image-region boundaries and notation diagnostics without rewriting these definitions or receipts.

The parallel primary recovers 19 complete abstracts that merged v3 lost relative to the 91 correct v2 cases. The **preserve-91 gate still fails**: it loses 55 of those 91 cases. Its 38/38 precision and 38/111 complete-abstract recall apply only to this known set. MinerU's false proposal is f039, so automatic MinerU fallback would add an error. No fallback is enabled.

All 200 parallel-primary and MinerU conversions report success. The cached GROBID route has one conversion error; the cached olmOCR route has three truncated conversions. These isolated states are counted in their method rows rather than dropped from the denominator.

The parallel selector initially proposed incomplete prefixes for f113 and f186. Their first-page images show structured Abstract subsections continuing after Methods. The selector now holds those uncertain. A first-page extraction check tolerates a maximum two-value RGB antialiasing difference after PyMuPDF page copying; the original source image and native spans must still match exactly.

## New source-first sample

Eight previously unexposed local works were selected by work identity, excluding known regression, retrieval and holdout works and earlier review samples. The assistant inspected original page images and native text, then froze references and code hashes **before** opening predictions. Six pages have complete abstracts; two math pages remain uncertain because native text garbles displayed formulae. This review is assistant-attributed, not independent human validation.

In a native-text-only diagnostic, merged v3 proposed 0/6 complete abstracts and parallel v4 proposed 1/6 correctly (q005), with no false proposals among eight pages. Parallel v4 withheld two other complete abstracts (q002 and q007) despite matching their text, because it did not establish a closing boundary. This tiny check used no Docling, GROBID, MinerU or olmOCR conversions and cannot estimate full-pipeline precision. The five authored PDF fixtures test distinct boundary counterexamples; they are not unseen papers.

The [reproduction notes](31_first_page_parallel_reproduction.md) describe the offline gates. The compact [integration receipt](../review/first_page_parallel_v4/integration_result.json) binds external run records without publishing PDFs, labels or full per-paper assessments. No paid model requests or production graph writes were made. Independent labels, specialist notation review, a preservation fix, a larger held-out cohort, and a source-bound 10,000-paper retrieval run remain outstanding. The included local retriever and reranker have no measured 10,000-paper result.

## 2026-09-29 native-field retrieval interim result

A later, frozen 10,000-document/60-query trial completed with the available native title and body fields plus two unreviewed OCR cover bodies. The [redacted interim receipt](../review/retrieval_native_10k_interim_v1/receipt.json) binds the source, model, code, runtime, ranking and integrity records. Current fields placed 59/60 known targets at rank 1 and 60/60 in the top 10; archived native-only fields placed 58/60 at rank 1 and 59/60 in the top 10. The image-only-cover target f076 moved from absent to rank 1. Five target-label rotation pairs passed. Twelve source errors remained in the 10,000-document denominator.

All 10,000 abstract assessments are absent from this trial. The frozen title-role defect tracked in #52 and the missing full V4 assessment map tracked in #53 prevent a repaired-field or full issue #22 qualification claim. No broader relevance judgment, graph admission, paid inference or production graph write occurred. This interim run supersedes the historical statement above only for the measured native-field baseline; the earlier parallel-selector experiment and its first-page quality claims are separate.
