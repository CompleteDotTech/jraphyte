# First-page section ownership: issue #16

This experimental selector remains a source-review proposal generator. It does
not admit evidence or publish a graph. The 200 previously examined papers are a
development regression corpus, not an independent qualification set.

## Cause and implementation

The former collector used the width of the opening region, including a narrow
centered `Abstract` heading, as the section's horizontal extent. This could
exclude a left-aligned Introduction heading while retaining the wider body
paragraph beneath it. A global vertical sort also placed a staggered right-hand
body paragraph before its left-hand closing heading. Source alignment then
either rejected a previously correct abstract or accepted a contaminated one.

`trace_gc/pdf_structure_parallel_v4.py` now records
`section_ownership_version: source-section-ownership-v1` and:

1. Derives the content lane from the first substantive region beneath a separate
   abstract heading. A short heading no longer determines the content width.
2. Examines plausible closing headings and metadata before consuming the next
   region. Heading text must locate in native evidence; converter labels alone
   cannot certify closure. The surrounding native text must support a heading:
   an interior word match cannot truncate a continuation, and a converter cannot
   erase `Graphical` from an abstract's source prefix. Unrecognized model section
   headings need corroborating native heading typography. The boundary retains
   boxes, tree order and source spans. Staggered columns and regions with
   conflicting tree/geometry order cannot silently append body text across a
   witnessed boundary. A located metadata label can establish the boundary even
   when the converter corrupts the following values; its native separator and
   surrounding context must also agree.
3. Preserves the already located abstract and holds unresolved transitions:
   multiple narrower lanes, overlapping model regions, a large layout gap, or a
   smaller separate source style. These signals stop collection but do not prove
   completeness. Region ownership decisions remain in the sealed assessment.
4. Removes a terminal footnote marker only when native span styling marks it as
   superscript, it follows sentence punctuation, and a unique later footnote
   region starts with the same marker and is located in source text. The excluded
   marker and footnote retain exact source spans. A footnote alone never supplies
   a complete-abstract closing boundary. An unlinked superscript stays in the
   candidate text and requires review. A cropped model marker `1` cannot match
   a native footnote numbered `21`.

Original native line IDs, offsets, hashes and source text are preserved. The
selector does not insert model text into native spans. Layout transitions do
not resolve structured-abstract scope or missing title-page closure: those remain
[#17](https://github.com/CompleteDotTech/jraphyte/issues/17). The geometry work in
[#15](https://github.com/CompleteDotTech/jraphyte/issues/15) can remove separate
alignment holds but must be evaluated together with this change.

## Causal fixtures

`tests/test_parallel_source_boundaries_v4.py` contains authored fixtures for the
narrow centered heading, staggered columns, full-width abstracts, missing body
headings, inconsistent tree/geometry order, source typography, repeated text,
unlocated headings and linked/unlinked footnote markers. It also preserves
first-page continuation holds and heading words inside running sentences.

```sh
python -m unittest discover -s tests -p 'test_parallel_source*v4.py' -q
python tools/run_validation.py
python tools/validate_package.py
```

These offline fixtures do not replace the authorized private paper replay.

## Paired empirical protocol

The private diagnostic uses the saved native representations from the previously
reported run with results SHA-256
`661964b8db10bf2bd806a95a0119f4492dcabf72e759fff521993f702f016b0d`.
Both selectors run in one Python process against the same immutable JSON
snapshots. The before-selector is loaded from Git commit
`d5ca636a48e963619f4c89e2958d0bb1a3e72f80`; the after-selector is this implementation.
All 200 source PDFs, cached first pages and review images are hash-checked against
their page receipts, and archived source identities must agree. Cached conversion
errors, partial pages and absent pages stay in all four method denominators.

The replay writes immutable before/after assessments, per-case differences,
source-span readback results, legacy and boundary-aware metrics, actual runtime
versions, input hashes, and source-code hashes outside the repository. All inputs
and implementation hashes are checked again before the completion receipt is
written. Its runner and private result are hash-bound by the public receipt.
It makes no provider calls and no production graph writes.

Authorized investigators can run the diagnostic script stored beneath the data
root; it contains no paper text. `--output` must name a new directory:

```sh
python "${TRACE_GC_TEST_DATA_ROOT}/validation_v3_private/issue16-boundaries-20260928/src/replay.py" \
  --repo . --data-root "${TRACE_GC_TEST_DATA_ROOT}" \
  --output validation_v3_private/issue16-boundaries-20260928/full200-new
```

This is a saved-evidence selector comparison. It does not claim a fresh converter
run, exact historical dependency reconstruction, independent source review,
notation certification, or a passed integrated preservation gate. Integrated
qualification must use the runtime/preflight work in
[#13](https://github.com/CompleteDotTech/jraphyte/issues/13), the stronger fidelity
review in [#14](https://github.com/CompleteDotTech/jraphyte/issues/14), and the
geometry changes in #15. The public receipt reports the measured remaining
holds and every changed case/state without private paper content.

## Measured development result

The [public receipt](../review/first_page_section_ownership/receipt.json) binds the
final private result, diagnostic runner, 2,805 checked inputs, method code and
validation report. All 800 before-assessments exactly reproduce their archived
JSON, including seals. The final input/code recheck passed. All four methods keep
200 papers in their denominators; 111 frozen references contain complete
first-page abstracts.

| Method | Proposals before / after | Boundary-and-text98 correct before / after | False proposals before / after |
| --- | ---: | ---: | ---: |
| Primary structure | 38 / 55 | 38 / 55 | 0 / 0 |
| GROBID | 33 / 50 | 33 / 50 | 0 / 0 |
| MinerU | 39 / 54 | 38 / 54 | 1 / 0 |
| olmOCR | 39 / 48 | 39 / 48 | 0 / 0 |

These are comparisons against the existing frozen references, not independent
semantic or notation certification. The receipt records all 348 changed
case/method rows, including unchanged text with stronger boundary evidence.
GROBID's one conversion error and olmOCR's three truncated outputs remain in the
results. After the change, the four methods still withhold 56, 61, 57 and 63
complete references, respectively. No assessment admits graph evidence.

The targeted primary-structure outcomes are:

| Cases | Result and remaining limitation |
| --- | --- |
| f039 | Complete, exact-boundary proposal; Introduction has source evidence. GROBID and MinerU agree. olmOCR preserves matching text but holds an unverified start/unlocated paragraph. |
| f032, f098 | Exact abstract text retained with 6 and 10 emitted source spans; section closure remains unresolved and held. |
| f059, f142 | Exact abstract text retained; native geometry still reports an unverified column transition. No final abstract spans are emitted; 3 and 11 located region spans are retained and checked. |
| f145, f146 | Complete, exact-boundary proposals, with located metadata/body closure. |
| f150 | Keywords/body excluded; 19 source spans retained, but closure remains unresolved and held. |
| f195 | Complete, exact-boundary proposal; the excluded superscript marker links to source footnote evidence. |

There is one newly withheld paper: f178 in primary, MinerU and olmOCR. Its
abstract text still matches, but the short start-label query has three native
substring matches within the model's broad start region. The source locator
cannot establish a unique start, so the new guard retains an explicit
`unverified_abstract_start_heading` hold. The receipt includes this regression;
any later disambiguation must verify heading context without relaxing repeated
source-text or cropped-heading protections.

Final offline validation ran 554 tests: 548 passed, six skipped, zero failures or
errors. The skips cover optional NumPy, Windows symlink privileges and an
unsupplied external legacy implementation. The focused V4 suite ran 135 tests
with one skip; package validation passed. These runs used no provider calls or
production graph writes. Independent agent review covered the implementation and
authored adversarial fixtures, including source-cropped headings and footnotes;
it is not independent human review of the private papers.

The historical 91-case preservation gate is not passed or reclassified here.
Integrated evaluation with #13/#14/#15 and remaining semantic work in #17 is
still required. The implementation fixes contamination while preserving holds
where located closing-boundary evidence is unavailable.

## Design references

Docling documents reading order through the body tree and child order, together
with layout and provenance fields. This motivates retaining tree order alongside
source geometry rather than assuming either is always correct.
[Docling document model](https://docling-project.github.io/docling/concepts/docling_document/).

PyMuPDF documents span font flags, including bit 0 for superscript and bit 4 for
bold text, and explains that extracted PDF text may have unexpected reading order.
These are evidence fields used by the selector; their presence does not establish
abstract scope or transcription fidelity.
[PyMuPDF text extraction and font characteristics](https://pymupdf.readthedocs.io/en/latest/recipes-text.html).
