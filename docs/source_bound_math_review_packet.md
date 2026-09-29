# Source-bound math review packet (prototype)

`trace_gc.pdf_math_review_v4.capture_math_review_packet(original_pdf_bytes,
cached_page_pdf_bytes, native_lines, structure_assessment)` derives review
evidence from the original PDF and the current page-one source-bound assessment.
It recaptures the existing native notation sidecar from the original bytes,
verifies the assessment seal, original-source and cached-page hashes, physical
page, page size, exact native identity and every owned glyph offset. It then
limits glyphs and candidate fraction/script relations to source spans already
owned by the abstract. Each glyph retains its raw Unicode, box, origin, font
resource references, trace witnesses and uncertainty. Fraction candidates
retain the observed vector rule and separate numerator/denominator glyph IDs.
Relations that cross the abstract boundary are listed but excluded.
Held formula regions are exposed separately as `held_candidate` from their
assessment-bound canonical native extents. A reviewer may explicitly name a
nearby native line as a witness; it must lie immediately above that candidate
and before the source-located closing boundary. Candidate glyphs and witnesses
remain unconfirmed and disjoint from included abstract glyphs. In particular,
f079's detached numerator is an explicit witness, not a promoted source span.

The packet always has `accepted: false`, `proposal: false`, no section owner and
no scientific transcription. Geometry, converter text and normalized text
agreement alone do not map a broken PDF glyph, prove a fraction's semantic
order, or settle scientific fidelity. A reviewer would have to verify the
rendered source and font/glyph evidence for each expression, bind a complete
expression order and scope, review the full abstract transcription, and run the
preservation and false-proposal gates before any separate admission adapter.

On the exposed 200-paper source set and the current source-geometry receipt,
the prototype produces these diagnostic counts:

| Case | Original PDF SHA-256 | Owned glyphs | Candidate relations | Unresolved glyphs | Controls/replacement glyphs |
| --- | --- | ---: | ---: | ---: | ---: |
| f079 | `743317f3d813449a9ce090f63fcee6c304e5f540fb5576b8652560b278ec82ff` | 446 | 6 | 63 | 0 |
| f081 | `628478fc6ce31b8ce771ebf28f240788323388a9145e32555246ec440734c951` | 896 | 12 | 149 | 0 |
| f122 | `48566c52c1e3bab9e5ca0619a51958e3845c71c1ce3b0d9f3c04a1b3aca59062` | 1118 | 9 | 157 | 0 |
| f153 | `f64770bace9a0742b4c7e560c153af9236f51fddf9e74e3c86a4bdf85abd1657` | 1487 | 4 | 220 | 6 |

Counts include ordinary glyphs with trace or font uncertainty; they do not
measure scientific transcription errors. The f079 numerator is a separate
native line above a rule; f081 ends with a vertically structured fraction;
f122's hat maps inconsistently between native and converter witnesses; f153
contains unresolved control glyphs in three expressions. All four remain held.

Focused tests cover owned fraction geometry, cross-boundary exclusion, control
glyph retention, changed source/page/native identity, duplicate and malformed
glyph offsets, missing uncertainty markers and a missing source rule. The four
source-first calls also read back the held formula scope for f079 and f122;
an authored negative checks that a body or Keywords line cannot bleed in.
The four
real-paper calls were read-only diagnostics and no packets were published or
used for proposals.
