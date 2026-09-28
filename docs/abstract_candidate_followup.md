# Source-owned abstract candidates and ordering

This follow-up to [issue #17](https://github.com/CompleteDotTech/jraphyte/issues/17)
uses selector structure version `source-abstract-sections-v2`. The original
[v1 measurement](34_first_page_abstract_structure.md) and its receipt remain
historical evidence.

## Causes and changes

- A converter can emit a body paragraph whose union box begins beside the
  Abstract heading. Sorting that box before the abstract selected unrelated
  body text in `f097` and `f188`. A region overlapping a separate Abstract
  heading now needs uniquely located native extents following that heading.
  Recovered extents must remain in the selected content lane. Exact later
  offsets on the same native line are ordered after the heading, independently
  of converter tree order. Oversized boxes with valid following source content
  remain usable; model geometry alone cannot establish ownership.
  A sole unlocated candidate excluded by this check remains available as an
  uncertain inspection artifact (`f023`), with no invented source spans.
- An empty scholarly field left unlabelled, ordinary-font frontmatter without
  a candidate in `f045`, `f096` and `f158`. A source-located title, author list
  and adjacent affiliation can now identify a candidate paragraph. This route
  retains text and provenance for review and never issues an automatic complete
  proposal. It does not infer abstract ownership from page position or font.
- A narrow abstract above a wider body can acquire body prose from the other
  column (`f171`). A located numbered heading plus a source font transition
  now retains the preceding prefix as an explicit section-ownership hold.
  An authored counterexample demonstrates that this evidence alone cannot
  certify closure: the neighboring column may start its body while the
  abstract continues. Ordinary math/text font changes without such a located
  heading do not truncate the candidate.
- The global alphanumeric locator can pass while omitting a short native line
  (`f106`). Its ordered non-whitespace source positions must now exactly match
  the positions in the selected paragraphs. When the global projection differs,
  the existing strict paragraph composer can retain the original characters;
  otherwise the candidate stays held. A source permutation, duplicate position,
  omitted punctuation or short phrase cannot pass on set membership alone.
  Ambiguous global matches and per-paragraph failures are never overridden.

`region_ownership` records native spans and heading evidence. Frontmatter
`candidate_scope` binds its title, authors, affiliation and candidate spans.
A cross-column hold records the located `candidate_boundary`, which is a
witness for further review, not an accepted closing boundary.

The first follow-up full run exposed `f106`: the historical metric called its
proposal correct despite a missing 20-character alphanumeric phrase. That run
is retained as diagnostic evidence. Historical text98 agreement must therefore
be reported separately from exact transcription and attributed source review.

Native IDs, offsets, source boxes, historical scoring and alignment thresholds
are preserved. This change does not reconstruct missing symbols, infer exponent
semantics, approve manual closure or enable graph admission. Notation mismatch
and unresolved geometry require separate source evidence and correction;
closure-only review cannot approve incomplete or wrong text.

## Measured result and remaining gates

The [versioned receipt](../review/first_page_abstract_structure_v2/evaluation_receipt.json)
binds a fresh extraction of all 200 authorized originals and all four methods
(800 assessments, 846.573 seconds). It records the measured base
`36768a342972552dedb6579951163ef2c550e9a9`, runtime and source hashes; later
integration changes require their own evidence. Source preflight and saved
historical replay passed. All 200 native JSON files were byte-identical to the
previous v1 run.

These counts use the historical boundary plus alphanumeric98 metric:

| Method | Previous v1 correct proposals | This version | Historical false proposals | Lost v1 correct proposals |
| --- | ---: | ---: | ---: | ---: |
| Primary structure | 74 | 77 | 0 | 0 |
| GROBID adapter | 68 | 71 | 0 | 0 |
| MinerU adapter | 68 | 68 | 0 | 0 |
| olmOCR adapter | 64 | 65 | 0 | 0 |

The primary and GROBID gains are `f097`, `f106` and `f188`. The additional olmOCR
gain, `f022`, uses exact owned paragraph composition to exclude a separate
vertical margin line. `f106` now retains the complete native wrap line and has
historical precision and recall of 1. `f023` retains its uncertain candidate;
`f195` remains a complete matching proposal.

**The original 91-case preservation gate still fails:** 18 original successes
remain held, down from 20 in v1. The automatic reasons are grouped below; they
do not establish that the underlying transcription is scientifically correct.

| Hold | IDs |
| --- | --- |
| No source-proven closing boundary | `f007`, `f085`, `f131` |
| Section ownership needs source review | `f012`, `f032`, `f098`, `f171` |
| Unlabelled frontmatter ownership needs source review | `f045`, `f096`, `f158` |
| Unresolved source geometry or symbol order | `f026`, `f059`, `f079`, `f081`, `f111`, `f122`, `f142`, `f153` |

The separate protected cases `f119` and `f150` also remain held for section
ownership. `f030` and `f192` retain historical complete matches; `f199` remains
correctly absent. In particular, source review found a notation defect in
`f192` despite its match to the frozen text reference. That defect is unresolved
by this change.

All four methods have zero source-reviewed verified proposals in this bare
regression: the reviewed boundary, notation and reading-order dimensions remain
unresolved. Separate source review has already identified scientific text
faults, so zero historical false proposals must not be reported as zero fidelity
errors. There are no graph admissions, production graph writes or new paid API
calls. Issue #17 remains open, and this development cohort does not qualify an
unseen cohort or the final promotion policy.

Verification also includes 15 authored tests, a 33-case/four-method cached-native
diagnostic, and repository validation with 708 tests: 701 passed, seven skipped,
zero failures or errors. Package validation passed. The cached-native diagnostic
is diagnostic evidence only. Its result and the repository report are separately
hash-bound in the receipt; generated validation artifacts were preserved
externally and the tracked historical artifacts restored.

## Reproduce

Use the pinned interpreter and authorized data described in the
[reproduction guide](31_first_page_parallel_reproduction.md).

```sh
python -m unittest discover -s tests -p 'test_parallel_source_structure_followup_v4.py' -v
python -m unittest discover -s tests -p 'test_parallel_source*v4.py' -q
python -m src.parallel_source_v4.geometry_probe \
  --data-root "${TRACE_GC_TEST_DATA_ROOT}" \
  --run validation_v3_private/issue17-abstract-structure-full200-20260928-01 \
  --output validation_v3_private/abstract-followup-new-diagnostic/results.json \
  --cases f045 f096 f158 f097 f188 f171 f026 f079 f122 f142 f039 f195 f017 f186
python -m src.parallel_source_v4.extraction regression \
  --data-root "${TRACE_GC_TEST_DATA_ROOT}" \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --runtime-lock src/parallel_source_v4/runtime-windows-py312.lock.json \
  --native-mode fresh \
  --output validation_v3_private/abstract-followup-new-full200
```

Output paths must be new. Cached-native diagnostics do not re-extract PDFs or
qualify an unseen cohort. Authored fixtures cannot substitute for the authorized
200 originals. A full preservation failure is reported even when a bounded
change improves individual cases. Source-reviewed notation and boundary gates
remain separate from historical boundary/text98 agreement.
