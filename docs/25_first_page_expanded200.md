# Expanded 200-paper local comparison

The fresh evaluation was expanded from 100 to 200 distinct papers: the earlier 100 plus 100 additional works. Each cohort contains 50 previously successful and 50 previously skipped papers. This is a diagnostic sample, not an estimate of corpus prevalence.

All six extraction pipelines used the same 200 physical first pages. The prior 100 source references and parser caches were preserved. Added references and 30 new queries were frozen before opening their predictions; the methods were frozen before selection. References were reviewed by the assistant; independent human validation remains outstanding.

## Extraction

References: **111 complete abstracts, 7 partial abstracts, 82 pages without an abstract**. Correct means a complete source reference with at least 98% ordered canonical alphanumeric precision and recall. A proposal is not permission to send text to Jev.

| Pipeline | Correct / proposed | Precision | Complete abstracts recovered as correct proposals | Correct with boundary check |
|---|---:|---:|---:|---:|
| Production baseline | 77/100 | 77.0% | 77/111 | 70 |
| Docling + geometry v1 | 80/99 | 80.8% | 80/111 | 80 |
| GROBID | 92/113 | 81.4% | 92/111 | 89 |
| Docling + structure v2 | 91/96 | 94.8% | 91/111 | 90 |
| MinerU + structure v2 | 77/83 | 92.8% | 77/111 | 75 |
| olmOCR + structure v2 | 41/43 | 95.3% | 41/111 | 34 |

### Added 100 separately

| Pipeline | Correct / proposed | Precision |
|---|---:|---:|
| Production baseline | 37/50 | 74.0% |
| Docling + geometry v1 | 39/52 | 75.0% |
| GROBID | 47/55 | 85.5% |
| Docling + structure v2 | 46/50 | 92.0% |
| MinerU + structure v2 | 36/41 | 87.8% |
| olmOCR + structure v2 | 20/21 | 95.2% |

### Remaining structure-selector errors

- f030 (prior): inline Overview text extends the selected region.
- f119: a separate colored synopsis is appended to the bold abstract.
- f150: the wrong column is selected instead of the bold abstract.
- f192: a dedication is appended to the abstract.
- f199: an author list is proposed as an unlabelled abstract.

These are retained test failures. No selector tuning was performed on the added 100. Mathematical notation also needs source review: normalized text agreement can hide detached radicals, flattened fractions, or lost superscripts. Flagged cases are listed in the results artifact; no production requests were prepared or executed by this experiment.

f151 contains an Executive Summary and is classified as no separate abstract. Its per-method proposals are retained for a sensitivity check; counting this as an abstract would raise the complete-reference denominator to 112.

## Local fallback increment

When used only where structure v2 abstained, the following additional proposals appeared. These counts describe the frozen pipeline, not standalone OCR accuracy.

| Fallback | Additional correct | Additional wrong |
|---|---:|---:|
| MinerU + structure v2 | 1 | 3 |
| olmOCR + structure v2 | 0 | 1 |

## Retrieval

60 source-authored known-item queries (30 prior, 30 added) were searched against the same 10,000-paper index. The local reranker uses the union of the top 50 BM25F and top 50 SPECTER2 candidates, with no target insertion. An absent target gets zero reciprocal-rank credit.

| Local method | Top 1 / 60 | Top 10 / 60 | Added top 1 / 30 | MRR |
|---|---:|---:|---:|---:|
| specter2 | 56 | 58 | 29 | 0.947 |
| bm25_page | 55 | 58 | 28 | 0.932 |
| bm25f | 55 | 57 | 29 | 0.932 |
| local_pooled_reranker | 57 | 58 | 29 | 0.958 |

The shared top-10 misses were f076 (an image-only book cover whose local text fields are empty) and f115 (a graphical-abstract cover). For f115, the automatic title field contains only `Graphical Abstract`, its abstract field is empty, and the real paper title appears only in the body. SPECTER2 therefore receives an uninformative input; BM25F ranks the target 226, full-page BM25 ranks it 44, and the local reranker never sees it. The observed failure comes from title extraction and candidate selection.

Gemini was not run on the added queries. Its earlier 27/30 top-1 and 30/30 top-10 result is a historical reference only. The earlier reranker used Gemini candidates, so its result is not the same configuration as this local-only reranker.

## Runtime and cost

| Vision pipeline | New inferences / reused | New inference minutes | Output states |
|---|---:|---:|---|
| mineru | 180 / 20 | 136.2 | {'success': 200} |
| olmocr | 180 / 20 | 169.9 | {'success': 197, 'truncated': 3} |

**New paid API calls: 0. New estimated API spend: $0.** Local electricity and hardware costs were not measured. Both model weights were already downloaded. The Google ledger was read in read-only mode and verified unchanged. No Jev calls or graph writes were made by the experiment.

## Interpretation and limits

Keep source review mandatory. The expanded test exposes additional false proposals, so these results do not qualify automatic acceptance. Use retrieval as a way to find papers; it does not validate extracted abstract boundaries or scientific notation.

- Assistant-reviewed references; independent human validation outstanding.
- Diagnostic sample balanced by prior ok/no_abstract status, not representative corpus prevalence.
- Prior100 was already evaluated; added100 uses methods frozen before selection and predictions.
- Canonical character matching is not exact punctuation, layout, or scientific formula fidelity.
- One labeled target per retrieval query; other relevant papers were not exhaustively judged.
- Local reranker candidate pool excludes Gemini; its prior30 result differs from the earlier three-method pool.
- olmOCR uses NF4 direct Transformers decoding, a 4096-token cap, and native alignment; this is not the complete upstream pipeline.
- MinerU and olmOCR results use the same conservative v2 selector and native-text projection; these are pipeline scores, not standalone OCR accuracy.
- Shared workstation timings are observed times, not controlled throughput measurements. Recorded inference time excludes model loading, paused time, and any interrupted attempt that did not save a result; olmOCR resumed from its 149 saved results.

## Reproduce

From the repository root, using the existing CPU/Docling environment for preparation, conversion and scoring, and the model environment for vision and retrieval:

```text
python -m src.abstract_validation_expanded.prepare
python -m src.abstract_validation_expanded.convert current
python -m src.abstract_validation_expanded.convert docling
python -m src.abstract_validation_expanded.convert grobid
python -m src.abstract_validation_expanded.references
python -m src.abstract_validation_expanded.vision mineru
python -m src.abstract_validation_expanded.vision olmocr
python -m src.abstract_validation_expanded.extraction
python -m src.abstract_validation_expanded.retrieval
python -m src.abstract_validation_expanded.verify
python -m src.abstract_validation_expanded.report
```

The baseline was run with the production Python/PyMuPDF environment. GROBID uses the existing pinned local container at 127.0.0.1:18070. The model environment uses local-only model paths, CPU retrieval, MinerU BF16 and olmOCR NF4, with unchanged v2 settings. All retained source pages, 400 vision input receipts, and frozen protocols are hash checked. Empty successful GROBID conversions are labeled absent in the assessment; this reporting correction was checked to leave all 200 texts and proposal decisions unchanged.

Private source PDFs, rendered pages, full parser outputs, and model weights remain outside this checkout in `../TRACE-GC_RealPaper_Test/validation_expanded200`. Portable source hashes, annotation specs, query text, and compact results are under `review/first_page_expanded200/`.
