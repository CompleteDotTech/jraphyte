# Page-two bibliographic Introduction closure

An unlabelled abstract on a title page can be followed by a distant
proceedings footer. The footer is not a body heading, so a large page-one gap
alone cannot close the abstract. Some proceedings repeat the title and author
in a page-two running header immediately above a numbered Introduction.

With verified original-PDF geometry enabled, the source descriptor records
that page-two header pair only when it occupies opposite ends of the same
row and the numbered Introduction begins below it. The selector uses the
opening only when the page-one candidate matches a frozen scholarly abstract
field, the repeated title matches exactly, the repeated author matches the
source author prefix, the candidate is full-width and sentence-complete, and
the distant footer is source-located below a blank content gap. Any
intervening horizontal source prose, mismatched header, missing Introduction,
or unverified source retains the hold. Page-two text is closure evidence; it
is never appended to the first-page selection.

In the exposed 200-paper, four-method replay, only f032 changed. Primary,
GROBID, MinerU, and olmOCR each gained one correct review-only proposal:
88 to 89, 78 to 79, 71 to 72, and 65 to 66 respectively. Primary, MinerU,
and olmOCR selected text and spans were unchanged; GROBID replaced its
previously unlocated field text with six source-located native spans. The
other 796 assessment files were byte-identical. All 200 original-source,
page, image, and native-line digests matched the prior replay. Measured
false proposals remained zero across all methods, and saved v2 replay passed.
The [redacted receipt](../review/page_two_bibliographic_intro_v1/receipt.json)
binds the private two-page source review and full result by SHA-256.

Reproduce using the authorized external data root and pinned Windows Python
3.12 replay environment:

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root "$TRACE_GC_TEST_DATA_ROOT" \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --source-geometry-policy source_fraction_v1 \
  --output validation_v3_private/<fresh-output-name>
```

The command still exits with a failed historical preservation gate: six of
the 91 formerly correct cases remain held. This development replay does not
qualify unseen-paper fidelity or automatic graph admission. Source geometry
remains disabled by default.
