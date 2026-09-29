# Shaded synopsis after a front-matter abstract

An unlabeled bold abstract can be followed by a separate synopsis in a filled
inset. A typography change alone cannot establish the section boundary, so
the selector previously held f119 for source review.

With verified original-PDF geometry enabled, the selector now requires an
opaque light fill behind all source-located synopsis lines, no intervening or
unowned horizontal prose, a unique source-located numbered outer heading,
and a located body paragraph after that heading. The selected abstract must
have a complete terminal sentence and match the converter's scholarly abstract
field under the existing legacy boundary/text metric. The source fill, heading
and body are distinct evidence; field agreement alone never closes the section.
The synopsis is excluded from the selected abstract. Missing, overpainted or
ambiguous geometry retains the hold.

The [redacted receipt](../review/shaded_synopsis_abstract_closure_v1/receipt.json)
binds a fresh 200-paper, four-method run to the measured source files and
private artifacts. All 800 assessment file hashes read back. Only f119 changed
decision among the 200 IDs: each method now proposes a source-located complete
abstract with the frozen legacy boundary/text98 match. Primary correct
proposals rose from 91 to 92; GROBID from 80 to 81, MinerU from 72 to 73,
and olmOCR from 66 to 67. All four methods still have zero false proposals in
this known development set. The original PDF, cached page and native-line
identities are unchanged. The saved v2 replay passed.

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
