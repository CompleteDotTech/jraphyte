# First-page source v3: implementation evidence and blocked empirical gates

> This document records the **supplied patch author's environment and claims**. The patch was subsequently integrated and tested in the real checkout; see [the integration report](29_first_page_v3_integration.md) for current results. The blocked and 390-test receipts below are historical provenance, not current gates.

**2026-09-26. Experimental patch; not production qualification.**

Base public main: `02e9c1fc530bec1b9a766caa4282ada2e5b957bf`. The same main was observed at the end of this work. No applicable `AGENTS.md` was found in the inspected root, source, tool or test directories. The [200-paper report](25_first_page_expanded200.md), [root-cause audit](26_first_page_failure_root_causes.md), and compact protocol/results/review receipts were read before editing.

## Delivery status

The implementation is delivered as a source patch, not a merged PR. The connected GitHub installation reports `pull=true`, `push=false`, and an actual attempt to create `fix/first-page-source-bound-v3` returned HTTP 403, `Resource not accessible by integration`. The container has no configured SSH signing identity or agent. Direct cloning also failed DNS resolution. No unsigned substitute commit was created. No remote branch, PR, merge or mirror push occurred.

This environment did not contain a current-main checkout. New paths and the two modified-file preimages were checked against the pinned public main. A public historical byte cache was used to assemble a separate validation runtime, with current core/PDF files reconstructed and checked against Git blob hashes. **That runtime is not the complete current-main snapshot.** Its broader test result must not be represented as current-main CI. The full checkout/CI and root release-manifest regeneration gates remain open.

Existing main's GitHub workflow run `36223478580` was successful, but predates this patch. Main's merge commit has GitHub-verified PGP signing; the preceding existing author commit has verified SSH signing. Neither is a signature on this work. The local work area is a non-Git patch workspace: there is no local merged main or meaningful ahead/behind/clean-main claim. No private mirror was accessed.

Machine-readable details: [delivery gate](../review/first_page_v3/delivery_gate.json), [validation scope](../review/first_page_v3/validation_scope.json), [verified baseline bytes](../review/first_page_v3/verified_baseline_bytes.json).

## What changed and why

`trace_gc/pdf_source_v3.py` is a **new native-source-first proposal method**, not a silent change to structure v2. Geometry v1, structure v2, their frozen protocol, original labels and old receipts are unchanged. Native text is selected with exact line IDs and character intervals; retained bounds are explicitly the containing native line, not fabricated character boxes. Returned text reconstructs from those intervals. Source hashes are only bindings until the file harness verifies actual bytes.

An explicit abstract anchor or a source-backed unlabelled candidate must have a structural closing boundary. A terminal period above the page bottom is no longer sufficient. Section starts, metadata, affiliation, author notes, dedication and author lists are recognized at source-line/run boundaries and supported inline boundaries, including when the PDF groups them with abstract prose. General rules, not case IDs or article quotations, control selection. A real-PDF fixture also verifies black text on a separate colored vector panel: native fill evidence is retained even when font color does not change. Raster-only panel semantics can still require image review.

| Saved regression mechanism | Focused evidence and v3 behavior | Actual private case replay |
|---|---|---|
| f030: Overview body included | Differential fixture: frozen v2 proposes the appended body; v3 stops at inline/run-supported Overview | Outstanding |
| f119: separate colored synopsis | Differential fixture: v2 includes it; v3 exposes the source prefix and **holds it as uncertain** because typography alone is not semantic proof | Outstanding |
| f150: wrong column, bold abstract left | Native region/column tests reject a reversed reading tree; a right-column control prevents a hard-coded left preference | Outstanding |
| f192: dedication | Differential fixture: v2 includes the dedication; v3 stops at its metadata boundary | Outstanding |
| f199: author list | Author-list, affiliation and author-note fixtures reject field-backed false proposals | Outstanding |

Column continuation is not resolved by arbitrary proximity or tree order alone. A bottom-of-column prefix can continue into a separate upper-page column only when the exact concatenation is uniquely witnessed in the filtered reading-order tree and the continuation has a structural closing boundary. An unfinished sentence requires a lower-case continuation; a sentence-ended prefix additionally requires a located scholarly field covering the concatenation. A valid frozen-v2 column-wrap fixture is retained, and counterexamples with a non-bottom prefix or uncorroborated terminal sentence remain held. More complex or ambiguous layouts can still lose coverage; the private preservation gate is mandatory.

### Scholarly fields and OCR

GROBID text is corroboration, never direct evidence that an abstract exists on physical page one. The wrapper checks field location, source role, boundary and complete candidate agreement. Highlights, key points, captions, author metadata, partial abstracts and Executive Summary controls are not upgraded simply because a field matches. f076's GROBID 500 remains a conversion error with no invented text.

The old olmOCR adapter matched whole native lines as substrings and assigned full-page placeholder boxes to unmatched paragraphs. V3 locates unique contiguous normalized intervals and maps them back to exact native characters. Fixtures cover merged/split paragraphs, line wraps, ligatures, hyphenation, paragraphs embedded inside a native line, duplicate locations and missing words. Approximate-only, ambiguous and image-only text remains review-only; no placeholder rectangle is emitted. This is native alignment, **not model-predicted coordinates** and not a claim that OCR itself became more accurate.

The candidate text must be uniquely supported by the cached OCR conversion. A source-supported native proposal, a model conversion, and a model-supported selector proposal are recorded separately. A 4,096-token generation cap is `truncated`; a complete abstract exceeding the 4,000-character request budget remains complete text with an independent budget hold. Neither state silently truncates evidence. The 14 historical math cases remain explicit source-notation review holds.

### Retrieval

The new title path rejects page-type labels such as “Graphical Abstract”, uses native style and adjacent title lines, and retains full first-page body text. Full-page BM25 contributes its own top-50 candidates before reranking, alongside the field-weighted lexical and optional source-bound cached SPECTER2 channel. Candidate generation accepts no labelled target argument; zero-score empty fields are not smuggled into top-k ties.

An image-only cover remains unindexable until there is an actual reviewed first-page image transcription. This is retrieval metadata only. Its wrapper checks source/page/image bindings and reproduces the first-page image; it never invents a title from a filename or an expected target.

A local scalar cross-encoder adapter is supplied for authorized external snapshots. It verifies every model-file hash against a pinned manifest, refuses remote code/pickled weights/downloads, and emits candidate/pair-bound score receipts. Its declared upstream revision is not independently verified by merely supplying a manifest. No model-backed run was possible here: Transformers and model weights are absent. Candidate-only evaluation reports reranker metrics as unavailable rather than borrowing old scores. The new lexical weighting is explicitly **not identical to frozen v2 BM25F**.

Reranker pair truncation (512-token longest-first limit) is recorded separately from abstract completeness and Jev request budgets. f020's competitor remains unjudged; a labelled target at rank two does not establish that rank one is irrelevant.

## Historical regression baseline, not new measurements

The already examined 200 pages are a regression set: **111 complete, 7 partial, 82 absent**. References were assistant-reviewed; independent human validation remains outstanding. The preserved scoring is ordered NFKD/alphanumeric character matching with both precision and recall at least 0.98, gold status complete, and a separate first/last-48-character boundary check. `proposed` applies the historical 4,000-character budget; it is not a request authorization.

| Frozen method | Proposals | Correct >=98% | False proposals | Withheld complete | Boundary-and-98% correct proposals |
|---|---:|---:|---:|---:|---:|
| Current baseline | 100 | 77 | 23 | 13 | 70 |
| Geometry v1 | 99 | 80 | 19 | 19 | 80 |
| GROBID field baseline | 113 | 92 | 21 | 13 | 89 |
| Structure v2 | 96 | 91 | 5 | 16 | 90 |
| MinerU | 83 | 77 | 6 | 30 | 75 |
| olmOCR | 43 | 41 | 2 | 69 | 34 |

Structure v2's historical proposal precision is 91/96 = **94.79%**, and complete-abstract proposal recall is 91/111 = **81.98%**. Of its 16 withheld complete abstracts, eight already matched the reference. Of olmOCR's 69 withheld complete abstracts, 41 matched, including 39 native-agreement failures. These are saved observations, not rerun results.

The GROBID baseline proposed 15 non-complete cases (partial or absent); a field cannot serve as a completeness/admission shortcut. The frozen structure v2 and geometry v1 source bytes reproduce their recorded method hashes exactly, but **unchanged code hashes are not proof that v3 preserves the 91 correct papers**. That gate is not run. No source-supported reference correction was made. f151 remains the boundary-sensitive Executive Summary reference, not relabelled as a separate abstract.

On primary abstentions, saved MinerU additions were one correct (f023), three wrong (f041/f128/f136); saved olmOCR additions were zero correct, one wrong (f068). New empirical fallback increment is unavailable. Automatic fallback remains disabled regardless of fixture success.

Historical local retrieval used 60 queries and 10,000 documents: reranker top-1 57/60, top-10 58/60, MRR 0.9583333333, candidate coverage 58/60. f076 and f115 were pool misses. **No new 10,000-document retrieval scores were measured here.**

## New empirical status and error ledger

| Requested new measurement | Known 200 regression | New unseen real-paper cohort |
|---|---|---|
| Pages assessed | 0 | 0 |
| Source-reviewed, frozen new papers | Not applicable: previously seen | 0 |
| Proposal precision / complete-abstract recall | Not measured | Not measured |
| Boundary accuracy / partial-absent false positives | Not measured | Not measured |
| OCR states / matching texts held / fallback increment | Not measured | Not measured |
| Retrieval top-1/top-10/MRR/candidate coverage | Not measured | Not measured |
| Original PDF/page/image hashes reverified | Not run | Not run |
| Preservation of 91 correct v2 proposals | Not run | Not applicable |

The private PDFs, page renders, source spans, cached model conversions/assessments and weights are unavailable. The comparison command exited **2 / BLOCKED**, with an immutable [receipt](../review/first_page_v3/regression_gate.json), not a fabricated success or partial-cohort aggregate. It could not newly inspect the actual f030/f119/f150/f192/f199 source images, nor replay the held matching-text cases.

The new source-first preparation/freeze tools reject known source/work overlap, prediction-first declarations, changed source bytes, changed labels, changed code and unbound image/native references. Reviewer declarations remain attestations, not proof of independence or of what a reviewer has previously seen. A synthetic two-page fixture exercises the freeze mechanism and was visually inspected, but **it is not an unseen real-paper cohort or an empirical accuracy estimate**.

[Error ledger](../review/first_page_v3/error_ledger.json) retains case IDs, the saved causal evidence, fixture coverage and unresolved source-review work. Math holds: f026, f033, f103, f111, f122, f125, f131, f142, f146, f153, f154, f158, f166, f189.

## Local validation

| Exact command | Result | Scope |
|---|---|---|
| `python -m unittest discover -s tests -p '*v3*.py' -v` | **80/80 passed**, 0 skipped, 0.247 s | New focused selector, differential, retrieval, freeze, I/O, local-model boundary and package-safety tests |
| `python -m unittest discover -s tests -p 'test_pdf_structure.py' -v` | **6/6 passed**, 0.003 s | Exact current-main frozen-v2 test file; Git blob verified |
| `python tools/run_validation.py` | **390 passed, 1 skipped**, 391 run, 16.949 s unittest time; exit 0 | Reconstructed reference runtime plus patch, **not a complete main checkout** |
| `python tools/validate_package.py` | PASS, exit 0; 12 schemas, 17 fixture records | Existing legacy synthetic fixture contract validation |
| `python -m compileall -q trace_gc/pdf_source_v3.py src/abstract_validation_v3 tests tools/package_project.py` | PASS, exit 0 | Syntax/import compilation, not model execution |
| `python -m src.abstract_validation_v3.evaluate --data-root /mnt/data/authorized-inputs-unavailable --out /mnt/data/v3-regression-gate` | BLOCKED, exit 2 | Missing authorized source evidence; no aggregate accuracy claim |

The broader run used older revisions of `test_runtime_contracts.py` and `test_runtime_transactions.py` and did not include current-main `test_abstract_validation.py`, `test_expanded_retrieval.py`, `test_pdf_admission.py`, or `test_pdf_evidence.py`. These differences are explicit in the [scope receipt](../review/first_page_v3/validation_scope.json); the complete main gate remains outstanding. The one skip requires the external pinned legacy `core.py`. Live provider, deployed backend, controlled pilot, trained-provider and production-calibration gates remain unavailable or unqualified.

**Paid model-provider requests made by this work: 0; corresponding spend: $0.00.** No provider billing reconciliation was performed. GitHub metadata reads are separate from model-provider requests. No external corpus worker was accessed or changed, and there were no production/external graph writes. The required broader validation did execute isolated synthetic reference-database transactions in temporary test databases; these are not production graph updates.

## Packaging, authority and next gates

The patch adds Git ignores for external paper/model artifacts and hardens the source ZIP builder: tracked-only default, no nested archives/wheels, private PDF/model/cache/output exclusion, env exceptions only for `.env.example`, symlink rejection, file-signature/key checks, deterministic entries and complete member/hash auditing. The patch bundle itself has a byte manifest and contains no PDFs, weights, `.env` secrets or temporary model outputs. It is **not a full current-main public release ZIP**; regenerate and audit the repository root `MANIFEST.json` on the authorized checkout before committing a full release. The scoped change manifest must not replace the full repository manifest.

All v3 proposals retain `eligible_for_jev=false`, `verified_admission=false`, and `source_review_required`. The existing admission and transaction code is unchanged. Tests explicitly reject passing an unreviewed v3 proposal as a Jev review. High similarity, a located field, a passed test, an assistant label, or a good candidate rank grants no publication authority.

Before stronger claims: replay the frozen 200 with actual source verification; resolve losses against the 91 successes without target-specific fixes; freeze and evaluate genuinely unseen source-reviewed papers; review all math/role/notation holds; measure candidate coverage and real local reranking separately; obtain independent labels and approved risk/coverage policy. GitHub completion additionally requires write-enabled access and the configured SSH signer, followed by the full checkout tests, hosted checks/review gates, merge and verified clean synchronization. No current result justifies enabling automatic fallback or production qualification.

See [reproduction and delivery instructions](28_first_page_v3_reproduction.md).
