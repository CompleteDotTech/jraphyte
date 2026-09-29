# PDF-bound fraction seam (opt-in locator support)

`source-vector-fraction-seam-v1` supports a narrowly defined raw reading-order
repair: a two-line native paragraph split between the numerator and denominator
of a numeric fraction. This is a locator API. Selector, converter, replay and
promotion consumers do **not** opt in automatically in this change.

## Supported API

```python
from trace_gc.pdf_source_parallel_v4 import SourceGeometry, locate

# Both values come from an authorized, independently pinned source receipt.
# Read one buffer, then use that exact buffer for hash checking and extraction.
source_bytes = source_path.read_bytes()
context = SourceGeometry.from_pdf(
    source_bytes, native_lines, expected_source_sha256=source_receipt_sha256,
)
alignment = locate(candidate_text, native_lines, source_geometry=context)
```

The factory re-extracts physical page 1 and requires the exact native JSON digest
to match. The context owns an immutable evidence buffer. `descriptor()` returns
a detached inspectable copy; deserialized dictionaries cannot be supplied as
verified contexts. A changed native input is rejected. The runtime dependency
is optional PyMuPDF, imported only when the factory is used.

The join requires all of the following:

- Complete native font-run partitions, matching baseline prose on both sides,
  a single smaller numeric numerator and nonzero denominator with matching
  font and geometry, and one matching horizontal vector rule between them.
- Every nonspace glyph in the four seam runs needs a unique, opaque painted
  text-trace witness with matching RAWDICT character, font, size and origin.
  Invisible, white, transparent, duplicated or later-obscured glyphs hold.
  Only the already-verified fraction rule can overlap numerator box padding.
- A unique standalone opaque, nonwhite stroke, no optional-content layer,
  unresolved clip/group hierarchy, annotation or widget overlays. Later
  overlapping images, shading, paths or painted glyphs reject the rule;
  overlapping duplicate strokes also reject it.
- Two source block starts, a unique following line owned by the second block,
  consistent paragraph typography, extent and spacing. A hidden later owner
  line, intervening prose, competing neighboring columns or rotated page holds.
- Existing source-occurrence ambiguity, region eligibility and the unchanged
  98% alignment threshold still apply.

The following support line requires consistent native font runs and painted
first/last glyphs in the same paint operation. This is explicitly **endpoint geometry
support**, not proof of every interior glyph or whole-line scientific fidelity.
Some real PDF ligature continuations lack an individual painted glyph in
`get_texttrace`; the locator does not invent a mapping for them.

The proof names the original PDF and native hashes, drawing command, exact
native run offsets/boxes and following support line. Native text, line IDs,
offsets and boxes remain unchanged. **No slash, fraction character or corrected
scientific expression is inserted.** Any selected fraction seam sets
`logical_geometry.notation_review_required=True`.

PyMuPDF reports drawing commands and their appearance sequence; those alone
do not establish visibility. The bounded occlusion checks use its drawing
hierarchy, paint bounds and per-glyph trace. Unsupported compositing stays held.
See the official [drawing API](https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_drawings)
and [paint bounds API](https://pymupdf.readthedocs.io/en/latest/functions.html#Page.get_bboxlog).

## Integration still required

A consumer must construct this context from the exact authorized original PDF
buffer and pass it explicitly through every relevant `locate` call. That
includes paragraph and final whole-text alignment, source-bound exclusion and
closure verification, and deterministic replay. A stored proof dictionary
cannot replace re-derivation from the pinned PDF. Pass the context explicitly;
do not install a process-global source context or monkey-patch production calls.

Consumers must propagate the logical notation flag into their existing math
review hold, preserve raw span roundtrip checks and retain independent section
ownership/closure gates. Any integration changes measured method hashes and
requires a new combined 200-paper run and source-reviewed fidelity evidence.
The existing passing reviewed 200-paper receipt remains evidence for its own
older implementation only.

## Evidence and limits

The exposed development case f059 has the supported drawn numeric stack.
Explicit locator opt-in keeps the exact three native spans and removes the
unsupported horizontal transition. Its unheaded full-width abstract followed
by two-column body still requires an attributed section-closure review. Its
raw fraction remains separate from a reviewed scientific transcription. This
change does not establish a whole-paper fidelity pass, independent human
validation, unseen qualification, automatic fallback, promotion or admission.

Authored synthetic PDFs exercise the positive seam plus missing, displaced,
invisible and overpainted rules; competing strokes and columns; clipping,
optional layers, invisible/obscured seam glyphs, rotation, changed typography/ownership, cropped regions,
duplicate source occurrences and source/native identity mutation:

```text
python -m unittest tests.test_parallel_source_fraction_seam_v4 -v
```
