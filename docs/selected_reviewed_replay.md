# Selected signed review replay

`python -m tools.selected_reviewed_replay --data-root ROOT --review-map PRIVATE_MAP.json --output NEW_PRIVATE_DIRECTORY --at ISO_UTC_TIME`

The map and output names are relative to the authorized external data root. The
output must be a new direct child of `validation_v3_private`. The map is an
application-owned trust enrollment, never model supplied. Keep it private;
its file hash is bound into the derived receipt. Its shape is:

```json
{
  "schema_version": 1,
  "baseline": "private/completed-baseline",
  "source_map": "private/original-source-map.json",
  "labels": "validation_expanded200/labels.json",
  "reviewers": [
    {"issuer": "reviewer-A", "principal": "reviewer-A", "public_key_base64": "...", "reviewer_kind": "assistant"},
    {"issuer": "reviewer-B", "principal": "reviewer-B", "public_key_base64": "...", "reviewer_kind": "assistant"}
  ],
  "cases": {
    "fNNN": {
      "source_pdf": "private/original.pdf",
      "page_pdf": "validation_v2/pages/fNNN/page.pdf",
      "page_image": "private/notation-render.png",
      "notation": "private/notation.json",
      "tex": "private/author-excerpt.tex",
      "manifest": "private/manifest.json",
      "reviews": ["private/reviewer-A.receipt.json", "private/reviewer-B.receipt.json"],
      "converter_assets": {
        "docling_status": "validation_v2/docling/fNNN.json",
        "docling_document": "validation_v2/docling/fNNN.document.json",
        "grobid": "validation_v2/grobid/fNNN.json"
      }
    }
  }
}
```

Use `validation_expanded200` paths for the second half of the cohort. Original
PDF paths must exactly match the source map and the preflight's verified
source identities. The frozen labels path and bytes must match the preflight.
The adapter verifies the completed
200 × 4 baseline assessment file hashes, scores, frozen inputs, runtime, code,
and signed review evidence before writing a new immutable selected receipt. It
recomputes the 91 historical text98 successes from gate-pinned saved v2
assessments and requires the selected primary results to preserve all 91. The
receipt also binds the baseline preflight, source map, and runner file hashes. It
never changes baseline files. A failure leaves the selected output unpublished.

The selected receipt measures **reviewed native text proposals**. It explicitly
does not qualify visual completeness, scientific notation, graph admission, or
independent human review. The map's public keys must be enrolled only after
the application owner verifies the reviewer identities and receipt provenance.
