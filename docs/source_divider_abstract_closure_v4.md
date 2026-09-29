# Visible source divider for a cross-lane abstract boundary

An explicit abstract can end immediately above a numbered Introduction. When the
Introduction starts in one column while its body continues in another, the V4
selector previously held the candidate: a heading and a font-size change alone
cannot prove that the abstract has ended in both lanes.

With verified original-PDF geometry enabled, the selector now accepts one
source-painted horizontal rule as closing evidence. The rule must be visible,
fully opaque, and span the source-located abstract, heading, and first body
text. It must fall below every selected abstract span and above both body
regions. The heading must be a source-located numbered Introduction. Missing,
short, misplaced, or obscured rules leave the conservative hold in place. The
body witness below the rule is explicitly excluded from abstract ownership.

On the exposed 200-paper, four-method replay, only f171 changed. The primary,
GROBID, and MinerU methods each changed from an uncertain hold to a correct
review-only proposal; olmOCR did not change. The primary and MinerU selected
text and spans were unchanged. GROBID replaced its previously unlocated field
text with the source-located native text; its candidate remained a correct
match under the frozen metric. All 200 source, page, image, and native-line
digests matched the prior replay. No other assessment changed. Correct
proposals were primary 87 to 88, GROBID 77 to 78, MinerU 70 to 71, and
olmOCR 65 to 65. Measured false proposals remained zero across all four
methods, and saved v2 replay passed. The [redacted receipt](../review/source_divider_abstract_closure_v1/receipt.json)
binds the private result and source-image review by SHA-256.

Reproduce with the authorized external data root and pinned Windows Python
3.12 replay environment:

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root "$TRACE_GC_TEST_DATA_ROOT" \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --source-geometry-policy source_fraction_v1 \
  --output validation_v3_private/<fresh-output-name>
```

The command still exits with the historical preservation-gate failure: seven
of the 91 formerly correct cases remain held. This exposed development replay
does not qualify unseen-paper fidelity or automatic graph admission. Source
geometry remains disabled by default.
