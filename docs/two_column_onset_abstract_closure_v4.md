# Source two-column onset after an inset summary

An unlabelled, inset title-page summary can end immediately before the paper
switches to two body columns. The converter sees multiple later lanes, but
their boxes alone cannot establish which text belongs to the abstract.

With verified original-PDF geometry enabled, the selector now uses a narrow
source proof: the complete inset paragraph must match the frozen scholarly
abstract field and span the future column gutter. Two long native body lines
must begin on the same lower baseline in separate lanes, each followed by a
continuing line. A horizontal source line between the summary and body onset
keeps the hold, as do a missing or offset lane, a field mismatch, or
unverified source geometry. The body text is never appended to the selected
summary.

In the exposed 200-paper, four-method replay, only f059 changed. Primary
correct review-only proposals rose from 89 to 90 and GROBID from 79 to 80;
MinerU stayed at 72 and olmOCR at 66. Primary selected text and spans were
unchanged. GROBID replaced its previously unlocated field text with three
source-located native spans. The other 798 assessment files were byte-
identical. All 200 original-source, page, image, and native-line digests
matched the prior replay. Measured false proposals remained zero across all
methods, and saved v2 replay passed. The [redacted receipt](../review/two_column_onset_abstract_closure_v1/receipt.json)
binds the private source review and full result by SHA-256.

Reproduce with the authorized external data root and pinned Windows Python
3.12 replay environment:

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root "$TRACE_GC_TEST_DATA_ROOT" \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --source-geometry-policy source_fraction_v1 \
  --output validation_v3_private/<fresh-output-name>
```

The command still exits with a failed historical preservation gate: five of
the 91 formerly correct cases remain held. This development replay does not
qualify unseen-paper fidelity or automatic graph admission. Source geometry
remains disabled by default.
