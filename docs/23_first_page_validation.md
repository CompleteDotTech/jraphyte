# First-page evidence and retrieval validation

This optional local experiment is separate from the TRACE-GC graph compiler and
from the active Jev corpus worker. It evaluates **abstract extraction** and
**paper retrieval** separately. A retrieved page is not an accepted graph claim.

## Decision

Keep the geometry selector experimental. Its 200-paper holdout exposed incorrect
complete assessments. Use `trace_gc.pdf_admission.prepare_jev_request` for the
new evidence path: it requires an explicit source review, current file/page/image
hashes, and an intact review receipt. Partial, absent, uncertain and error reviews
are held. Complete text exceeding a request limit is held without truncation.

The current references are **assistant-reviewed**. Independent human validation
is outstanding. Receipt hashes detect accidental changes; they are not reviewer
signatures, authenticity proofs, or TRACE-GC publication authority.

## Implemented components

| Component | Purpose |
| --- | --- |
| `trace_gc/pdf_evidence.py` | Frozen experimental selector: geometric ordering, adjacent paragraphs/formulas, spaced Abstract headings, short abstracts, actual email detection, native text comparison, five dispositions, source boxes and hashes. |
| `trace_gc/pdf_admission.py` | Exact source-span review receipts and a review-gated Jev request builder. No network or database calls. |
| `src/abstract_validation/prepare.py` | Seeded fresh holdout and 30,000-work distractor pool, read-only corpus access. |
| `src/abstract_validation/extraction_trial.py` | Development evaluation, selector freeze and optional Docling conversion. |
| `src/abstract_validation/references.py` | Materialize manually selected source blocks; freeze reference hashes. |
| `src/abstract_validation/baselines.py` | Existing production extractor under its actual Python/PyMuPDF runtime. |
| `src/abstract_validation/retrieval_trial.py` | Render and embed a 10,000-work first-page index. |
| `src/abstract_validation/embedding_batch.py` | Atomic cost reservations, bounded concurrency, immutable call receipts and input-bound caches. |
| `src/abstract_validation/evaluate.py` | Separate extraction/admission metrics and rectangular query-to-document retrieval metrics. |
| `src/abstract_validation/audit.py` | Source-reviewed requests and a selective reprocessing plan; no corpus writes. |
| `src/abstract_validation/search.py` | Search the completed local page index with lexical, semantic or fixed hybrid ranking. |

## Holdout findings

The 200 fresh works contain 146 complete abstracts, 8 partial abstracts and 46
pages without abstract text. Sampling deliberately includes 120 previously
accepted and 80 skipped cases across nine diagnostic strata. These proportions
must not be extrapolated to the entire corpus.

| Method | Complete abstracts recovered at 98% text match | Correct proposed admissions | Wrong proposed admissions |
| --- | ---: | ---: | ---: |
| Current production extractor | 98 / 146 | 98 / 120 | 22 |
| Previous Docling selector, same conversions | 124 / 146 | 124 / 152 | 28 |
| Frozen geometry selector | 124 / 146 | 122 / 136 | 14 |

The geometry selector held all eight partial abstracts, but proposed five pages
without abstracts and nine incomplete/contaminated transcriptions as complete.
Its 89.7% admission precision on this diagnostic set is insufficient for automatic
promotion. The earlier 79/79 development result did not generalize to this holdout.

Principal causes: missing Index Terms boundaries; metadata sharing an abstract
box; Introduction in another column cutting the region; missing continuation
into a second column; publication/funding notices looking like narrative prose;
and native formula fragments arriving out of order. Boundary review is necessary
even when Docling and native text agree.

Ordered canonical character alignment ignores case, punctuation, whitespace and
Unicode compatibility differences. Passing requires at least 98% precision and
recall. Exact first/last 48-character matches are reported separately. Neither
measure certifies mathematical or scientific fidelity.

## Retrieval protocol

- 10,000 distinct works, one PDF version and first physical page per work.
- 300 targets (previous 100 plus fresh 200); 20 nearest native-text TF-IDF
  neighbors per target from 30,000 other works, then seeded random fill.
- Neighbor selection uses documents, not evaluation queries. These are topic
  proxies, not independently confirmed subject classifications.
- 100 previously written source queries; the Darkside-20k query erratum was
  corrected before this trial. New distractors test index scaling; the query
  cohort itself is not fresh.
- Gemini Embedding 2 uses 120-dpi page images and 768 dimensions. Controls are
  native word/bigram TF-IDF and fixed reciprocal-rank fusion (`k=60`).
- Report Recall@1/3/10, MRR and nDCG@10 with target identities mapped explicitly
  into the 10,000-document index. Scores are not probabilities.
- This is known-item retrieval with one designated target per query. Other
  relevant papers are not exhaustively labeled; this is not relevance precision,
  abstract correctness or downstream GraphRAG answer evaluation.

Completed retrieval results:

| Method | Recall@1 | Recall@3 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Native TF-IDF | 73% | 82% | 91% | 0.7889 |
| Gemini Embedding 2 | 90% | 97% | 100% | 0.9381 |
| Fixed RRF hybrid | 85% | 95% | 98% | 0.8960 |

Use Gemini as the primary retrieval method for this pilot. Keep the lexical
control available; fixed RRF reduced Recall@1 on this query cohort. The ten
Gemini top-1 misses all placed the designated target within the top seven.
The retained rankings permit later relevance adjudication without new API calls.

## Cost and isolation

The authorized Google project is `crossword-489306`. A separate SQLite ledger
reserves up to $12 conservatively; expected image usage is about $1.16. The first
100 cached page vectors are imported by matching image hash. They incur no new
charge in this trial. Every failed/ambiguous request retains its reservation;
retries require `--retry-errors`. The batch stops new submissions after five
failures in a pass. An interrupted in-flight call requires receipt reconciliation,
not blind resubmission. Provider invoices remain authoritative.

No credentials are included in output artifacts or repository files. Authentication
uses the already configured Cloud SDK identity. Only first-page images and query
text are submitted. No Jev API call is made by this validation suite.

Final incremental Google estimate: **$1.1498312**, with $9.915 in conservative
reservations. There were 9,900 successful new page calls, 100 successful query
calls and five HTTP 429 attempts. All five failed keys succeeded on retry; no
unresolved failures or duplicate successful calls remain. The stored-index search
smoke test reused a cached query and incurred no extra API call.

The source-reviewed 200-record plan has 94 exact requests to reuse, 21 changed
requests, 31 recovered requests and 54 holds. The estimated reservation for those
52 proposed evaluations is $0.004870068. It is a plan, not a completed rerun.
Any future executor must recheck the current checkpoint and reserve against the
existing **$50 corpus ledger**, preserving every historical attempt and charge.

## Reproduce locally

The scripts currently use the sibling `TRACE-GC_RealPaper_Test` data directory;
paths are centralized in `src/abstract_validation/common.py`. Raw PDFs, reference
text, vectors, receipts and costs remain outside Git in `validation_200_10k/`.
The old `sample_comparison_100/` artifacts remain intact.

Use the optional Python 3.12 benchmark environment for Docling, rendering and
retrieval. Recorded versions are in `environment.json`; the optional pinned
requirements are under `src/abstract_validation/requirements.txt`. Use the
production Python 3.14 environment for the current extractor and audit request
builder, to match the live PyMuPDF 1.27.2.2 behavior.

```powershell
# From the repository root; these commands reuse existing artifacts.
$benchPython = '..\TRACE-GC_RealPaper_Test\sample_comparison\.venv\Scripts\python.exe'
& $benchPython -X utf8 -m src.abstract_validation.prepare
& $benchPython -X utf8 -m src.abstract_validation.retrieval_trial render
& $benchPython -X utf8 -m src.abstract_validation.extraction_trial convert

# Complete source review/specs.json before opening holdout predictions.
& $benchPython -X utf8 -m src.abstract_validation.references
& 'C:\Python314\python.exe' -X utf8 -m src.abstract_validation.baselines
& $benchPython -X utf8 -m src.abstract_validation.evaluate extraction

# These two stages can incur Google API charges for uncached inputs.
& $benchPython -X utf8 -m src.abstract_validation.retrieval_trial embed --workers 8
& $benchPython -X utf8 -m src.abstract_validation.retrieval_trial queries --workers 2
& $benchPython -X utf8 -m src.abstract_validation.evaluate retrieval
& 'C:\Python314\python.exe' -X utf8 -m src.abstract_validation.audit
& $benchPython -X utf8 -m src.abstract_validation.report
```

For a genuinely new experiment, use a new output directory, prepare source-only
reference sheets and freeze the selector with `extraction_trial freeze` before
conversion/scoring. Never relabel a tuned rerun as an untouched holdout. A frozen
reference mismatch aborts evaluation. The reference process is manual; scripts
cannot establish independent human review.

See the local `validation_200_10k/REPORT.md`, `review/index.html`,
`extraction_metrics.json`, `retrieval_metrics.json`, `failure_analysis.json`,
`reprocessing_plan.json` and `cost.json` for the final trial artifacts.

After index evaluation, run a local lexical search with:

```powershell
& $benchPython -X utf8 -m src.abstract_validation.search 'dark matter data acquisition'
```

Add `--method semantic` or `--method hybrid` to use the stored page vectors.
An uncached semantic query can incur a small Google API charge against the same
trial ledger; cached exact queries are reused. Search results remain retrieval
candidates and do not bypass source review.

Provider references: [Google embedding documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/embeddings/get-multimodal-embeddings)
and [Google pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing).
The trial estimates cost from returned modality token counts (image $0.45/million,
text $0.20/million), with larger conservative reservations.
