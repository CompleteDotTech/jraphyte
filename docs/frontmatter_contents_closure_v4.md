# Source-backed contents closure for first-page abstracts

Some papers put an unlabelled abstract below the title, authors and affiliations, then put correspondence details and a figure on the remainder of page one. The next page may begin with a running title and a table of contents. The V4 selector previously held such a candidate because correspondence is metadata, not an abstract-closing body heading.

With verified original-PDF geometry enabled, the source descriptor now retains a centered running header above a page-two `Contents` heading. The selector uses that witness only when the header matches the located first-page title, the candidate is a full-width source-located paragraph after the affiliations, correspondence is a located boundary after the candidate, and the candidate has a complete terminal sentence. Page-two text supplies closure evidence only; it is never appended to the first-page abstract. Metadata by itself still cannot close a candidate. A mismatched header or missing Contents keeps the hold.

The exposed 200-paper, four-method replay changed only f045: the primary method moved from held to a correct review-only proposal with identical selected native text and spans. Primary correct proposals rose from 86 to 87; GROBID, MinerU and olmOCR remained 77, 70 and 65. Measured false proposals remained zero across all methods, and saved v2 replay passed. The [redacted receipt](../review/frontmatter_contents_closure_v1/receipt.json) binds the private preflight, full result, assessment and source-image review by SHA-256.

Reproduce with the authorized external data root and optional PDF dependencies:

```sh
python -m src.parallel_source_v4.extraction regression \
  --data-root "$TRACE_GC_TEST_DATA_ROOT" \
  --source-map validation_v3_private/parallel-v4-source-map.json \
  --source-geometry-policy source_fraction_v1 \
  --output validation_v3_private/<fresh-output-name>
```

The command exits with the preservation-gate failure while eight of the historical 91 correct cases remain held. This result is development evidence, not unseen-paper qualification or permission to admit the text to a production graph. The default source-geometry policy remains disabled.
