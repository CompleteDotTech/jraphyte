# Embedded metadata and abstract completeness

The experimental selector records the boundary version
`source-embedded-nonabstract-role-hold-v1` when a known nonabstract role appears
inside located abstract text. This follows the source ownership rules in
[the abstract structure guide](34_first_page_abstract_structure.md).

## Cause and bounded change

Affiliations, funding acknowledgements and captions were recognized when they
began a separate converter region. The same native text could become a complete
proposal if a converter combined it with the preceding abstract. The embedded
boundary scan recognized explicit metadata labels such as `Keywords:` and
`Funding:`, but missed the broader role prefixes used for separate regions.

The scan now detects those role prefixes after a source newline or sentence
boundary, including `Affiliations:`, `Corresponding author:`, lowercase prefixes
and numeric or symbol affiliation markers. Newly recognized explicit role labels
also stay held when placed in a separate converter region. It retains the whole
located candidate and reports
`embedded_nonabstract_role_requires_source_review`. It records the original
suffix spans, clears complete ownership and does not propose the candidate.
Ambiguous prose such as a sentence beginning “University education…” is held
without certifying a shorter prefix. Ordinary uses of role words within a
sentence remain part of the abstract.

Role recognition uses the label's structure. A caption needs a numbered label
and separator; a standalone `Highlights` or explicit `highlight:` label differs
from wrapped prose such as “highlight the result” or “Figure 1 shows…”. A
marker-prefixed institution requires a capitalized role name or an explicit
label delimiter, so the ordinary phrase “a university can…” remains prose.
Hyphenated institutional adjectives and URLs continuing an unfinished sentence
also remain part of the source text. Sentence tails use the existing punctuation,
quotation, closing-parenthesis and footnote-marker grammar.

Existing explicit metadata cuts keep their behavior. This change does not
attempt to recognize every possible affiliation or caption, infer ownership
from typography, alter source offsets, repair notation, or resolve title-page
closure. All proposals remain subject to the separate fidelity and promotion
gates; graph admission flags remain false.

## Acceptance evidence and remaining scope

The source audit of the previous measured tree `7cbc22f` checks these issue #17
examples against their original pages and sealed reviewed results:

| Requirement | Evidence on the previous measured tree |
| --- | --- |
| Structured abstracts (`f113`, `f186`) | All reviewed subsection labels remain in order and close before source metadata or outer Introduction. `f113` uses a separately reviewed image transcription to repair notation. |
| Multiple paragraphs (`f017`, `f119`) | Both paragraphs retained. `f119` uses attributed closure review excluding the separate synopsis. |
| Unlabelled abstract (`f080`) | Source event/date/footer closure; no English narrative-verb requirement. |
| Title pages (`f007`, `f085`, `f131`) | Default native assessments remain held. Attributed review binds actual physical page-two Introduction/Contents; `f131` also needs image transcription for notation. |
| Classification (`f084`) | Mathematics Subject Classification is outside the selected source spans. |
| Partial first-page scope | All seven frozen partial cases remain nonproposed in all four arms. Their primary diagnostic states are one partial, five uncertain and one absent; they are not uniformly classified as partial. |

The private audit is identified by SHA-256
`b89ce4e19671de8d6811d4006a8a3f95f440368ce67073bcfcb84dd30587c416`.
It binds nine named cases and 51 input hashes, with internally attributed review
of previously examined development sources. It is not independent human or
unseen-paper qualification. The [previous promotion result](selector_promotion_200_result.md)
remains valid only for its recorded code and reviewed inputs.

Authored tests cover merged converter regions, same native lines, separate
regions, invented converter text, ambiguous role-led prose, ordinary running
prose, structured subsection retention and French/German paragraphs. Existing
tests retain later-body, competing abstract, title-page, partial-page,
footnote, source-order and source-heading negatives.

Development replays exposed four recall regressions in an earlier draft:
wrapped “highlight” prose, a URL continuing an availability sentence, and a
hyphenated institutional adjective were mistaken for role boundaries. That
800-assessment result is preserved as a failed development attempt. The bounded
structure checks above address those causes. A subsequent four-case/four-arm
probe restored all 16 prior assessment seals; later authored checks additionally
guard wrapped articles before institution names and a singular “highlight” on
its own source line. These checks are separate from the final full-corpus replay.

## Final cached-native comparison

The [redacted receipt](../review/abstract_embedded_metadata_20260928/receipt.json)
records 200 original papers and all 800 assessments on base `f9f7c13` with the
final selector hash `57f64027`. This measurement predates PR #51: its opt-in
fraction helper was absent and no `SourceGeometry` context was supplied. The
patch was subsequently reconciled onto main `eb2772c`; the old corpus receipt
is not relabeled as a measurement of that combined tree.

| Arm | Legacy boundary + text98 correct proposals | Legacy false proposals | Complete first-page abstracts withheld |
| --- | ---: | ---: | ---: |
| Native structure | 79 | 0 | 32 / 111 |
| GROBID | 73 | 0 | 38 / 111 |
| MinerU | 67 | 0 | 44 / 111 |
| olmOCR | 64 | 0 | 47 / 111 |

Every metric in this table is unchanged from the prior measured tree. Source
and native identities match, and saved v2 replay passes. The only assessment
changes are boundary/ownership explanations for already-uncertain olmOCR cases
`f050` and `f123`; their text, spans, proposal flags and reasons are unchanged.
The comparison checks 1,604 input hashes and all 800 before/after assessment
seals. Diagnostic notation mismatch counts also remain unchanged; legacy
boundary/text agreement does not establish scientific notation fidelity.

The automatic preservation gate still **fails**, with the same 16 losses from
the original 91. No source reviews were reapplied and no new promotion claim
is made. The earlier six authored merged/same-line false proposals now remain
held, while three separate-region metadata exclusions retain their behavior.

## Reproduction and integration

```sh
python -m unittest discover -s tests -p 'test_parallel_source_embedded_metadata_v4.py' -q
python -m unittest discover -s tests -p 'test_parallel_source*v4.py' -q
python tools/run_validation.py
python tools/validate_package.py
```

A new source-pinned 200-paper/four-arm run and current-code review verification
are required before transferring the previous promotion claim to this selector.
Cached-native comparison alone is a development regression measurement. Keep
private papers, text, labels and source maps outside the repository.
