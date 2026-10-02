# Unlabelled keywords below a two-column abstract

A bold abstract can occupy the upper left column while ordinary body prose is
already flowing in the right column. A smaller, unlabelled keyword list can
then follow the abstract in the left lane. Typography alone cannot establish
whether that list is abstract continuation, metadata, or body text.

With verified original-PDF geometry enabled, the selector requires a long,
source-located bold left-lane narrative ending in a sentence, a compact
nonbold list with several pipe-delimited terms immediately below it, at least
five contemporaneous long right-lane body lines, and at least three regular
left-lane body lines after the list. It rejects any unowned horizontal text
between the selected abstract and later left body. A conflicting scholarly
abstract field also retains HOLD. The keyword list and both body lanes are
excluded from the selected text. Missing or ambiguous evidence remains held.
The first five substantial right-lane lines must have regular body typography;
all later lines must remain mostly regular at a size distinct from the smaller
keywords. This allows an inline body lead-in while a bold right-lane paragraph
still retains HOLD as possible abstract continuation.

The [redacted receipt](../review/two_column_keywords_abstract_closure_v1/receipt.json)
binds a fresh 200-paper, four-method run to the measured source files and
private artifacts. All 800 assessment file hashes read back; only f150
assessment files changed. Primary correct legacy text98 proposals rose from
92 to 93 and MinerU from 73 to 74, with zero false proposals in every arm.
GROBID remained absent for f150 because its scholarly field is empty; olmOCR
remained held because its candidate OCR paragraph is unlocated. Original
source and native-line identities are unchanged. Saved v2 replay passed.

To reproduce with the authorized external data root and pinned Windows Python
3.12 evaluator, use a fresh output name:

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root "$TRACE_GC_TEST_DATA_ROOT" \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --native-mode fresh \
  --source-geometry-policy source_fraction_v1 \
  --output validation_v3_private/<fresh-output-name>
```

The command still exits with a failed historical preservation gate: f079,
f081, f122 and f153 remain held. This exposed development replay does not
qualify scientific notation, visual completeness, unseen-paper precision,
automatic promotion or graph admission. Source geometry remains disabled by
default, and every proposal remains review-only.
