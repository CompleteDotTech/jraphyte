# First-page extraction and retrieval follow-up

This experiment implements the research recommendations using a separate v2
selector and reproducible local model adapters. It leaves the frozen v1 artifacts,
corpus worker, Jev budget, and graph admission authority intact.

Aggregate results are in
[`review/first_page_validation_v2/results.json`](../review/first_page_validation_v2/results.json).
Raw conversions, source images, references, input hashes, API receipts, model
weights, timing logs, and per-query rankings remain in the local sibling
`TRACE-GC_RealPaper_Test/validation_v2` directory. They are not packaged as source.

## Protocol

- The previous 200 papers are regression cases, used to develop the new selector.
- The new 100 papers exclude previously reviewed works and versions. They contain
  50 previous `ok` and 50 previous `no_abstract` results: a diagnostic sample, not
  an estimate of corpus-wide prevalence.
- The assistant reviewed all 100 page images and selected native source spans
  before opening their predictions. The references contain 56 complete abstracts,
  five partial abstracts, and 39 pages without an abstract.
- Selector development started before source review; regression tuning followed
  source review. This is **not an independent blind evaluation**. Independent
  human validation remains outstanding, as agreed for this work.
- Source references, 30 new queries, model revisions, and scoring settings have
  freeze receipts. The 100 previous retrieval queries are reported separately.
- Correct extraction requires a complete source reference and at least 98%
  ordered canonical character precision **and** recall. Case, punctuation, and
  whitespace are normalized; this does not certify mathematical notation fidelity.
- All parsers see only the first physical page. Missing abstracts, partial
  abstracts, highlights, key points, author notes, and cover pages are distinct.
- A proposal is not an authorized graph claim or a Jev request. The existing
  source-review admission gate still applies.

## Extraction changes and results

`trace_gc/pdf_structure.py` traverses Docling's document body tree instead of
globally sorting text by vertical position. It handles duplicate Abstract headings,
metadata embedded in paragraphs, structured abstracts, and footnotes between
columns. GROBID's abstract field can identify unlabeled prose or corroborate a
geometry-based selection when the reading-order tree is wrong. Model text must
agree with native source text before it becomes an eligible proposal; missing
source verification is held.

Regression tuning explicitly compared a more permissive variant. It recovered
more text but admitted a page without an abstract, so the stricter variant was
frozen before scoring new predictions.

| Selector | Old 200: correct / proposed | New 100: correct / proposed | New complete abstracts recovered as correct proposals |
|---|---:|---:|---:|
| Production v5 baseline | 98 / 120 | 40 / 50 | 40 / 56 |
| Frozen geometry v1 | 122 / 136 | 41 / 47 | 41 / 56 |
| GROBID nonempty-field baseline | 109 / 131 | 45 / 58 | 45 / 56 |
| Structure v2 | **127 / 127** | **45 / 46** | **45 / 56** |

On the new sample, v2 proposal precision is 97.8%, and correct proposal recall is
80.4%. The 95% Wilson interval for proposal precision is approximately 88.7–99.6%,
so this sample does not establish production-level reliability. It proposes none
of the five partial abstracts or 39 absent abstracts.
It recovers near-complete text from 51 of the 56 complete abstracts, but holds six
of those otherwise accurate texts because of boundary or transcription uncertainty.
These figures describe agreement with the frozen native-text reference. The
visual checks below demonstrate mathematical errors that this metric misses.
Requiring the first and last 48 canonical characters to match, alongside the
98% text threshold, gives 45 correct v2 proposals versus 36 for production on the
fresh sample. This stricter boundary check still ignores mathematical layout.

The remaining incorrect proposal, `f030`, includes body text after an inline
`1. Overview.` heading that Docling labels as ordinary text. Native agreement
confirms that the words exist on the page; it cannot prove that they belong to the
abstract. Other remaining holds include mixed affiliation/abstract blocks,
formula fragments, URLs, and footnote markers at the final sentence. These fresh
errors are recorded without retroactively tuning the frozen selector to them.

Among the 50 previously skipped pages, source review finds eight complete
abstracts, three partial abstracts, and 39 pages with no abstract. V2 correctly
proposes six of those eight complete abstracts. This small diagnostic subset
must not be extrapolated to all skipped papers.

The separate source-review gate is exercised on all 100 pages. The initial pass
prepared 56 source-bound requests. A subsequent visual transcription audit holds
`f026` and `f033`, leaving **54 prepared requests**, five partial-page holds,
39 absent-page holds, and two mathematical-transcription holds. The two earlier
drafts are retained under `superseded_requests`; their active paths now contain
denial receipts. Candidate-only admission is zero. Requests are **not sent**;
a future executor must recheck the checkpoint, source hashes and visual audit,
and reserve against the existing $50 corpus ledger. Source binding alone does
not certify scientific fidelity.

### Local vision fallback pilot

MinerU2.5 and olmOCR 2 are tested on the same 40 pages: 20 known difficult
regression cases and 20 seeded random fresh pages. This subset contains 21
complete abstracts and 19 absent abstracts, including only six fresh complete
abstracts and **no partial abstracts**. It is too small to establish fallback
safety at page breaks.

Both parser outputs pass through the same frozen v2 selection and native-source
checks. MinerU supplies layout boxes. olmOCR outputs Markdown; its adapter estimates
boxes by matching paragraph lines to native PDF lines and holds unanchored evidence.
The score measures these parser-plus-adapter pipelines, not general OCR quality.

| Pipeline | Old difficult 20: correct / proposed | Fresh 20: correct / proposed |
|---|---:|---:|
| Structure v2 with Docling | 11 / 11 | 4 / 4 |
| MinerU2.5 plus v2 selector | 10 / 11 | 4 / 5 |
| olmOCR 2 plus v2 selector | 8 / 8 | 2 / 2 |

Using MinerU whenever v2 holds would add one correct proposal (`h079`) and two
wrong proposals (`h055`, `f041`). The `f041` proposal consists of affiliations on
an author-only first page. olmOCR adds no correct proposals beyond v2 in this
pilot. These results do not support automatic fallback promotion.

All 40 MinerU conversions complete. olmOCR completes 39; `f095` reaches the
configured 4,096 generated-token cap and is held. Total recorded inference
times are 35.5 minutes for MinerU and 39.8 minutes for olmOCR, excluding model
setup. Medians are 44.3 and 46.2 seconds per page on the shared RTX 3060.

MinerU uses pinned 1.2B weights, BF16, its two-step layout/crop extraction, and
200-dpi page rendering. olmOCR uses pinned 7B weights with NF4 double quantization,
BF16 compute, a 1288-pixel longest image edge, and deterministic direct Transformers
decoding. Its configuration differs from the upstream BF16/FP8 pipeline and omits
rotation/retry stages; results must not be represented as that upstream benchmark.

### Visual transcription audit

Six deliberately selected pages were checked against their rendered source;
the source and prediction hashes are retained in
[`visual_audit.json`](../review/first_page_validation_v2/visual_audit.json).
This is a qualitative diagnostic, not a population accuracy estimate.

- `f030`: the inline Overview heading visibly ends the abstract, but the v2
  selector includes the following body text.
- `f041`: native agreement verifies affiliation text that the MinerU adapter
  incorrectly proposes as an abstract.
- `f026`: native text flattens fractions and exponents; v2 also moves a radical
  from the complexity bound into an earlier expression. The character metric
  counts this proposal as correct.
- `f033`: native text loses the structure of floor functions and fractions;
  v2 holds its scattered output as partial.
- `h171`: native text interleaves form-factor fragments. olmOCR changes a
  source uncertainty from 0.009 to 0.0009 and changes some subscripts. MinerU
  preserves the checked expressions but is held because its LaTeX differs
  from the native representation.
- `h172`: the raw vision outputs preserve `R(r)=sqrt(r^2+A^2)`. Native-text
  substitution in v2 and the MinerU adapter detaches the radical and flattens
  exponents while still passing the character metric.

The fresh `f026` and `f033` requests are held; the audit also records `h171`
and `h172` as execution holds for the earlier retry plan. Frozen reference
labels and benchmark scores remain intact for reproducibility. No graph claims
or Jev calls are made from these experiments. Formula-aware source alignment
remains necessary before such transcriptions can be treated as scientific
evidence; the native text layer cannot serve as mathematical ground truth.

## Retrieval

All methods search the same frozen 10,000 distinct works. Fields come from automatic
first-page extraction for every document; reviewed abstract references are never
inserted into the index. There are 663 missing automatic abstract fields, 13 missing
titles, and two pages without native text. Gemini's existing page embeddings are
reused unchanged.

BM25F uses title/abstract/page weights 2/1/0.25, per-field length normalization,
`b=0.75`, and `k1=1.2`, frozen before rankings. The full-page BM25 control tests
whether field weighting itself helps. SPECTER2 uses its paper adapter for
title-plus-abstract documents and its ad-hoc-query adapter for queries. Its
512-token limit truncates 393 document inputs and no query inputs.

The MiniLM cross-encoder reranks the union of each method's top 50 candidates
(BM25F, SPECTER2, Gemini). Targets are never inserted into candidate lists. This
evaluates a complete retrieval-and-reranking pipeline.

| Method | Old 100: target at rank 1 | New 30: target at rank 1 | New 30: target within top 10 |
|---|---:|---:|---:|
| Full-page BM25 | 86% | 90% | 96.7% |
| Field-weighted BM25F | 85% | 86.7% | 93.3% |
| SPECTER2 | 76% | 90% | 96.7% |
| Gemini Embedding 2 | 90% | 90% | **100%** |
| Pooled MiniLM reranker | **93%** | **93.3%** | 96.7% |

Gemini finds every new target within its top three. Reranking improves two new
queries from rank two to rank one, but demotes the image-only book cover `f076`
from rank one to rank 72 because its text representation is empty. On the old
queries it also demotes `p04` from rank one to rank 25. A text reranker should
therefore remain optional while visual results remain accessible.

These are known-item queries with one labeled target. They do not measure all
relevant papers, answer correctness, or graph-synthesis accuracy. The one-query
net advantage on the new sample is insufficient to establish general superiority.

## Cost and execution

The 30 new Gemini query calls add **$0.0001394 estimated API usage**, with $0.003
of conservative reservations. All 30 succeed. There are no new image embedding
calls or Jev calls. Local compute, electricity, downloads, and hardware costs
are not included. The existing $12 embedding trial reservation cap remains enforced.

The new 100 Docling conversions take 199.1 seconds total; their GROBID header
passes take another 142.1 seconds. SPECTER2 embeds 10,000 documents in 312.8 seconds
and 130 queries in 0.7 seconds. These are observed times on a shared workstation,
not controlled throughput comparisons. Reranking starts on CPU and resumes on
CUDA after SPECTER completes; completed CPU caches are retained and recorded.

The local suite completes **334 tests: 333 pass, one external integration test is
skipped**. Six new tests exercise cross-column reading order, interleaved footnotes,
embedded metadata, partial-page holds, failed conversions, missing native evidence,
cyclic provenance, receipt binding, and funding-note rejection.

The final replay rescores all six methods from retained outputs and verifies
100 original source PDFs, first-page renders, and native reference block sets;
all 80 fallback input receipts; 130 query inputs; and frozen extraction/retrieval
protocols. Known transcription holds are enforced in the request plan. The
replay makes no additional model or API calls. Its receipt is retained as
`validation_v2/verification.json` and included in the aggregate results.

## Reproduction

The experiment uses isolated Python 3.12 environments outside the repository.
Docling conversions use the previous CPU environment; vision and retrieval models
use the new CUDA environment. Exact installed versions and six model revisions
are stored alongside results. Production-baseline extraction uses Python 3.14.
The optional model packages are listed in
[`src/abstract_validation_v2/requirements.txt`](../src/abstract_validation_v2/requirements.txt).
The tested GPU environment uses `torch==2.8.0+cu128` and
`torchvision==0.23.0+cu128` from PyTorch's CUDA 12.8 index; these are not added to
the TRACE-GC runtime dependencies.

```text
python -m src.abstract_validation_v2.prepare
python -m src.abstract_validation_v2.convert docling --cohort fresh
python -m src.abstract_validation_v2.convert grobid --cohort regression
python -m src.abstract_validation_v2.convert grobid --cohort fresh
python -m src.abstract_validation_v2.references
python -m src.abstract_validation_v2.extraction baseline
python -m src.abstract_validation_v2.extraction regression
python -m src.abstract_validation_v2.extraction freeze
python -m src.abstract_validation_v2.extraction fresh
python -m src.abstract_validation_v2.download_models
python -m src.abstract_validation_v2.fields
python -m src.abstract_validation_v2.retrieval specter
python -m src.abstract_validation_v2.retrieval gemini
python -m src.abstract_validation_v2.retrieval rank
python -m src.abstract_validation_v2.vision mineru
python -m src.abstract_validation_v2.vision olmocr
python -m src.abstract_validation_v2.extraction regression --methods mineru olmocr
python -m src.abstract_validation_v2.extraction fresh --methods mineru olmocr
python -m src.abstract_validation_v2.audit
python -m src.abstract_validation_v2.verify
python -m unittest discover -s tests -v > ../TRACE-GC_RealPaper_Test/validation_v2/unit_tests.log 2>&1
python -m src.abstract_validation_v2.report
```

The GROBID commands require the local experimental service on port 18070.
Replay requires the retained source catalog, frozen manifests, and source PDFs.
Selecting another sample requires a new reference review; existing manual labels
are bound to source hashes and must not be reused for different pages. The
olmOCR adapter also requires the retained official prompt source in
`validation_v2/environment/olmocr_prompts.py`.
`references` verifies the assistant-written source selections; it does not infer
ground truth. The retained visual audit contains assistant-authored observations;
`verify` checks their source bindings, without independently judging those observations.
Cached conversions and API receipts resume without rebilling
successful inputs. Protocol hashes reject changed inputs or scoring code.

## Primary implementation references

- [SPECTER2 models and task adapters](https://github.com/allenai/SPECTER2)
- [MinerU2.5 model](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B)
- [olmOCR 2 model](https://huggingface.co/allenai/olmOCR-2-7B-1025)
- [Sentence Transformers retrieval and reranking](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)
